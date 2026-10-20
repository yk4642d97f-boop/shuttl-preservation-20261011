"""Visual detector alone vs + audio, on amateur rallies with audio (leave-one-venue-out).

Visual curve: kwyoke's released GRU "domain" model (14-frame windows, 3 classes; doubles =
max over its two player pairings) — a stand-in for HitNet, whose weights are encrypted.
Protocol: the visual (shift, threshold) is tuned on the two other venues and shared by every
variant; fusion parameters are the shipped FusionParams defaults, never tuned here (only one
venue passes the gate, so they cannot be tuned honestly). Lag anchors:
  hitnet_sim  labels degraded with HitNet's measured offset spread, 10% missed, 10% spurious
  labels      clean labels (oracle)
  visual      the proxy's own confident detections (its timing is too coarse — reported only)
Gate = production rule (anchors >= min_anchors, lag-peak excess >= min_excess).
"""
import collections, dataclasses, functools, json, os, sys, numpy as np
from common import audio_hits, data, curve, match, prf
from app.services.tracking import hit_fusion

KW = os.path.join(data.DATA, 'kwyoke', 'domain_probs')
P = hit_fusion.FusionParams()
OFF = np.array([0, 1, -1, 2, -2, 3]); W = np.array([2032, 1390, 430, 309, 100, 59], float); W /= W.sum()
clips = [c for c in data.all_clips() if c.kind == 'amateur']
CLIPS = {c.name: c for c in clips}
venues = sorted({c.group for c in clips})


@functools.lru_cache(maxsize=None)
def visual(name, shift):
    c = CLIPS[name]
    parts = c.name.split('_')                          # kw_am_doubles_match_china_doubles0
    kind, mdir, base = '_'.join(parts[1:3]), '_'.join(parts[3:5]), parts[5]
    files = [f'{KW}/{kind}/{mdir}/{base}_probs.npy'] if kind == 'am_singles' else \
            [f'{KW}/{kind}/{mdir}/{base}_pair{k}_probs.npy' for k in (1, 2)]
    ph = np.max([1 - np.load(f)[:, 0] for f in files], axis=0)
    p = np.zeros(len(c.pts), np.float32)
    idx = np.arange(len(ph)) + shift
    ok = (idx >= 0) & (idx < len(p))
    p[idx[ok]] = ph[ok]
    return p


@functools.lru_cache(maxsize=None)
def onsets(name, z):
    return audio_hits.onsets(curve(CLIPS[name]), z)


def anchors(c, k, source, shift):
    if source == 'labels':
        return c.hits_t
    if source == 'hitnet_sim':
        rng = np.random.default_rng(1000 + k)
        keep = c.hits_t[rng.random(len(c.hits_t)) > 0.10]
        fp = rng.random(int(round(0.1 * len(c.hits_t)))) * c.pts[-1]
        return np.concatenate([keep + rng.choice(OFF, len(keep), p=W) / c.fps, fp])
    fr = hit_fusion.decode_nms(visual(c.name, shift), c.fps, P.anchor_p, 0.3)
    return c.pts[fr]


def gate(venue, source, shift, min_anchors):
    cs = [c for c in clips if c.group == venue]
    on = np.concatenate([onsets(c.name, P.onset_z)[0] + 1000 * k for k, c in enumerate(cs)])
    oz = np.concatenate([onsets(c.name, P.onset_z)[1] for c in cs])
    an = np.concatenate([anchors(c, k, source, shift) + 1000 * k for k, c in enumerate(cs)])
    est = audio_hits.estimate_lag(on, an, oz, max_lag_s=P.max_lag_s)
    used = est.excess >= P.min_excess and est.anchors >= min_anchors
    return hit_fusion.AudioGate(used, 'ok' if used else ('too_few_anchors' if est.anchors < min_anchors else 'audio_not_informative'),
                                est.lag_s, est.excess, est.match_rate, est.anchors)


