"""Confusion matrix of one ensemble on a VideoBadminton split (rows: truth, cols: prediction)."""
import sys, numpy as np, torch
import bstlib as bo
from importlib import import_module
ev = import_module('40_eval')
spec, split = sys.argv[1], sys.argv[2]
nets = [bo.load_net(p) for p in ev.paths(spec)]
z = np.load(ev.DATA / f'vb_hit_{split}.npz', allow_pickle=False)
lg = bo.logits_of(nets, [torch.from_numpy(z[k]) for k in ('jnb', 'shuttle', 'pos', 'length')]).numpy()
pred = bo.type_prediction(lg); truth = z['type']; T = bo.TYPES; kk = truth >= 0; z = {k: z[k][kk] for k in z.files}; pred = pred[kk]; truth = truth[kk]
print(spec, split, 'acc %.4f' % (pred == truth).mean(), 'n', len(truth))
print(' ' * 12 + ' '.join(t[:5].rjust(5) for t in T) + '   abst  recall')
for c in range(12):
    m = truth == c
    if not m.any(): continue
    row = [int(((pred == k) & m).sum()) for k in range(12)]
    print(T[c].ljust(12) + ' '.join(str(v).rjust(5) for v in row) + str(int(((pred < 0) & m).sum())).rjust(7) + '  %.3f' % ((pred == c) & m).sum().__truediv__(m.sum()))
# by raw source class
raw = z['raw_class']
print('by source class:')
for rc in sorted(set(raw)):
    m = raw == rc; print('  %-26s n=%-4d recall %.3f  top pred: %s' % (rc, m.sum(), (pred[m] == truth[m]).mean(), ', '.join(f'{T[i]} {c}' for i, c in sorted(enumerate(np.bincount(pred[m][pred[m] >= 0], minlength=12)), key=lambda x: -x[1])[:3])))
# by position in rally and padding
for name, m in (('first stroke of segment (no pre-contact frames)', z['k'] == 0), ('later strokes', z['k'] > 0), ('side known', z['side'] >= 0), ('side unknown', z['side'] < 0)):
    if m.any(): print('  %-48s n=%-5d acc %.4f' % (name, m.sum(), (pred[m] == truth[m]).mean()))
