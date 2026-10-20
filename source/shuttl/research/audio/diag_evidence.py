"""How strong is the audio at true contacts vs other in-rally instants? (per venue, label lag)"""
import collections, numpy as np
from common import audio_hits, data, curve, match, prf, in_windows
clips = [c for c in data.all_clips() if c.kind == 'amateur']
by = collections.defaultdict(list)
for c in clips: by[c.group].append(c)
for venue, cs in by.items():
    ons = [audio_hits.onsets(curve(c), 3.0) for c in cs]
    on = np.concatenate([t + 1000 * k for k, (t, _) in enumerate(ons)])
    oz = np.concatenate([z for _, z in ons])
    gt = np.concatenate([c.hits_t + 1000 * k for k, c in enumerate(cs)])
    est = audio_hits.estimate_lag(on, gt, oz); lag, frac = est.lag_s, est.match_rate
    hit_ev, rnd_ev, near_ev, mz, uz = [], [], [], [], []
    rng = np.random.default_rng(1)
    for c in cs:
        cur = curve(c)
        ev = audio_hits.frame_evidence(cur, c.pts, lag, 1.0 / c.fps)
        hf = np.searchsorted(c.pts, c.hits_t)
        hit_ev += list(ev[hf])
        far = np.ones(len(c.pts), bool)
        for f in hf: far[max(0, f - 6):f + 7] = False      # >= 0.2 s from any contact
        rnd_ev += list(ev[far])
        ot, oz = audio_hits.onsets(cur, 3.0)
        vt = ot - lag
        d = np.min(np.abs(vt[:, None] - c.hits_t[None]), axis=1) if len(c.hits_t) else np.full(len(vt), 9)
        mz += list(oz[d <= 2 / 30]); uz += list(oz[(d > 2 / 30) & in_windows(vt, c.windows)])
    hit_ev, rnd_ev = np.array(hit_ev), np.array(rnd_ev)
    q = lambda a: np.percentile(a, [10, 25, 50, 75, 90]).round(1).tolist()
    print(f"{venue}: lag {1e3*lag:.0f} ms  match {frac:.2f}")
    print("   evidence at contacts  pct10/25/50/75/90:", q(hit_ev))
    print("   evidence elsewhere    pct10/25/50/75/90:", q(rnd_ev))
    for thr in (4, 6, 8, 12, 16, 24):
        tpr = np.mean(hit_ev >= thr); fpr = np.mean(rnd_ev >= thr)
        print(f"   A>={thr:2d}: contacts {tpr:.2f}  other frames {fpr:.3f}  LR {tpr / max(fpr, 1e-3):.1f}")
    print("   onset z matched med", np.median(mz).round(1), " unmatched med", np.median(uz).round(1), " n", len(mz), len(uz))
