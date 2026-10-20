"""Shared helpers: shipped backend code is imported, never re-implemented here."""
import os, sys, pickle
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '../../backend')))
from app.services.tracking import audio_hits   # noqa: E402
import data                                      # noqa: E402

CACHE = os.path.join(data.DATA, 'cache'); os.makedirs(CACHE, exist_ok=True)


def curve(clip):
    p = os.path.join(CACHE, clip.name + '.curve.pkl')
    if os.path.exists(p):
        return pickle.load(open(p, 'rb'))
    x, sr = data.read_wav(clip.wav)
    c = audio_hits.impact_curve_from_samples(x, sr, start_s=clip.audio_start)
    pickle.dump(c, open(p, 'wb'))
    return c


def match(pred_t, gt_t, tol):
    """Greedy one-to-one matching by distance; returns (tp, fp, fn, residuals pred-gt)."""
    pred_t, gt_t = np.asarray(pred_t, float), np.asarray(gt_t, float)
    if len(pred_t) == 0 or len(gt_t) == 0:
        return 0, len(pred_t), len(gt_t), np.zeros(0)
    d = np.abs(pred_t[:, None] - gt_t[None])
    pairs = np.argwhere(d <= tol)
    order = np.argsort(d[pairs[:, 0], pairs[:, 1]], kind='stable')
    up, ug, res = set(), set(), []
    for k in order:
        i, j = pairs[k]
        if i in up or j in ug:
            continue
        up.add(i); ug.add(j); res.append(pred_t[i] - gt_t[j])
    tp = len(up)
    return tp, len(pred_t) - tp, len(gt_t) - tp, np.asarray(res)


def prf(tp, fp, fn):
    p = tp / max(tp + fp, 1); r = tp / max(tp + fn, 1)
    return p, r, 2 * p * r / max(p + r, 1e-9)


def in_windows(t, windows):
    t = np.asarray(t, float)
    m = np.zeros(len(t), bool)
    for a, b in windows:
        m |= (t >= a) & (t <= b)
    return m
