"""Assemble hit-centred BST inputs for every VideoBadminton stroke from rally features.

Hitter side (far/near) is not in the dataset. It is inferred without human labels from three
cues per stroke (shuttle-to-player proximity at the hit, which player's wrist is swinging, and
the side predicted by the professional-only BST ensemble) combined under the hard structural
constraint that the two players alternate inside a rally. Each cue is validated against the
consensus of the other two before use.
"""
import collections, json
from pathlib import Path
import numpy as np, torch
import vblib as vb
import bstlib as bo

root = Path('/dev/shm/claude/vbr'); here = Path('/root/shuttl-claude-20261118')
segs = json.loads((here / 'vb_segments.json').read_text())
rows = []; missing = 0; feats = {}
for s in segs:
    f = root / 'feat' / (s['id'] + '.npz')
    if not f.exists(): missing += 1; continue
    z = dict(np.load(f)); feats[s['id']] = z
    hits = list(z['hits']) + [len(z['covered'])]
    for k, c in enumerate(s['clips']):
        prox, swing = vb.side_cues(z, hits[k])
        rows.append(dict(seg=s['id'], k=k, h=int(hits[k]), nxt=int(hits[k + 1]), prox=prox, swing=swing, sgn=1.0 if c['player'] == 'A' else -1.0,
                         fps=float(z['meta'][0]), **{x: c[x] for x in ('id', 'raw_class', 'player')},
                         recording=s['recording'], session=s['session'], date=s['date'], nclips=len(s['clips'])))
print('segments missing', missing, 'strokes', len(rows))
# Sessions annotated with a five-word vocabulary (serves, Clear, Smash, Flat Shot): there "Flat Shot" is a catch-all
# (its flight lasts 32 frames at the median, like net shots and lifts; a real flat drive lasts 19) and no fine class occurs.
FINE = {'02_Lift', '05_Drop Shot', '08_Cut', '04_Block', '06_Push Shot', '01_Cross Court Flight', '07_Transitional Slice'}
per = collections.defaultdict(collections.Counter)
for r in rows: per[r['session']][r['raw_class']] += 1
COARSE = {s for s, c in per.items() if sum(c.values()) >= 40 and sum(c[k] for k in FINE) / sum(c.values()) < .05 and not s.startswith('2023')}
COARSE_SET = {'15_Flat Shot': ['net', 'block', 'lift', 'drive', 'push', 'cross_net', 'drop', 'kill'], '17_Short Flat Shot': ['net', 'block', 'lift', 'drive', 'push', 'cross_net', 'drop', 'kill'],
              '12_Clear': ['clear', 'lift'], '14_Smash': ['smash', 'drop']}
print('coarse-vocabulary sessions', len(COARSE), sorted(COARSE), 'strokes', sum(r['session'] in COARSE for r in rows))

built = {}
for style in ('hit', 'clip'):
    for i, r in enumerate(rows):
        z = feats[r['seg']]
        if style == 'hit':
            j, s, info = vb.window(z, r['h'], r['fps'], center=True)
        else:                                # 2026-11-17 style: the whole author clip [hit_k, hit_k+1)
            j, s = z['joints'][r['h']:r['nxt']], z['shuttle'][r['h']:r['nxt']]
            cov = z['covered'][r['h']:r['nxt']]; res = z['resolved'][r['h']:r['nxt']]
            info = dict(pad=0, covered_all=bool(cov.all()), resolved_any=bool(res[:30].any()), resolved_frac=float(res.mean()), covered_frac=float(cov.mean()))
        built[(style, i)] = (vb.to_model(j, s), info)

# cue 3: side predicted by the professional-only ensemble (never trained on these clips)
nets = [bo.load_net(bo.PREV / 'selected' / f'control-member-{i}.pt') for i in range(10)]
arr = [torch.from_numpy(np.stack([built[('hit', i)][0][c] for i in range(len(rows))])) for c in range(3)] + [torch.tensor([built[('hit', i)][0][3] for i in range(len(rows))])]
lg = bo.logits_of(nets, arr)
margin = (torch.logsumexp(lg[:, 13:25], 1) - torch.logsumexp(lg[:, 1:13], 1)).numpy()
for r, m in zip(rows, margin): r['bst'] = 0.0 if abs(m) < 1.0 else float(np.sign(m))
del nets

