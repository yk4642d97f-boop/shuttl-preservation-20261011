"""Automatic court calibration (the runtime's own calibrate_from_frames) for a group of segments that share a
static camera, then floor positions of both players per frame, stored next to the features.
Usage: 16_calibrate.py SEGMENTS.json FEAT_DIR VIDEO_DIR [group-by-field]"""
import json, sys, os
from pathlib import Path
import numpy as np
sys.path.insert(0, '/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime/backend')
from app.services.tracking import court_calibration, players, video_io
segs_path, feat, videos = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
out = feat.parent / 'foot'; out.mkdir(exist_ok=True); report = {}
for m in json.loads(Path(segs_path).read_text()):
    items = [s for s in m['segments'] if (feat / (s['id'] + '.npz')).exists()]
    if not items: continue
    path = str(videos / m['video']); pick = items[:: max(1, len(items) // 24)][:24]
    frames = [next(f for _, f in video_io.iter_frames(path, (s['a'] + s['b']) // 2, (s['a'] + s['b']) // 2 + 1)) for s in pick]
    H, W = frames[0].shape[:2]; diag = {}
    cam = court_calibration.calibrate_from_frames(frames, (W, H), diagnostics=diag)
    report[m['match']] = dict(accepted=cam is not None, **{k: (float(v) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in diag.items() if k in ('confidence', 'rmse', 'reason', 'source', 'coverage')})
    print(m['match'], report[m['match']], flush=True)
    if cam is None: continue
    for s in items:
        z = np.load(feat / (s['id'] + '.npz')); n = len(z['covered']); foot = np.full((n, 2, 2), np.nan, np.float32)
        for p in (0, 1):
            ok = np.isfinite(z['box'][:, p]).all(-1) & np.isfinite(z['kp'][:, p]).all((-1, -2))
            if ok.any():
                px, ank = players.foot_pixels(z['box'][ok, p].astype(float), z['kp'][ok, p].astype(float))
                foot[ok, p] = players.floor_positions(cam, px, ank)
        np.save(out / (s['id'] + '.npy'), foot)
(feat.parent / 'calibration_report.json').write_text(json.dumps(report, indent=1))
