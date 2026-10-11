"""Portable entry for the separate pose-evaluation archive, CPU or CUDA explicitly.

preflight verifies all bundled files and real model forwards; run evaluates the
frozen panel, compare verifies shared pixels/features. This is not an API server.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import torch
import numpy as np
import cv2
import onnxruntime as ort

import adapters
from adapters import HERE, ROOT, sha, load
from panel import R, write_new
import run as benchmark
from compare import compare
from app.services.tracking.video_io import iter_frames


def verify_bundle():
    manifest_path = ROOT / 'pose-eval-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for name, row in manifest['files'].items():
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink():
            raise ValueError('Unsafe bundle path')
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('Bundle mismatch: ' + name)
    return manifest_path, manifest


def runtime_versions():
    return dict(numpy=np.__version__, opencv=cv2.__version__, onnxruntime=ort.__version__,
                torch=torch.__version__, cuda_runtime=torch.version.cuda,
                cloud_entry_sha256=sha(Path(__file__)))


def preflight(args):
    manifest_path, manifest = verify_bundle()
    torch.set_num_threads(args.threads)
    panel_path = HERE / 'panels' / f'{args.panel}.json'
    panel = json.loads(panel_path.read_text())
    benchmark.verify_manifest(panel)
    frames = R.MatchFrames('041')
    event = panel['events'][0]
    fid = event['frame']
    _, image = next(iter_frames(str(ROOT / 'research/shuttleset/videos/041.mp4'), start=fid, stop=fid + 1))
    boxes = frames.data['player_box'][frames.indices[fid]]
    if not np.isfinite(boxes).all():
        raise ValueError('Frozen preflight frame missing boxes')
    with np.load(HERE / 'checks/reference.npz') as z:
        reference = {key: z[key] for key in z.files}
    if fid != int(reference['frame']):
        raise ValueError('Preflight frame number differs from CPU reference')
    decoded_sha = hashlib.sha256(image.tobytes()).hexdigest()
    reference_sha = str(reference['pixel_sha256'])
    decode = dict(frame=fid, decoded_pixel_sha256=decoded_sha,
                  reference_pixel_sha256=reference_sha, exact=decoded_sha == reference_sha)
    if args.reference_image:
        # Platform video decoders can differ in YUV->BGR rounding. Verify model
        # numerics with the exact frozen pixels, and report decoder drift separately.
        frozen = np.load(args.reference_image, allow_pickle=False)
        if frozen.dtype != np.uint8 or frozen.shape != image.shape or hashlib.sha256(frozen.tobytes()).hexdigest() != reference_sha:
            raise ValueError('Lossless reference image does not match frozen CPU pixels')
        difference = np.abs(image.astype(np.int16) - frozen.astype(np.int16))
        decode.update(max_pixel_error=int(difference.max()), mean_pixel_error=float(difference.mean()),
                      reference_image_sha256=sha(args.reference_image),
                      model_input='verified lossless CPU reference pixels')
        image = frozen
    elif not decode['exact']:
        raise ValueError('Preflight decoded frame differs from CPU reference; supply verified --reference-image for model-only parity')
    else:
        decode['model_input'] = 'decoded video pixels matching CPU reference'
    np.testing.assert_array_equal(boxes, reference['box'])
    rows = []
    for name in ['rtmpose_m', 'rtmpose_x', 'vitpose_plus_base']:
        model = load(name, args.device, args.threads)
        t = time.perf_counter()
        kp = model.estimate(image, boxes)
        np.testing.assert_equal(kp.shape, (2, 17, 3))
        if not np.isfinite(kp).all():
            raise ValueError('Model returned invalid keypoints')
        np.testing.assert_allclose(kp, reference['kp_' + name], atol=.03, rtol=0)
        rows.append(dict(model=model.info, elapsed_seconds=time.perf_counter() - t,
                         max_reference_error=float(np.abs(kp - reference['kp_' + name]).max())))
        del model
    clip, reason = frames.raw_clip(fid)
    if clip is None:
        raise ValueError('Preflight BST window unavailable: ' + str(reason))
    logits = R.classify([clip], args.device)
    if logits.shape != (1, 25) or not np.isfinite(logits).all():
        raise ValueError('Invalid BST output')
    np.testing.assert_allclose(logits, reference['bst_logits'], atol=1e-4, rtol=0)
    report = dict(device=args.device, environment=runtime_versions(), decode_comparison=decode,
                  bundle_files_verified=len(manifest['files']),
                  bundle_manifest_sha256=sha(manifest_path), models=rows,
                  bst_argmax=int(logits.argmax()), bst_logits=logits.tolist(),
                  bst_max_reference_error=float(np.abs(logits - reference['bst_logits']).max()),
                  scope='real input model loading/forward only; not complete validation or API deployment')
    write_new(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['preflight', 'run', 'compare'])
    p.add_argument('--model', choices=['rtmpose_m', 'rtmpose_x', 'vitpose_plus_base'])
    p.add_argument('--panel', choices=['small', 'full'], default='small')
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--report', type=Path, default=Path('pose-preflight.json'))
    p.add_argument('--reference-image', type=Path, help='Optional lossless .npy image verified against frozen reference hash')
    a = p.parse_args()
    # The archive carries the baseline too: no dependency on the host's home cache.
    adapters.BASELINE = HERE / 'models/rtmpose_m.onnx'
    if a.stage == 'preflight':
        preflight(a)
    elif a.stage == 'run':
        if not a.model:
            p.error('run requires --model')
        verify_bundle()
        benchmark.run(a)
        write_new(HERE / 'results' / a.panel / f'{a.model}_{a.device}' / 'runtime_versions.json', runtime_versions())
    else:
        verify_bundle()
        compare(a.panel, a.device)
