"""Run frozen validation pose arms; keep all selected labels and abstentions.

Usage: .venv/bin/python run.py --model rtmpose_m --panel small --device cpu
Then repeat for rtmpose_x and vitpose_plus_base; compare.py checks shared inputs.
No download, train, held-out evaluation, or production model selection occurs.
"""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
import torch

from adapters import HERE, ROOT, load, sha
from panel import R, write_new
from app.services.tracking.video_io import iter_frames


def ranges(ids):
    """Sorted half-open contiguous decode ranges; no gaps hidden in frame IDs."""
    ids = sorted(set(map(int, ids)))
    if not ids:
        return []
    out, start, last = [], ids[0], ids[0]
    for f in ids[1:]:
        if f != last + 1:
            out.append((start, last + 1))
            start = f
        last = f
    return out + [(start, last + 1)]


def joint_features(kp, box):
    """Same slot validity/normalization as the frozen BST feature reference."""
    if kp.shape[1:] != (2, 17, 3) or box.shape != (len(kp), 2, 4):
        raise ValueError('BST comparison accepts exactly two far/near slots')
    covered = np.isfinite(kp[:, :, 0, 0]).any(1)
    good = np.isfinite(box).all(-1) & np.isfinite(kp[:, :, :, :2]).all((-1, -2))
    good &= ~(kp[:, :, 15, 2] <= 0) & ~(kp[:, :, 16, 2] <= 0)
    good[:, 1] &= good[:, 0]
    centre = (box[:, :, :2] + box[:, :, 2:]) / np.float32(2)
    diag = np.maximum(np.hypot(box[:, :, 2] - box[:, :, 0], box[:, :, 3] - box[:, :, 1]), 1e-6)
    joints = np.where(good[:, :, None, None], (kp[..., :2] - centre[:, :, None]) / diag[:, :, None, None], 0).astype(np.float32)
    if not np.isfinite(joints).all():
        raise ValueError('Non-finite normalized features')
    return joints, covered, good.all(1)


def make_clips(events, window_ids, indices, joints, covered, resolved, pos, shuttle):
    clips, locations, predictions = [], [], []
    for event, ids in zip(events, window_ids):
        ix = [indices[f] for f in ids]
        reason = ('missing_window' if len(ix) < 2 else
                  'missing_pose_coverage' if not covered[ix].all() else
                  'no_resolved_players' if not resolved[ix[:R.B.SEQ_LEN]].any() else None)
        predictions.append(dict(id=event['id'], frame=event['frame'], label=event['class'], prediction=0,
                                abstain_reason=reason))
        if reason is None:
            locations.append(len(predictions) - 1)
            clips.append((joints[ix], pos[ix], shuttle[ix]))
    return clips, locations, predictions


