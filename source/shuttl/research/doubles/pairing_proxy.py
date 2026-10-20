"""Does "singles model over partner pairings" hold up on amateur doubles? Proxy evidence from
kwyoke's released GRU (trained on pro singles) run by its authors over two pairings per
doubles clip (pair1/pair2 probabilities); we decode max-over-pairings exactly like
hitnet.HitNet.curves does. Labels are per clip; all clips with labels and probabilities."""
import collections, csv, glob, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'audio'))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '../../backend')))
from app.services.tracking.hit_fusion import decode_nms   # noqa: E402
from common import match, prf                              # noqa: E402
DATA = os.environ.get('AUDIO_STUDY_DATA', '/home/user/workspace/data')
KW = f'{DATA}/kwyoke'


def clips():
    for lab in sorted(glob.glob(f'{KW}/am_*/match_*/player_hit/*.mp4_player_hit.csv')):
        kind, m = lab.split('/')[-4], lab.split('/')[-3]
        base = os.path.basename(lab).split('.')[0]
        rows = list(csv.DictReader(open(lab)))
        hits = np.array([int(r['frame']) for r in rows if r['player_hit'] != '0'])
        files = sorted(glob.glob(f'{KW}/domain_probs/{kind}/{m}/{base}_pair*_probs.npy')) if kind == 'am_doubles' \
            else [f'{KW}/domain_probs/{kind}/{m}/{base}_probs.npy']
        files = [f for f in files if os.path.exists(f)]
        if files:
            yield kind, m, base, len(rows), hits, [1 - np.load(f)[:, 0] for f in files]


def f1_for(items, shift, thr, single_pair=False):
    tot = collections.Counter()
    for kind, m, base, n, hits, curves in items:
        ph = curves[0] if single_pair else np.max(curves, axis=0)
        p = np.zeros(n, np.float32)
        idx = np.arange(len(ph)) + shift
        ok = (idx >= 0) & (idx < n)
        p[idx[ok]] = ph[ok]
        det = np.asarray(decode_nms(p, 30.0, thr, 0.3), float)
        tp, fp, fn, _ = match(det, hits.astype(float), 2 + 1e-6)
        tot.update(tp=tp, fp=fp, fn=fn)
    return prf(tot['tp'], tot['fp'], tot['fn']), tot


items = list(clips())
grid = [(s, t) for s in range(9, 14) for t in (.3, .5, .7, .9, .97)]
best = max(grid, key=lambda q: f1_for(items, *q)[0][2])
out = {'common_operating_point': dict(shift=best[0], thr=best[1])}
for kind in ('am_singles', 'am_doubles'):
    sub = [i for i in items if i[0] == kind]
    (p, r, f), tot = f1_for(sub, *best)
    out[kind] = dict(clips=len(sub), hits=int(sum(len(i[4]) for i in sub)), P=round(p, 3), R=round(r, 3), F1=round(f, 3))
    if kind == 'am_doubles':
        (p1, r1, f1), _ = f1_for(sub, *best, single_pair=True)
        out['am_doubles_first_pairing_only'] = dict(P=round(p1, 3), R=round(r1, 3), F1=round(f1, 3))
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, 'results_pairing_proxy.json'), 'w'), indent=1)
