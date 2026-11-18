"""Rally-grammar decoding on top of BST: an HMM whose emissions are the ensemble's class probabilities and
whose transitions come from public stroke-sequence labels (ShuttleSet22, no video). States are
(hitter side, type); the hitter alternates. Max-posterior decoding per stroke.
Usage: 45_rally_decode.py [--final] ARM=SPEC ...     (prior strength is chosen on development data)"""
import json, sys, numpy as np, torch
import bstlib as bo
from importlib import import_module
ev = import_module('40_eval')
prior = json.loads((bo.Path('/root/shuttl-claude-20261118/rally_prior_ss22.json')).read_text())
B = np.array(prior['bigram'], float) + 1.0; TT = B / B.sum(1, keepdims=True)
PI = np.array(prior['init'], float) + 1e-3; PI /= PI.sum()
MARG = B.sum(0) / B.sum()


def decode(p25, first_is_start, lam, rho, flip=.98):
    """p25 (K,25) probabilities of one rally in order. Returns predicted type per stroke (0..11)."""
    K = len(p25); e = np.concatenate((p25[:, 1:13], p25[:, 13:25]), 1) + 1e-9      # (K,24) far types, near types
    A = np.zeros((24, 24))
    for s in (0, 1):
        for s2 in (0, 1): A[s * 12:(s + 1) * 12, s2 * 12:(s2 + 1) * 12] = (TT ** lam) * (flip if s != s2 else 1 - flip)
    start = (rho * PI + (1 - rho) * MARG) ** lam if first_is_start else np.ones(12)
    f = np.zeros((K, 24)); b = np.ones((K, 24))
    f[0] = e[0] * np.tile(start, 2); f[0] /= f[0].sum()
    for k in range(1, K): f[k] = e[k] * (f[k - 1] @ A); f[k] /= f[k].sum()
    for k in range(K - 2, -1, -1): b[k] = A @ (e[k + 1] * b[k + 1]); b[k] /= b[k].sum()
    post = f * b; return (post[:, :12] + post[:, 12:]).argmax(1)


def sequences(name, final):
    out = {}
    vj, vs, vp, vl, vy = bo.load_split('val'); names = bo.split_names('val')
    keys = np.array(['/'.join(n.split('/')[:3]) for n in names]); frames = np.array([int(n.split('/')[3]) for n in names])
    seqs = []
    for k in np.unique(keys):
        idx = np.flatnonzero(keys == k); idx = idx[np.argsort(frames[idx])]; cur = [idx[0]]
        for a, b in zip(idx, idx[1:]):
            if frames[b] - frames[a] > 75: seqs.append(cur); cur = [b]       # a missing stroke in between: restart the chain
            else: cur.append(b)
        seqs.append(cur)
    out['pro_val'] = ([vj, vs, vp, vl], ((vy - 1) % 12).numpy(), seqs)
    out['pro_val_nopos'] = ([vj, vs, torch.zeros_like(vp), vl], ((vy - 1) % 12).numpy(), seqs)
    for split in ['development'] + (['holdout', 'holdout2'] if final else []):
        z = np.load(ev.DATA / f'vb_hit_{split}.npz', allow_pickle=False); seg = z['seg']; k = z['k']; seqs = []
        for s in np.unique(seg):
            idx = np.flatnonzero(seg == s); seqs.append(list(idx[np.argsort(k[idx])]))
        out['vb_' + split] = ([torch.from_numpy(z[c]) for c in ('jnb', 'shuttle', 'pos', 'length')], z['type'], seqs)
    return out


final = '--final' in sys.argv; arms = [x for x in sys.argv[1:] if not x.startswith('--')]
fixed = [x.split('=')[1] for x in sys.argv if x.startswith('--lam=')]
data = sequences('x', final); report = {}
for arm in arms:
    name, _, spec = arm.partition('='); spec = spec or name
    nets = [bo.load_net(p) for p in ev.paths(spec)]; report[name] = {}
    probs = {k: torch.softmax(bo.logits_of(nets, arr), 1).numpy() for k, (arr, _, _) in data.items()}
    def acc(key, lam, rho):
        arr, truth, seqs = data[key]; pred = np.full(len(truth), -1)
        for s in seqs: pred[s] = decode(probs[key][s], True, lam, rho)
        return float((pred == truth)[truth >= 0].mean())
    base = {k: float((bo.type_prediction(np.log(probs[k])) == data[k][1])[data[k][1] >= 0].mean()) for k in data}
    grid = [(l, r) for l in (.25, .5, .75, 1.0) for r in (0., .5, .9)]
    if fixed: lam, rho = [float(v) for v in fixed[0].split(',')]
    else:
        score = {g: .5 * acc('vb_development', *g) + .25 * acc('pro_val', *g) + .25 * acc('pro_val_nopos', *g) for g in grid}
        lam, rho = max(score, key=score.get)
    line = f'{name:<16} prior strength {lam} start {rho} |'
    for k in data:
        d = acc(k, lam, rho); report[name][k] = dict(argmax=base[k], rally_decoded=d); line += f' {k} {base[k]:.4f}->{d:.4f}'
    report[name]['lam'] = lam; report[name]['rho'] = rho; print(line, flush=True)
out = [x.split('=', 1)[1] for x in sys.argv if x.startswith('--out=')]
if out: open(out[0], 'w').write(json.dumps(report, indent=1))
