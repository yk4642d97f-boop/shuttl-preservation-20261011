"""Label-semantics check: what does the pro-only control ensemble (never trained on
public clips) predict for each VideoBadminton class as mapped on 2026-11-17?"""
import json, numpy as np, torch
import bstlib as bo
T = bo.TYPES
nets = [bo.load_net(bo.PREV / 'selected' / f'control-member-{i}.pt') for i in range(10)]
rel = [bo.load_net(p) for p in bo.released_paths()]
for split in ('train', 'development', 'holdout'):
    arrays, truth, groups, ids = bo.load_public(split)
    for name, ens, zero in (('control', nets, False),):
        lg = bo.logits_of(ens, arrays)
        p = torch.softmax(lg, 1); p12 = (p[:, 1:13] + p[:, 13:25]).numpy()
        pred = p12.argmax(1)
        print(f'== {split} / {name}  (rows: yesterday label; cols: predicted type share)')
        for c in np.unique(truth):
            m = truth == c; cnt = np.bincount(pred[m], minlength=12)
            top = ', '.join(f'{T[i]} {cnt[i]/m.sum():.2f}' for i in np.argsort(-cnt)[:4] if cnt[i])
            print(f'  {T[c]:<12} n={m.sum():<4} -> {top}')