CUES = ('prox', 'swing', 'bst')


def consensus(use):
    sc = collections.defaultdict(float)
    for r in rows: sc[r['seg']] += sum(r[c] for c in use) * r['sgn']
    return sc


print('cue validation on rallies of >=3 strokes (each cue against the alternation-constrained consensus of the OTHER two):')
for c in CUES:
    sc = consensus([x for x in CUES if x != c])
    sub = [(r[c] > 0) == ((sc[r['seg']] > 0) == (r['sgn'] > 0)) for r in rows if r['nclips'] >= 3 and r[c] != 0 and sc[r['seg']] != 0]
    print('  %-5s agrees %.4f over %d strokes (cue silent on %.1f%% of strokes)' % (c, np.mean(sub), len(sub), 100 * np.mean([r[c] == 0 for r in rows])))
sc = consensus(CUES)
for r in rows:
    v = sc[r['seg']]; r['side'] = -1 if abs(v) < 1 else int((v > 0) == (r['sgn'] > 0)); r['side_margin'] = abs(v) / r['nclips']
print('side decided for %d of %d strokes; single-stroke segments decided %d of %d' % (
    sum(r['side'] >= 0 for r in rows), len(rows), sum(r['side'] >= 0 and r['nclips'] == 1 for r in rows), sum(r['nclips'] == 1 for r in rows)))

out = collections.defaultdict(lambda: collections.defaultdict(list))
for (style, i), ((jnb, sh, pos, length), info) in built.items():
    r = rows[i]; side = r['side']
    t = vb.TYPES.index(vb.MAP18[r['raw_class']]); old = vb.TYPES.index(vb.OLD8[r['raw_class']]) if r['raw_class'] in vb.OLD8 else -1
    al = np.zeros(12, bool); al[t] = True; coarse = r['session'] in COARSE
    if coarse and r['raw_class'] in COARSE_SET:
        al[:] = False; al[[vb.TYPES.index(x) for x in COARSE_SET[r['raw_class']]]] = True; t = -1
    elif coarse and 'Serve' not in r['raw_class']: al[:] = False; t = -1
    o = out[(style, vb.SPLIT[r['date']])]
    o['jnb'].append(jnb); o['shuttle'].append(sh); o['pos'].append(pos); o['length'].append(length)
    o['type'].append(t); o['old_type'].append(old); o['side'].append(side); o['label'].append(1 + t + 12 * side if side >= 0 and t >= 0 else -1)
    o['allowed12'].append(al); o['coarse'].append(coarse)
    o['id'].append(r['id']); o['seg'].append(r['seg']); o['recording'].append(r['recording']); o['session'].append(r['session'])
    o['raw_class'].append(r['raw_class']); o['k'].append(r['k']); o['pad'].append(info['pad']); o['nclips'].append(r['nclips'])
    o['gate_prod'].append(info['covered_all'] and info['resolved_any']); o['gate_strict'].append(info['covered_all'] and info['resolved_frac'] >= .9)
    o['resolved_frac'].append(info['resolved_frac']); o['covered_frac'].append(info['covered_frac'])
dst = here / 'data'; dst.mkdir(exist_ok=True); report = {}
for (style, split), o in sorted(out.items()):
    arrays = {k: (np.stack(v) if k in ('jnb', 'shuttle', 'pos', 'allowed12') else np.array(v)) for k, v in o.items()}
    np.savez_compressed(dst / f'vb_{style}_{split}.npz', **arrays)
    report[f'{style}/{split}'] = dict(n=len(arrays['type']), gate_prod=float(arrays['gate_prod'].mean()), gate_strict=float(arrays['gate_strict'].mean()),
                                      types={vb.TYPES[i]: int(c) for i, c in enumerate(np.bincount(arrays['type'][arrays['type'] >= 0], minlength=12))}, typed=int((arrays['type'] >= 0).sum()),
                                      near_share=float((arrays['side'] == 1).mean()), side_known=float((arrays['side'] >= 0).mean()), sessions=len(set(arrays['session'])))
    if style == 'hit': print(split, json.dumps(report[f'{style}/{split}']))
(dst / 'vb_build_report.json').write_text(json.dumps(dict(report=report, strokes=len(rows), side_decided=int(sum(r['side'] >= 0 for r in rows))), indent=1))