def metrics(rows):
    if not rows or any(r['label'] not in range(1, 25) or r['prediction'] not in range(25) for r in rows):
        raise ValueError('Expected known labels and predictions in frozen class range')
    exact = sum(r['label'] == r['prediction'] for r in rows)
    typ = sum(r['prediction'] > 0 and (r['label'] - 1) % 12 == (r['prediction'] - 1) % 12 for r in rows)
    side = sum(r['prediction'] > 0 and (r['label'] - 1) // 12 == (r['prediction'] - 1) // 12 for r in rows)
    support = Counter(r['label'] for r in rows)
    per_class = {str(c): dict(support=n, correct=sum(r['label'] == c and r['prediction'] == c for r in rows)) for c, n in sorted(support.items())}
    return dict(n=len(rows), exact_correct=exact, exact_accuracy=exact / len(rows), type_correct=typ,
                type_accuracy=typ / len(rows), side_correct=side, side_accuracy=side / len(rows),
                macro_recall=float(np.mean([v['correct'] / v['support'] for v in per_class.values()])),
                classified=sum(r['prediction'] > 0 for r in rows), per_class=per_class,
                abstentions=dict(Counter(r['abstain_reason'] or 'model_unknown' for r in rows if not r['prediction'])))


def verify_manifest(panel):
    if panel['match'] != '041':
        raise ValueError('Only existing validation match041 is allowed')
    for p, digest in {**panel['sources'], **panel['bst_weights']}.items():
        if sha(ROOT / p) != digest:
            raise ValueError(f'Frozen input changed: {p}')
    if sha(HERE / 'panels/official_val_labels.json') != panel['official_labels_sha256']:
        raise ValueError('Frozen label mapping changed')


def run(args):
    torch.set_num_threads(args.threads)
    panel_path = HERE / 'panels' / f'{args.panel}.json'
    panel = json.loads(panel_path.read_text())
    verify_manifest(panel)
    result_dir = HERE / 'results' / args.panel / f'{args.model}_{args.device}'
    result_dir.mkdir(parents=True, exist_ok=False)
    frozen = R.MatchFrames('041')
    half = int(round(frozen.fps)) // 2
    window_ids = [[f for f in range(e['frame'] - half, e['frame'] + half + 1) if f in frozen.indices] for e in panel['events']]
    wanted = sorted(set(f for ids in window_ids for f in ids))
    source_ix = np.array([frozen.indices[f] for f in wanted])
    boxes = frozen.data['player_box'][source_ix].astype(np.float32)
    with np.load(ROOT / 'research/rtmpose/pose/041.npz') as z:
        np.testing.assert_allclose(boxes, z['box'][source_ix], rtol=0, atol=0, equal_nan=True)
    pos, shuttle = frozen.pos[source_ix], frozen.shuttle[source_ix]
    kp = np.full((len(wanted), 2, 17, 3), np.nan, np.float32)
    model = load(args.model, args.device, args.threads)
    write_new(result_dir / 'started.json', dict(panel_sha256=sha(panel_path), model=model.info,
               code_sha256={str(p.relative_to(ROOT)): sha(p) for p in [HERE / 'run.py', HERE / 'adapters.py', HERE / 'panel.py', HERE.parent / 'stroke_chain.py', Path(R.B.__file__), Path(R.CV.__file__)]},
               environment=dict(python=sys.version, platform=platform.platform(), device=args.device,
                    torch_cuda=torch.version.cuda,
                    packages={n: importlib.metadata.version(n) for n in ['numpy', 'torch', 'torchvision', 'rtmlib', 'transformers', 'scipy']},
                    cuda_name=torch.cuda.get_device_name(0) if args.device == 'cuda' else None)))
    indices = {f: i for i, f in enumerate(wanted)}
    pixel_hash = hashlib.sha256()
    valid_box_count, elapsed, inferred, t0 = 0, 0., 0, time.perf_counter()
    video = str(ROOT / 'research/shuttleset/videos/041.mp4')
    last_log = t0
    for start, stop in ranges(wanted):
        for fid, image in iter_frames(video, start=start, stop=stop):
            i = indices[fid]
            pixel_hash.update(np.asarray([fid, *image.shape], dtype='<i8').tobytes())
            pixel_hash.update(image.tobytes())
            valid = np.isfinite(boxes[i]).all(1) & (boxes[i, :, 2:] > boxes[i, :, :2]).all(1)
            if valid.any():
                tick = time.perf_counter()
                kp[i, valid] = model.estimate(image, boxes[i, valid])
                elapsed += time.perf_counter() - tick
                valid_box_count += int(valid.sum())
            inferred += 1
            if time.perf_counter() - last_log >= 20:
                print(args.model, inferred, '/', len(wanted), 'frames', round(time.perf_counter() - t0, 1), 'seconds', flush=True)
                last_log = time.perf_counter()
    if inferred != len(wanted):
        raise RuntimeError('Missing video frames; refusing incomplete report')
    total_pose_seconds = time.perf_counter() - t0
    joints, covered, resolved = joint_features(kp, boxes)
    clips, locs, rows = make_clips(panel['events'], window_ids, indices, joints, covered, resolved, pos, shuttle)
    tick = time.perf_counter()
    logits = R.classify(clips, args.device)
    bst_seconds = time.perf_counter() - tick
    for i, logit in zip(locs, logits):
        rows[i]['prediction'] = int(logit.argmax())
        if rows[i]['prediction'] == 0:
            rows[i]['abstain_reason'] = 'model_unknown'
    np.savez_compressed(result_dir / 'outputs.npz', frame=np.array(wanted), kp=kp, box=boxes,
                        joints=joints, pos=pos, shuttle=shuttle, covered=covered, resolved=resolved,
                        logits=logits, classified_row_indices=np.array(locs))
    report = dict(panel_sha256=sha(panel_path), pixel_sha256=pixel_hash.hexdigest(), model=model.info,
                  metrics=metrics(rows), predictions=rows, frame_count=len(wanted), pose_count=valid_box_count,
                  covered_frames=int(covered.sum()), resolved_frames=int(resolved.sum()),
                  inference_seconds=elapsed, decode_and_pose_seconds=total_pose_seconds, bst_seconds=bst_seconds,
                  poses_per_second=valid_box_count / max(elapsed, 1e-9), timing_scope='pose preprocessing, inference and postprocessing; excludes decoding/model loading/BST; hardware-specific, not GPU evidence when cpu',
                  outputs_sha256=sha(result_dir / 'outputs.npz'),
                  scope=panel['protocol']['scope'])
    write_new(result_dir / 'report.json', report)
    print(json.dumps(dict(model=args.model, metrics=report['metrics'], seconds=total_pose_seconds), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['rtmpose_m', 'rtmpose_x', 'vitpose_plus_base'], required=True)
    parser.add_argument('--panel', choices=['small', 'full'], default='small')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--threads', type=int, default=2)
    run(parser.parse_args())
