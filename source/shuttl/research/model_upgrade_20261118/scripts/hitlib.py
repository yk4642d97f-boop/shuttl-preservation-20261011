"""Hit-detection data and scoring on rally segments (VideoBadminton amateur rallies, BFMD pro rallies).

A segment is one continuous tracked interval with the dataset authors' hit frames. A
VideoBadminton segment starts exactly on its first hit (no footage before it exists) and the frame
after its last frame may be another, unlisted hit. Both ends are artefacts of how the clips were
cut, so the first and last EDGE frames are neither scored nor trained on: a detector could
otherwise learn "a sequence starts with a hit", which is never true in a real recording.
"""
import json, sys
from pathlib import Path
import numpy as np

RUNTIME = Path('/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime')
sys.path.insert(0, str(RUNTIME / 'backend'))
HERE = Path('/root/shuttl-claude-20261118')
HITNET = RUNTIME / 'research/cloud_upgrade/artifacts/hitnet_single_v2.pt'
EDGE = 4
VB_SPLIT = {'2022-08-30': 'train', '2022-08-31': 'train', '2022-09-06': 'train', '2022-09-07': 'development',
            '2022-09-01': 'holdout', '2023-05-02': 'holdout2'}


def load_vb():
    out = []
    for s in json.loads((HERE / 'vb_segments.json').read_text()):
        f = Path('/dev/shm/claude/vbr/feat') / (s['id'] + '.npz')
        if not f.exists(): continue
        z = np.load(f)
        if len(z['hitnet_raw']) != len(z['covered']): continue
        out.append(dict(id=s['id'], domain='vb', split=VB_SPLIT[s['date']], group=s['session'], raw=z['hitnet_raw'], kp=z['kp'], box=z['box'], wh=z['meta'][1:3], fps=float(z['meta'][0]),
                        hits=z['hits'].astype(int), valid_to=len(z['covered']) - EDGE, valid_from=EDGE, sides=None))
    return out


def load_bfmd(with_foot=True):
    import cv2
    from app.services.tracking import players
    out = []
    for m in json.loads((HERE / 'bfmd_segments.json').read_text()):
        c = m['court']
        Hm = cv2.getPerspectiveTransform(np.float32([c['top_left'], c['top_right'], c['bottom_right'], c['bottom_left']]), np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]))
        split = 'test' if 'All-England' in m['match'] else ('dev' if 'Shi-Yu-Qi-CHN-3-vs.-Wang-Zheng-Xing' in m['match'] else 'train')
        for sg in m['segments']:
            f = Path('/dev/shm/claude/bfmd/feat') / (sg['id'] + '.npz')
            if not f.exists(): continue
            z = np.load(f); raw = z['hitnet_raw'].copy()
            if len(raw) != len(z['covered']): continue
            if with_foot:
                for p in (0, 1):
                    ok = np.isfinite(z['box'][:, p]).all(-1) & np.isfinite(z['kp'][:, p]).all((-1, -2))
                    if ok.any():
                        foot, _ = players.foot_pixels(z['box'][ok, p].astype(float), z['kp'][ok, p].astype(float))
                        uv = cv2.perspectiveTransform(foot[None].astype(np.float32), Hm)[0]
                        raw[ok, 12 + 2 * p] = 6.7 - uv[:, 1] * 13.4; raw[ok, 13 + 2 * p] = (0.5 - uv[:, 0]) * 6.1
            out.append(dict(id=sg['id'], domain='bfmd', split=split, group=m['match'], raw=raw, kp=z['kp'], box=z['box'], wh=z['meta'][1:3], fps=30.0,
                            hits=np.array([h['frame'] for h in sg['hits']], int), valid_to=len(raw), sides=None))
    return out


def vb_sides():
    """segment id -> array of inferred hitter side per hit (1 near, 0 far, -1 undecided), from the BST build."""
    out = {}
    for split in ('train', 'development', 'holdout', 'holdout2'):
        z = np.load(HERE / 'data' / f'vb_hit_{split}.npz', allow_pickle=False)
        for seg, k, side in zip(z['seg'], z['k'], z['side']): out.setdefault(str(seg), {})[int(k)] = int(side)
    return {seg: np.array([d.get(k, -1) for k in range(max(d) + 1)]) for seg, d in out.items()}


def load_generic(path, feat_dir, domain, split):
    out = []
    for m in json.loads(Path(path).read_text()):
        for sg in m['segments']:
            f = Path(feat_dir) / (sg['id'] + '.npz')
            if not f.exists(): continue
            z = np.load(f)
            if len(z['hitnet_raw']) != len(z['covered']): continue
            raw = z['hitnet_raw'].copy(); ff = Path(feat_dir).parent / 'foot' / (sg['id'] + '.npy')
            if ff.exists():
                foot = np.load(ff); raw[:, 12:14] = foot[:, 0]; raw[:, 14:16] = foot[:, 1]
            out.append(dict(id=sg['id'], domain=domain, split=split, group=m['match'], raw=raw, kp=z['kp'], box=z['box'], wh=z['meta'][1:3], fps=float(z['meta'][0]),
                            hits=np.array([h['frame'] for h in sg['hits']], int), valid_to=len(z['covered']), sides=None))
    return out


