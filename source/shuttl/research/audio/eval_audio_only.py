"""Audio-only contact detection on amateur rallies (per-venue lag fitted on labels = upper bound)."""
import collections, json, numpy as np
from common import audio_hits, data, curve, match, prf, in_windows

clips = [c for c in data.all_clips() if c.kind == 'amateur']
by_venue = collections.defaultdict(list)
for c in clips:
    by_venue[c.group].append(c)
out = {}
for z_min in (2.0, 3.0, 4.0, 5.0, 6.0, 8.0):
    tot = collections.Counter(); tot1 = collections.Counter(); res_all = []
    rows = {}
    for venue, cs in by_venue.items():
        ons = {c.name: audio_hits.onsets(curve(c), z_min) for c in cs}
        # one lag per venue (clips come from one continuous recording per venue)
        all_on = np.concatenate([ons[c.name][0] + 1000 * k for k, c in enumerate(cs)])
        all_z = np.concatenate([ons[c.name][1] for c in cs])
        all_gt = np.concatenate([c.hits_t + 1000 * k for k, c in enumerate(cs)])
        lag = audio_hits.estimate_lag(all_on, all_gt, all_z).lag_s
        v = collections.Counter(); v1 = collections.Counter()
        for c in cs:
            t, z = ons[c.name]
            t = t - lag
            t = t[in_windows(t, c.windows)]
            tp, fp, fn, res = match(t, c.hits_t, 2 / c.fps + 1e-6)
            v.update(tp=tp, fp=fp, fn=fn); res_all += list(res)
            tp1, fp1, fn1, _ = match(t, c.hits_t, 1 / c.fps + 1e-6)
            v1.update(tp=tp1, fp=fp1, fn=fn1)
        tot.update(v); tot1.update(v1)
        rows[venue] = dict(lag_ms=round(1e3 * lag), **{k: round(x, 3) for k, x in zip('prf', prf(v['tp'], v['fp'], v['fn']))})
    p, r, f = prf(tot['tp'], tot['fp'], tot['fn'])
    p1, r1, f1 = prf(tot1['tp'], tot1['fp'], tot1['fn'])
    res_all = np.abs(np.asarray(res_all)) * 1e3
    out[z_min] = dict(P=round(p, 3), R=round(r, 3), F1=round(f, 3), F1_1frame=round(f1, 3),
                      med_abs_err_ms=round(float(np.median(res_all)), 1) if len(res_all) else None, venues=rows)
    print(f"z>={z_min:4.1f}  P {p:.3f} R {r:.3f} F1@±2f {f:.3f}  F1@±1f {f1:.3f}  |err| med {out[z_min]['med_abs_err_ms']} ms  {rows}")
json.dump(out, open('results_audio_only.json', 'w'), indent=1)
