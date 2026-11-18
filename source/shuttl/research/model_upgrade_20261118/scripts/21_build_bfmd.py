"""Assemble hit-centred BST inputs for BFMD (12 full professional matches, manual hit frames and types).

Court positions come from the dataset's static court corners (homography to the unit court, the
same normalisation as production). Hitter side is inferred as for VideoBadminton: three cues per
stroke under the constraint that players alternate inside a rally. Source classes that cover two
BST types are kept as a set of allowed types rather than forced to one.
"""
import collections, json, sys
from pathlib import Path
import cv2, numpy as np, torch
import vblib as vb
import bstlib as bo
from app.services.tracking import bst, players

root = Path('/dev/shm/claude/bfmd'); here = Path('/root/shuttl-claude-20261118')
T = vb.TYPES
MAP = {'serve': ['short_serve'], 'flick_serve': ['long_serve'], 'net_shot': ['net', 'cross_net'], 'lift': ['lift'], 'smash': ['smash'],
       'block': ['block'], 'drive': ['drive'], 'push': ['push'], 'drop': ['drop'], 'clear': ['clear'], 'net_kill': ['kill'], 'press': []}
SPLIT = lambda m: 'test' if 'All-England' in m else ('dev' if 'Shi-Yu-Qi-CHN-3-vs.-Wang-Zheng-Xing' in m else 'train')
matches = json.loads((here / 'bfmd_segments.json').read_text())
rows = []; feats = {}; missing = 0
for m in matches:
    c = m['court']
    Hm = cv2.getPerspectiveTransform(np.float32([c['top_left'], c['top_right'], c['bottom_right'], c['bottom_left']]), np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]))
    for sg in m['segments']:
        f = root / 'feat' / (sg['id'] + '.npz')
        if not f.exists(): missing += 1; continue
        z = dict(np.load(f)); n = len(z['covered'])
        pos = np.zeros((n, 2, 2), np.float32)
        for p in (0, 1):
            ok = np.isfinite(z['box'][:, p]).all(-1) & np.isfinite(z['kp'][:, p]).all((-1, -2)) & z['joints'][:, p].any((-1, -2))
            if ok.any():
                foot, _ = players.foot_pixels(z['box'][ok, p].astype(float), z['kp'][ok, p].astype(float))
                pos[ok, p] = cv2.perspectiveTransform(foot[None].astype(np.float32), Hm)[0]
        z['pos'] = pos; feats[sg['id']] = z
        hits = [h['frame'] for h in sg['hits']]
        for k, h in enumerate(sg['hits']):
            allowed = sorted({t for x in h['types'] for t in MAP[x]})
            prox, swing = vb.side_cues(z, h['frame'])
            rows.append(dict(seg=sg['id'], k=k, h=h['frame'], prox=prox, swing=swing, sgn=1.0 if k % 2 == 0 else -1.0, types=h['types'], allowed=allowed,
                             match=m['match'], split=SPLIT(m['match']), nclips=len(hits)))
print('segments missing', missing, 'strokes', len(rows))
built = []
for r in rows:
    z = feats[r['seg']]; half = 15; a, b = max(0, r['h'] - half), min(len(z['covered']), r['h'] + half + 1); pad = max(0, half - r['h'])
    j, s, p = z['joints'][a:b], z['shuttle'][a:b], z['pos'][a:b]
    if pad:
        j = np.concatenate((np.zeros((pad,) + j.shape[1:], j.dtype), j)); s = np.concatenate((np.zeros((pad, 2), s.dtype), s)); p = np.concatenate((np.zeros((pad, 2, 2), p.dtype), p))
    jnb, sh, pp, length = bst.model_inputs([(j, p, s)])
    cov = z['covered'][a:b]; res = z['resolved'][a:b]
    built.append((jnb[0], sh[0], pp[0], int(length[0]), bool(cov.all() and res[:30].any())))
