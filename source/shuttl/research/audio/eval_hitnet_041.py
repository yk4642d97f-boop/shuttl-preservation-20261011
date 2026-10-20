"""HitNet v2 in its own domain: validation match 041, research extraction, scored per rally.

Reports F1@±2 with all inputs and with the players' court foot positions removed (what an
uncalibrated video feeds the model), and the peak heights at true contacts (sets anchor_p).
The extraction npz (shuttle/players/foot_world/rally hits) is written by the research
pipeline (pose-eval/research/extract); it is not in the repo.

Run from source/shuttl/backend:
  SHUTTL_HITNET_WEIGHTS=.../hitnet_single_v2.pt PYTHONPATH=. python ../research/audio/eval_hitnet_041.py extract/out/041.npz
"""
import os, sys
import numpy as np
from app.services.tracking import hitnet, hitnet_core as core

z = np.load(sys.argv[1], allow_pickle=False)
model = hitnet.load(os.environ['SHUTTL_HITNET_WEIGHTS'], os.environ.get('INFERENCE_DEVICE', 'cuda'))
fps, W, H = float(z['fps']), float(z['width']), float(z['height'])
sxy, vis = z['shuttle_xy'].astype(float), z['shuttle_visible'] & np.isfinite(z['shuttle_xy']).all(1)
conf, interp = z['shuttle_conf'].astype(float), z['shuttle_interp'].astype(float)
box, foot = z['player_box'].astype(float), z['player_foot_world'].astype(float)
rs, hf, hs, frame = z['rally_row_start'], z['rally_hit_frames'], z['rally_hit_start'], z['frame']


def nms(p, thr=.4, gap_s=.3):
    gap = max(1, int(round(gap_s * fps)))
    pl, pr = np.r_[-1, p[:-1]], np.r_[p[1:], -1]
    idx = np.where((p > pl) & (p >= pr) & (p >= thr))[0]
    kept = []
    for i in idx[np.argsort(-p[idx], kind='stable')]:
        if all(abs(i - j) >= gap for j in kept):
            kept.append(int(i))
    return sorted(kept)


def match(det, gt, tol=2):
    cand = sorted((abs(a - b), i, j) for i, a in enumerate(det) for j, b in enumerate(gt) if abs(a - b) <= tol)
    ud, ug, pairs = set(), set(), []
    for _, i, j in cand:
        if i not in ud and j not in ug:
            ud.add(i); ug.add(j); pairs.append((i, j))
    return pairs


res = {k: [0, 0, 0] for k in ('full', 'no_foot')}
tp_peaks, fp_peaks, gt_p = [], [], []
for r in range(len(rs) - 1):
    a, b = int(rs[r]), int(rs[r + 1])
    T = b - a
    raw = np.full((T, 16), np.nan, np.float32)
    v = vis[a:b]
    raw[v, 0], raw[v, 1], raw[v, 2] = sxy[a:b][v, 0] / W, sxy[a:b][v, 1] / H, conf[a:b][v]
    raw[:, 3] = interp[a:b]
    for p in range(2):
        bx = box[a:b, p]; ok = np.isfinite(bx).all(1); o = 4 + 4 * p
        raw[ok, o], raw[ok, o + 1] = (bx[ok, 0] + bx[ok, 2]) / 2 / W, (bx[ok, 1] + bx[ok, 3]) / 2 / H
        raw[ok, o + 2], raw[ok, o + 3] = (bx[ok, 2] - bx[ok, 0]) / W, (bx[ok, 3] - bx[ok, 1]) / H
        ft = foot[a:b, p]; ok = np.isfinite(ft).all(1)
        raw[ok, 12 + 2 * p], raw[ok, 13 + 2 * p] = ft[ok, 0], ft[ok, 1]
    gt = list((hf[hs[r]:hs[r + 1]] - frame[a]).astype(int))
    for name in res:
        x = raw.copy()
        if name == 'no_foot':
            x[:, 12:16] = np.nan
        p = core.sigmoid(model.logits(x, fps)[:, 0])
        det = nms(p)
        pairs = match(det, gt)
        res[name][0] += len(pairs); res[name][1] += len(det); res[name][2] += len(gt)
        if name == 'full':
            matched = {i for i, _ in pairs}
            tp_peaks += [p[det[i]] for i in matched]
            fp_peaks += [p[d] for i, d in enumerate(det) if i not in matched]
            gt_p += [p[max(0, g - 2):g + 3].max() for g in gt if 0 <= g < T]
for name, (tp, nd, ng) in res.items():
    P, R = tp / max(1, nd), tp / max(1, ng)
    print(f'041 {name:8s} P {P:.3f} R {R:.3f} F1@2 {2 * P * R / (P + R):.3f}  ({tp}/{nd}/{ng})')
tp_peaks, fp_peaks, gt_p = map(np.asarray, (tp_peaks, fp_peaks, gt_p))
for thr in (.6, .7, .8, .9):
    print(f'  peak p>={thr}: {np.mean(tp_peaks >= thr):.3f} of true detections, {np.mean(fp_peaks >= thr) if len(fp_peaks) else 0:.3f} of false ones')
print('  true-detection peak p pct10/50/90:', np.percentile(tp_peaks, [10, 50, 90]).round(3), ' max', tp_peaks.max().round(3))