def rules_detect(seg_id, feat_dir):
    """Production rule detector (hits.detect_hits) re-run from stored track and player arrays."""
    from app.services.tracking import hits as rules
    from app.services.tracking.data_types import Track2D, VideoMeta, PlayerObservation
    z = np.load(Path(feat_dir) / (seg_id + '.npz')); n = len(z['covered']); fps = float(z['meta'][0])
    t = np.arange(n, dtype=np.float64) / fps
    track = Track2D(t=t, xy=z['xy'].astype(np.float64), conf=z['conf'].astype(np.float64), visible=z['visible'], interpolated=z['interpolated'])
    meta = VideoMeta(fps=fps, width=int(z['meta'][1]), height=int(z['meta'][2]), n_frames=n, timestamps=t)
    pl = []
    for f in range(n):
        for p, side in ((0, 'far'), (1, 'near')):
            if np.isfinite(z['box'][f, p]).all():
                pl.append(PlayerObservation(frame=f, track_id=2 - p, bbox=z['box'][f, p].astype(float), score=1.0, side=side,
                                            keypoints=z['kp'][f, p] if np.isfinite(z['kp'][f, p]).all() else None))
    return [h.frame for h in rules.detect_hits(track, meta, None, pl)]


def pose_features(seg, raw=None):
    """(T,26) arm kinematics per player for the pose-aware hit detector: wrist positions relative to the
    box, wrist velocities and speed, and the shuttle's distance to the nearer wrist. Zero where unknown."""
    kp = seg['kp'].astype(np.float64); box = seg['box'].astype(np.float64); W, H = float(seg['wh'][0]), float(seg['wh'][1])
    raw = seg['raw'] if raw is None else raw
    T = len(kp); ps = seg['fps'] / 30.0; out = np.zeros((T, 26), np.float32)
    sx, sy = raw[:, 0].astype(np.float64) * W, raw[:, 1].astype(np.float64) * H
    for p in (0, 1):
        o = 13 * p; hgt = np.maximum(box[:, p, 3] - box[:, p, 1], 1.0); cx = (box[:, p, 0] + box[:, p, 2]) / 2; cy = (box[:, p, 1] + box[:, p, 3]) / 2
        ok = np.isfinite(box[:, p]).all(-1) & np.isfinite(kp[:, p, 9:11, :2]).all((-1, -2)) & np.isfinite(raw[:, 4 + 4 * p])
        speed = []
        for w, j in enumerate((9, 10)):
            x = np.where(ok, (kp[:, p, j, 0] - cx) / hgt, np.nan); y = np.where(ok, (kp[:, p, j, 1] - cy) / hgt, np.nan)
            vx = np.full(T, np.nan); vy = np.full(T, np.nan); vx[1:-1] = (x[2:] - x[:-2]) / 2; vy[1:-1] = (y[2:] - y[:-2]) / 2
            out[:, o + 4 * w + 0] = np.nan_to_num(x); out[:, o + 4 * w + 1] = np.nan_to_num(y)
            out[:, o + 4 * w + 2] = np.clip(np.nan_to_num(vx) * 10 * ps, -6, 6); out[:, o + 4 * w + 3] = np.clip(np.nan_to_num(vy) * 10 * ps, -6, 6)
            speed.append(np.nan_to_num(np.hypot(vx, vy)) * 10 * ps)
        out[:, o + 8] = np.clip(np.maximum(speed[0], speed[1]), 0, 6)
        d = np.minimum(np.hypot(kp[:, p, 9, 0] - sx, kp[:, p, 9, 1] - sy), np.hypot(kp[:, p, 10, 0] - sx, kp[:, p, 10, 1] - sy)) / hgt
        seen = ok & np.isfinite(sx)
        out[:, o + 9] = np.where(seen, np.clip(d, 0, 6) / 3, 0); out[:, o + 10] = seen; out[:, o + 11] = ok
        out[:, o + 12] = np.where(ok, np.clip((kp[:, p, 9:11, 1].min(1) - box[:, p, 1]) / hgt, -1, 2), 0)      # how high the upper wrist is in the box
    return out


def features(seg, n_in, raw=None, aug_pose=None):
    from app.services.tracking import hitnet_core as core
    raw = seg['raw'] if raw is None else raw
    x = core.derive(raw, seg['fps'])
    if n_in == 51: return x
    return np.concatenate((x, pose_features(seg, raw)), 1)


def match(pred, truth, tol):
    """One-to-one greedy matching within +/-tol frames; returns tp."""
    pred = sorted(pred); truth = sorted(truth); used = set(); tp = 0
    for t in truth:
        best = None
        for i, p in enumerate(pred):
            if i in used or abs(p - t) > tol: continue
            if best is None or abs(p - t) < abs(pred[best] - t): best = i
        if best is not None: used.add(best); tp += 1
    return tp


def score(segments, detections, tol=2):
    """detections: dict id -> list of frames. Returns pooled P/R/F1 and first-hit/interior recall."""
    tp = fp = fn = 0; first = [0, 0]; inner = [0, 0]; minutes = 0.
    for s in segments:
        lo = s.get('valid_from', 0)
        truth = [int(h) for h in s['hits'] if lo <= h < s['valid_to']]
        pred = [int(p) for p in detections.get(s['id'], []) if lo <= p < s['valid_to']]
        t = match(pred, truth, tol); tp += t; fp += len(pred) - t; fn += len(truth) - t
        minutes += max(0, s['valid_to'] - lo) / s['fps'] / 60
        if truth:
            first[1] += 1; first[0] += match(pred, truth[:1], tol)
            inner[1] += len(truth) - 1; inner[0] += match(pred, truth[1:], tol) if len(truth) > 1 else 0
    p = tp / max(tp + fp, 1); r = tp / max(tp + fn, 1)
    return dict(P=round(p, 4), R=round(r, 4), F1=round(2 * p * r / max(p + r, 1e-9), 4), tp=tp, fp=fp, fn=fn,
                first_hit_recall=round(first[0] / max(first[1], 1), 4), interior_recall=round(inner[0] / max(inner[1], 1), 4),
                fp_per_min=round(fp / max(minutes, 1e-9), 2), segments=len(segments))
