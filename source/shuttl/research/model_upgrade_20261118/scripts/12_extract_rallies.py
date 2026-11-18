"""Rally-level per-frame feature extraction for VideoBadminton (2026-11-18).

Clips in this dataset are consecutive [hit_k, hit_k+1) intervals of the same recording
(4,762 of 7,699 neighbouring clip pairs are frame-contiguous and the player alternates in
4,761 of them). Contiguous clips are therefore decoded back into one continuous segment
and tracked as production would track a rally. Clip start offsets are kept as the
dataset authors' hit frames. No labels are created; model outputs are stored as features.
"""
from __future__ import annotations
import argparse, json, os, sys, time, traceback, zipfile
from dataclasses import replace
from pathlib import Path

RUNTIME = Path('/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime')


def write_json(path, value):
    tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(value, ensure_ascii=False)); tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--queue', type=Path, required=True)
    ap.add_argument('--zip', type=Path, required=True)
    ap.add_argument('--rank', type=int, default=0); ap.add_argument('--world', type=int, default=1)
    ap.add_argument('--limit', type=int); ap.add_argument('--batch', type=int, default=16)
    ap.add_argument('--mem-fraction', type=float, default=0.08)
    a = ap.parse_args(); root = a.root; out = root / 'feat'; out.mkdir(parents=True, exist_ok=True)
    media = root / 'media'; media.mkdir(exist_ok=True)
    os.environ['OMP_NUM_THREADS'] = '2'; os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['MKL_NUM_THREADS'] = '2'; os.environ['YOLO_CONFIG_DIR'] = str(root / 'yolo-config')
    import cv2, numpy as np, torch
    cv2.setNumThreads(1); torch.set_num_threads(2); torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    torch.cuda.set_per_process_memory_fraction(a.mem_fraction)
    sys.path.insert(0, str(RUNTIME / 'backend'))
    from app.services.tracking import bst, detector, linker, players, video_io, rtmpose_core as rc
    from app.services.tracking.hitnet import player_index
    state = {'rank': a.rank, 'pid': os.getpid(), 'started': time.time(), 'done': 0, 'failed': 0}
    state_file = root / f'worker-{a.rank}.json'

    def status(stage, **kw):
        state.update(stage=stage, updated=time.time(), **kw); write_json(state_file, state)

    queue = json.loads(a.queue.read_text())
    if a.limit: queue = queue[:a.limit]
    queue = [r for i, r in enumerate(queue) if i % a.world == a.rank]
    queue = [r for r in queue if not (out / (r['id'] + '.npz')).exists() and not (out / (r['id'] + '-error.json')).exists()]
    from app.services.tracking.data_types import VideoMeta
    from app.services.tracking import hitnet as hn
    if not queue: status('complete', pending=0); return
    status('loading_models', pending=len(queue))
    yolo = players.make_yolo_detector(str(RUNTIME / 'backend/ml/weights/yolov8s-pose.pt'), 'cuda', imgsz=1280)
    model, spec = detector.load_model(RUNTIME / 'backend/ml/weights/wasb_badminton_best.pth.tar', 'wasb')
    ball = detector.HeatmapDetector(model, spec, device='cuda', half=False, batch_size=a.batch, min_score=.1, stride=3, prefetch=False)
    session = rc.make_session(str(RUNTIME / 'research/cloud_upgrade/artifacts/runtime/rtmpose_m_body7.onnx'),
                              ['CUDAExecutionProvider', 'CPUExecutionProvider'],
                              provider_options=[{'device_id': '0', 'use_tf32': '0', 'gpu_mem_limit': str(3 * 1024 ** 3)}, {}], threads=1)
    if session.get_providers()[0] != 'CUDAExecutionProvider': raise RuntimeError('GPU pose provider unavailable')
    session.disable_fallback(); input_name = session.get_inputs()[0].name; output_names = [x.name for x in session.get_outputs()]

    def refine(frames, observations):
        result = []; batch = []; info = []

        def flush():
            if not batch: return
            x = np.stack(batch); outputs = session.run(output_names, {input_name: x})
            locs, scores = rc.get_simcc_maximum(outputs[0], outputs[1])
            for (obs, center, scale), loc, sc in zip(info, locs, scores):
                kp = loc / 2. / np.array(rc.INPUT_SIZE, np.float32) * scale + center - scale / 2
                result.append(replace(obs, keypoints=np.concatenate((kp, sc[:, None]), axis=1).astype(np.float32)))
            batch.clear(); info.clear()

        for obs in observations:
            image = frames[obs.frame]; h, w = image.shape[:2]
            padded = rc.pad_box(np.asarray(obs.bbox), w, h)
            center, scale = rc.bbox_xyxy2cs(padded, padding=1.25)
            crop, scale = rc.top_down_affine(rc.INPUT_SIZE, scale, center, image)
            batch.append(((crop.astype(np.float32) - rc.MEAN) / rc.STD).transpose(2, 0, 1))
            info.append((obs, center, scale))
            if len(batch) >= 64: flush()
        flush(); return result

    z = zipfile.ZipFile(a.zip)
    for entry in queue:
        began = time.time(); key = entry['id']
        try:
            frames = []; hits = []; fps = None; W = H = 0
            for c in entry['clips']:
                path = media / (c['id'] + '.mp4')
                if not path.exists(): path.write_bytes(z.read(c['zip_member']))
                m = video_io.probe(str(path))
                got = [image for _, image in video_io.iter_frames(str(path))]
                if len(got) != c['frames']: raise ValueError(f"Decoded {len(got)} frames, expected {c['frames']} in {c['id']}")
                if fps is None:
                    fps = float(m.fps) if m.fps and m.fps > 0 else 30.0; W, H = m.width, m.height
                elif (m.width, m.height) != (W, H): raise ValueError('Frame size changes inside a segment')
                hits.append(len(frames)); frames += got
            n = len(frames)
            if n < 2: raise ValueError(f'Segment too short: {n}')
            meta = VideoMeta(fps=fps, width=W, height=H, n_frames=n, timestamps=np.arange(n, dtype=np.float64) / fps)
            sampled = []
            indices = list(range(n))
            for start in range(0, n, a.batch):
                ids = indices[start:start + a.batch]; images = [frames[i] for i in ids]
                detections = yolo(images, ids)
                for fi, image, dets in zip(ids, images, detections):
                    sampled.append(players.build_candidates(fi, dets, None, (meta.width, meta.height), image=image))
            observations = players.assemble_tracks(sampled, meta, None, doubles=False)
            refined = refine(frames, observations)

            def source(step):
                return ((i, frames[i]) for i in range(0, len(frames), step))

            candidates = ball.detect_frames(source, meta.width, meta.height, meta.fps, meta.n_frames)
            track = linker.link_candidates(candidates, meta)
            joints, position, sh, covered, resolved = bst.frame_features(track, meta, refined)
            index, multiple = player_index(refined)
            box = np.full((n, 2, 4), np.nan, np.float32); kp = np.full((n, 2, 17, 3), np.nan, np.float32)
            for (f, side), obs in index.items():
                if not 0 <= f < n: continue
                p = 0 if side == 'far' else 1
                if np.shape(obs.bbox) == (4,): box[f, p] = obs.bbox
                if np.shape(obs.keypoints) == (17, 3): kp[f, p] = obs.keypoints
            try: raw16 = hn.raw_matrix(track, meta, refined)
            except Exception as e: raw16 = np.zeros((0, 16), np.float32)
            np.savez_compressed(out / (key + '.npz'), joints=joints.astype(np.float32), shuttle=sh.astype(np.float32),
                                covered=covered, resolved=resolved, box=box, kp=kp,
                                xy=np.asarray(track.xy, np.float32), visible=np.asarray(track.visible), conf=np.asarray(track.conf, np.float32),
                                interpolated=np.asarray(track.interpolated),
                                meta=np.array([meta.fps, meta.width, meta.height, n], np.float32), hits=np.array(hits, np.int32),
                                hitnet_raw=raw16, diag=json.dumps(getattr(observations, 'diagnostics', {}), default=str))
            del frames
            torch.cuda.empty_cache()
            state['done'] += 1
        except Exception as e:
            state['failed'] += 1; torch.cuda.empty_cache()
            write_json(out / (key + '-error.json'), {'id': key, 'error': f'{type(e).__name__}: {e}', 'traceback': traceback.format_exc()})
        if state['done'] % 20 == 0:
            status('running', clips_per_second=state['done'] / max(time.time() - state['started'], 1), last_seconds=time.time() - began)
    status('complete', max_torch_memory_gb=torch.cuda.max_memory_allocated() / 1024 ** 3)


if __name__ == '__main__': main()
