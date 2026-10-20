"""How precise must visual anchors be for audio_hits.estimate_lag (the shipped, z-weighted function)?

Anchors = labels with jitter (Gaussian σ, or HitNet's measured offset spread), 10% dropped,
10% spurious; 30 draws per setting; error vs the lag fitted on clean labels.
"""
import collections, json, numpy as np
from common import audio_hits, data, curve
from app.services.tracking.hit_fusion import FusionParams
P = FusionParams()
clips = [c for c in data.all_clips() if c.kind == 'amateur']
by = collections.defaultdict(list)
for c in clips: by[c.group].append(c)
rng = np.random.default_rng(7)
OFF = np.array([0, 1, -1, 2, -2, 3]); W = np.array([2032, 1390, 430, 309, 100, 59], float); W /= W.sum()
out = {}
for venue, cs in by.items():
    ons = [audio_hits.onsets(curve(c), P.onset_z) for c in cs]
    on = np.concatenate([t + 1000 * k for k, (t, _) in enumerate(ons)])
    oz = np.concatenate([z for _, z in ons])
    gt = np.concatenate([c.hits_t + 1000 * k for k, c in enumerate(cs)])
    span = np.array([[1000 * k, 1000 * k + c.pts[-1]] for k, c in enumerate(cs)])
    ref = audio_hits.estimate_lag(on, gt, oz)
    rows = {}
    for name in ('sigma0.5', 'sigma1', 'hitnet', 'sigma2'):
        errs, exc = [], []
        for rep in range(30):
            keep = gt[rng.random(len(gt)) > 0.10]
            jit = rng.choice(OFF, len(keep), p=W) if name == 'hitnet' else rng.normal(0, float(name[5:]), len(keep))
            k = rng.integers(0, len(span), int(0.1 * len(gt)))
            fp = span[k, 0] + rng.random(len(k)) * (span[k, 1] - span[k, 0])
            est = audio_hits.estimate_lag(on, np.concatenate([keep + jit / 30, fp]), oz)
            errs.append(abs(est.lag_s - ref.lag_s) * 1e3); exc.append(est.excess)
        rows[name] = dict(lag_err_ms_med=round(float(np.median(errs)), 1), lag_err_ms_p90=round(float(np.percentile(errs, 90)), 1),
                          excess_med=round(float(np.median(exc)), 3), excess_p10=round(float(np.percentile(exc, 10)), 3),
                          excess_max=round(float(np.max(exc)), 3),
                          gate_on=round(float(np.mean(np.array(exc) >= P.min_excess)), 2))
    out[venue] = dict(hits=int(len(gt)), label_lag_ms=round(ref.lag_s * 1e3), label_excess=round(ref.excess, 3),
                      label_match_rate=round(ref.match_rate, 2), anchors=rows)
    print(venue, json.dumps(out[venue]))
json.dump(out, open('results_lag_robustness.json', 'w'), indent=1)
