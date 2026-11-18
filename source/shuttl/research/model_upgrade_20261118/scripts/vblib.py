"""VideoBadminton rally features -> BST inputs (2026-11-18).

Label facts established today (no human labelling by us):
  * the 18 source classes are the 18 ShuttleSet stroke types in English; they merge into the
    12 BST types exactly as the BST authors merge ShuttleSet (see MAP18);
  * a clip is the interval [hit_k, hit_k+1): its first frame is the authors' hit frame.
Windows are cut exactly as production does (bst.clip_at): hit +/- round(fps)//2 frames.
"""
import json, sys
from pathlib import Path
import numpy as np

RUNTIME = Path('/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime')
sys.path.insert(0, str(RUNTIME / 'backend'))
TYPES = ('net', 'block', 'smash', 'lift', 'clear', 'drive', 'drop', 'push', 'kill', 'cross_net', 'short_serve', 'long_serve')
MAP18 = {  # source class -> BST merged type (ShuttleSet name)
    '00_Short Serve': 'short_serve',            # 發短球
    '01_Cross Court Flight': 'cross_net',       # 勾球
    '02_Lift': 'lift',                          # 挑球
    '03_Tap Smash': 'smash',                    # 點扣 -> 殺球
    '04_Block': 'block',                        # 擋小球
    '05_Drop Shot': 'net',                      # 放小球  (mapped to 切球 "drop" on 2026-11-17: wrong)
    '06_Push Shot': 'push',                     # 推球
    '07_Transitional Slice': 'drop',            # 過渡切球 -> 切球
    '08_Cut': 'drop',                           # 切球
    '09_Rush Shot': 'kill',                     # 撲球
    '10_Defensive Clear': 'lift',               # 防守回挑 -> 挑球
    '11_Defensive Drive': 'drive',              # 防守回抽 -> 平球
    '12_Clear': 'clear',                        # 長球
    '13_Long Serve': 'long_serve',              # 發長球
    '14_Smash': 'smash',                        # 殺球
    '15_Flat Shot': 'drive',                    # 平球
    '16_Rear Court Flat Drive': 'drive',        # 後場抽平球 -> 平球
    '17_Short Flat Shot': 'drive',              # 小平球 -> 平球
}
OLD8 = {'00_Short Serve': 'short_serve', '02_Lift': 'lift', '04_Block': 'block', '05_Drop Shot': 'drop', '06_Push Shot': 'push',
        '12_Clear': 'clear', '13_Long Serve': 'long_serve', '14_Smash': 'smash'}   # the 2026-11-17 mapping, kept for comparison
SPLIT = {'2022-08-30': 'train', '2022-08-31': 'train', '2022-09-06': 'train', '2022-09-07': 'development',
         '2022-09-01': 'holdout', '2023-05-02': 'holdout2'}


def side_cues(z, h):
    """Two image cues that the NEAR (bottom) player made the hit at frame h; each in {-1,0,+1}.
    prox: the shuttle is closer to the near player's box; swing: the near player's wrist moves faster."""
    xy = z['xy']; vis = z['visible']; box = z['box']; kp = z['kp']; n = len(vis); prox = 0.0
    for i in sorted(range(max(0, h - 3), min(n, h + 4)), key=lambda i: abs(i - h)):
        if not (vis[i] and np.isfinite(xy[i]).all() and np.isfinite(box[i]).all()): continue
        d = []
        for p in (0, 1):
            x1, y1, x2, y2 = box[i, p]; hgt = max(y2 - y1, 1.0)
            dx = max(x1 - xy[i, 0], 0, xy[i, 0] - x2); dy = max(y1 - xy[i, 1], 0, xy[i, 1] - y2)
            d.append(float(np.hypot(dx, dy)) / hgt)
        if abs(d[0] - d[1]) > 0.25: prox = 1.0 if d[1] < d[0] else -1.0
        break
    a, b = max(0, h - 5), min(n, h + 3); sp = [0.0, 0.0]
    for p in (0, 1):
        w = kp[a:b, p, 9:11, :2]; hgt = box[a:b, p, 3] - box[a:b, p, 1]
        if len(w) < 2: continue
        v = np.linalg.norm(np.diff(w, axis=0), axis=-1).max(1) / np.maximum(hgt[1:], 1.0)
        v = v[np.isfinite(v)]
        sp[p] = float(v.max()) if len(v) else 0.0
    swing = 0.0
    if max(sp) > 0.05 and max(sp) > 1.4 * min(sp): swing = 1.0 if sp[1] > sp[0] else -1.0
    return prox, swing


def window(z, h, fps, lower=0, upper=None, center=True):
    """Production window (bst.clip_at) around hit frame h. With center=True, frames missing before
    `lower` are zero-filled so the contact keeps its usual index; returns arrays + bookkeeping."""
    joints, shuttle = z['joints'], z['shuttle']
    n = len(joints); upper = n if upper is None else upper
    half = int(round(fps)) // 2
    a, b = h - half, min(upper, h + half + 1)
    pad = max(0, lower - a); a = max(lower, a)
    j = joints[a:b]; s = shuttle[a:b]
    cov = z['covered'][a:b]; res = z['resolved'][a:b]
    if center and pad:
        j = np.concatenate((np.zeros((pad,) + j.shape[1:], j.dtype), j)); s = np.concatenate((np.zeros((pad, 2), s.dtype), s))
    return j, s, dict(a=a, b=b, pad=pad, covered_all=bool(cov.all()) if len(cov) else False,
                      resolved_any=bool(res[:30].any()) if len(res) else False, resolved_frac=float(res.mean()) if len(res) else 0.0,
                      covered_frac=float(cov.mean()) if len(cov) else 0.0)


def to_model(j, s):
    from app.services.tracking import bst
    p = np.zeros((len(j), 2, 2), np.float32)
    jnb, sh, pos, length = bst.model_inputs([(j, p, s)])
    return jnb[0], sh[0], pos[0], int(length[0])
