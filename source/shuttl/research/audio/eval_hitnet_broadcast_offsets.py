"""Offset between FineBadminton `start_frame` labels and detected contacts; re-score at the median.

Usage: python eval_hitnet_broadcast_offsets.py results_hitnet_v2_fineb.json
"""
import collections, json, sys
import numpy as np

rep = json.load(open(sys.argv[1]))
vids = [v for v in rep if v != 'pooled']


def match(det, gt, tol):
    cand = sorted((abs(a - b), i, j) for i, a in enumerate(det) for j, b in enumerate(gt) if abs(a - b) <= tol)
    ud, ug, pairs = set(), set(), []
    for _, i, j in cand:
        if i not in ud and j not in ug:
            ud.add(i); ug.add(j); pairs.append((i, j))
    return pairs


hist = {k: collections.Counter() for k in ('rules_or_pipeline', 'hitnet')}
for v in vids:
    gt = rep[v]['labels']
    for k in hist:
        det = rep[v][k]['frames']
        for i, j in match(det, gt, 40):
            hist[k][det[i] - gt[j]] += 1
for k, h in hist.items():
    top = h.most_common(6)
    print(k, 'det − label, top offsets:', top, ' n', sum(h.values()))
    arr = np.repeat(list(h.keys()), list(h.values()))
    print('   median %.1f  IQR %s' % (np.median(arr), np.percentile(arr, [25, 75])))
shift = int(round(np.median(np.repeat(list(hist['rules_or_pipeline'].keys()), list(hist['rules_or_pipeline'].values())))))
print('\nre-score with labels shifted by %+d frames (diagnostic only):' % shift)
tot = collections.defaultdict(lambda: [0, 0, 0])
for v in vids:
    gt = [g + shift for g in rep[v]['labels']]
    row = []
    for k in ('rules_or_pipeline', 'hitnet', 'hitnet_no_foot', 'hitnet_audio'):
        det = rep[v][k]['frames']
        tp = len(match(det, gt, 2))
        t = tot[k]; t[0] += tp; t[1] += len(det); t[2] += len(gt)
        p, r = tp / max(1, len(det)), tp / max(1, len(gt))
        row.append(f"{k} F1 {2 * p * r / max(1e-9, p + r):.3f}")
    print(v, rep[v].get('hitnet_audio', {}).get('gate'), '|', ' | '.join(row))
for k, (tp, nd, ng) in tot.items():
    p, r = tp / max(1, nd), tp / max(1, ng)
    print('pooled', k.ljust(18), 'P %.3f R %.3f F1 %.3f (%d/%d/%d)' % (p, r, 2 * p * r / max(1e-9, p + r), tp, nd, ng))