def run(cs, shift, thr, variant, gates, params=P):
    t2, t1 = collections.Counter(), collections.Counter()
    for c in cs:
        p = visual(c.name, shift)
        g = gates.get(c.group) if gates else None
        if variant == 'visual' or g is None or not g.used:
            frames = hit_fusion.decode_nms(p, c.fps, thr, 0.3)
        elif variant == 'snap':
            frames = hit_fusion.decode_nms(p, c.fps, thr, 0.3)
            ot, oz = onsets(c.name, params.z_snap)
            frames = hit_fusion.snap_frames(frames, c.pts, ot, oz, g.lag_s, params.max_shift_frames / c.fps,
                                            priority=p[frames] if len(frames) else None).tolist()
        else:  # 'fused' = shipped fuse_and_decode with a precomputed gate
            frames, _, _ = hit_fusion.fuse_and_decode(p, c.pts, c.fps, curve(c), thr=thr, gap_s=0.3,
                                                      params=params if variant == 'fused' else dataclasses.replace(params, z_snap=None),
                                                      gate=g)
        t = c.pts[np.asarray(frames, int)] if len(frames) else np.zeros(0)
        a, b, d, _ = match(t, c.hits_t, 2 / c.fps + 1e-6); t2.update(tp=a, fp=b, fn=d)
        a, b, d, _ = match(t, c.hits_t, 1 / c.fps + 1e-6); t1.update(tp=a, fp=b, fn=d)
    return t2, t1


def f1(c):
    return prf(c['tp'], c['fp'], c['fn'])


if __name__ == '__main__':
    min_anchors = int(os.environ.get('MIN_ANCHORS', P.min_anchors))
    report = {'fusion_params': dataclasses.asdict(P), 'min_anchors': min_anchors, 'by_source': {}}
    VARIANTS = ('visual', 'fused_no_snap', 'snap', 'fused')
    for source in ('hitnet_sim', 'labels', 'visual'):
        pooled = {v: [collections.Counter(), collections.Counter()] for v in VARIANTS}
        folds = {}
        for held in venues:
            train = [c for c in clips if c.group != held]; test = [c for c in clips if c.group == held]
            shift, thr = max(((s, t) for s in range(9, 14) for t in (.3, .5, .7, .9, .97)),
                             key=lambda q: f1(run(train, q[0], q[1], 'visual', None)[0])[2])
            g = {held: gate(held, source, shift, min_anchors)}
            row = {'shift': shift, 'thr': thr, 'gate': g[held].as_dict()}
            for v in VARIANTS:
                t2, t1 = run(test, shift, thr, v, g)
                pooled[v][0].update(t2); pooled[v][1].update(t1)
                row[v] = dict(P=round(f1(t2)[0], 3), R=round(f1(t2)[1], 3), F1_2=round(f1(t2)[2], 3), F1_1=round(f1(t1)[2], 3))
            folds[held] = row
        pooled_rows = {v: dict(P=round(f1(a)[0], 3), R=round(f1(a)[1], 3), F1_2=round(f1(a)[2], 3), F1_1=round(f1(b)[2], 3), **a)
                       for v, (a, b) in pooled.items()}
        report['by_source'][source] = {'folds': folds, 'pooled': pooled_rows}
        print(f'== lag anchors: {source}')
        for held, row in folds.items():
            print(f"  {held:18s} gate {row['gate']}")
            print('     ' + '  '.join(f"{v}: F1@2 {row[v]['F1_2']:.3f} F1@1 {row[v]['F1_1']:.3f}" for v in VARIANTS))
        print('  pooled ' + '  '.join(f"{v}: P {r['P']:.3f} R {r['R']:.3f} F1@2 {r['F1_2']:.3f} F1@1 {r['F1_1']:.3f}" for v, r in pooled_rows.items()), flush=True)
    # sensitivity of the fused variant to (beta, penalty, z_snap) on venues that pass the gate (oracle lag)
    sens = {}
    for beta in (1.0, 2.0, 3.0):
        for pen in (0.0, 0.5, 1.0):
            for zs in (None, 6.0):
                q = dataclasses.replace(P, beta=beta, penalty=pen, z_snap=zs)
                tot2, tot1 = collections.Counter(), collections.Counter()
                for held in venues:
                    fold = report['by_source']['labels']['folds'][held]
                    g = {held: gate(held, 'labels', fold['shift'], min_anchors)}
                    if not g[held].used:
                        continue
                    a, b = run([c for c in clips if c.group == held], fold['shift'], fold['thr'], 'fused', g, q)
                    tot2.update(a); tot1.update(b)
                sens[f'beta={beta},penalty={pen},z_snap={zs}'] = (round(f1(tot2)[2], 3), round(f1(tot1)[2], 3))
    report['sensitivity_gated_venues_oracle_lag'] = sens
    print('sensitivity (gated venues, oracle lag) F1@2, F1@1:', sens)
    json.dump(report, open(f'results_fusion_proxy_min{min_anchors}.json', 'w'), indent=1, default=str)
