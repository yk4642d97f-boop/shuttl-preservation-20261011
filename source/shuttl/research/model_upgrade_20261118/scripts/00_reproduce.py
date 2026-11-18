"""Reproduce yesterday's headline numbers to validate the rebuilt harness."""
import json, torch, numpy as np
import bstlib as bo
torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
vj, vs, vp, vl, vy = bo.load_split('val')
arms = {'released': bo.released_paths(),
        'control': [bo.PREV / 'selected' / f'control-member-{i}.pt' for i in range(10)],
        'aux': [bo.PREV / 'selected' / f'aux-member-{i}.pt' for i in range(10)]}
out = {}
for arm, files in arms.items():
    nets = [bo.load_net(f) for f in files]
    r = {'clean': bo.pro_metrics(bo.logits_of(nets, (vj, vs, vp, vl)), vy),
         'nopos': bo.pro_metrics(bo.logits_of(nets, (vj, vs, torch.zeros_like(vp), vl)), vy)}
    for name in ('development', 'holdout'):
        arrays, truth, groups, ids = bo.load_public(name)
        m = bo.clip_metrics(bo.type_prediction(bo.logits_of(nets, arrays).numpy()), truth)
        r[name] = {k: m[k] for k in ('n', 'accuracy', 'macro_recall', 'answered')}
    out[arm] = r
    print(arm, json.dumps(r), flush=True)