arr = [torch.from_numpy(np.stack([x[c] for x in built])) for c in range(3)] + [torch.tensor([x[3] for x in built])]
nets = [bo.load_net(bo.PREV / 'selected' / f'control-member-{i}.pt') for i in range(10)]
lg = bo.logits_of(nets, arr); del nets
margin = (torch.logsumexp(lg[:, 13:25], 1) - torch.logsumexp(lg[:, 1:13], 1)).numpy()
for r, m in zip(rows, margin): r['bst'] = 0.0 if abs(m) < 1.0 else float(np.sign(m))
CUES = ('prox', 'swing', 'bst')


def consensus(use):
    sc = collections.defaultdict(float)
    for r in rows: sc[r['seg']] += sum(r[c] for c in use) * r['sgn']
    return sc


print('cue validation (each cue against the alternation-constrained consensus of the OTHER two, rallies of >=3 strokes):')
for c in CUES:
    sc = consensus([x for x in CUES if x != c])
    sub = [(r[c] > 0) == ((sc[r['seg']] > 0) == (r['sgn'] > 0)) for r in rows if r['nclips'] >= 3 and r[c] != 0 and sc[r['seg']] != 0]
    print('  %-5s agrees %.4f over %d strokes' % (c, np.mean(sub), len(sub)))
sc = consensus(CUES)
for r in rows:
    v = sc[r['seg']]; r['side'] = -1 if abs(v) < 1 else int((v > 0) == (r['sgn'] > 0))
print('side decided for %d of %d strokes' % (sum(r['side'] >= 0 for r in rows), len(rows)))
# position sanity: far player should sit in the far half (v<0.5), near player in the near half
P = arr[2].numpy(); far = P[:, :, 0, 1][P[:, :, 0].any(-1)]; near = P[:, :, 1, 1][P[:, :, 1].any(-1)]
print('court depth of far player median %.3f (in [0,.5]: %.3f) / near player median %.3f (in [.5,1]: %.3f)' % (
    np.median(far), ((far >= -.05) & (far <= .55)).mean(), np.median(near), ((near >= .45) & (near <= 1.05)).mean()))
tz = np.load(bo.FIXED / 'train.npz')['pos']; print('ShuttleSet reference: far median %.3f near median %.3f' % (np.median(tz[:, :, 0, 1][tz[:, :, 0].any(-1)]), np.median(tz[:, :, 1, 1][tz[:, :, 1].any(-1)])))
out = collections.defaultdict(lambda: collections.defaultdict(list))
for r, (jnb, sh, pp, length, gate) in zip(rows, built):
    o = out[r['split']]; al = np.zeros(25, bool)
    for t in r['allowed']:
        i = T.index(t)
        if r['side'] != 1: al[1 + i] = True
        if r['side'] != 0: al[13 + i] = True
    o['jnb'].append(jnb); o['shuttle'].append(sh); o['pos'].append(pp); o['length'].append(length); o['allowed'].append(al)
    o['type'].append(T.index(r['allowed'][0]) if len(r['allowed']) == 1 else -1); o['side'].append(r['side']); o['gate_prod'].append(gate)
    o['label'].append(1 + T.index(r['allowed'][0]) + 12 * r['side'] if len(r['allowed']) == 1 and r['side'] >= 0 else -1)
    o['match'].append(r['match']); o['seg'].append(r['seg']); o['k'].append(r['k']); o['source_type'].append('+'.join(r['types']))
for split, o in sorted(out.items()):
    arrays = {k: (np.stack(v) if k in ('jnb', 'shuttle', 'pos', 'allowed') else np.array(v)) for k, v in o.items()}
    np.savez_compressed(here / 'data' / f'bfmd_{split}.npz', **arrays)
    print(split, 'n', len(arrays['side']), 'supervised', int(arrays['allowed'].any(1).sum()), 'gate', round(float(arrays['gate_prod'].mean()), 4), 'matches', len(set(arrays['match'])),
          dict(collections.Counter(arrays['source_type']).most_common(13)))
