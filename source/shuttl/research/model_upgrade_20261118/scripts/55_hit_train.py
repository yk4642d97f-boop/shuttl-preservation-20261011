"""Fine-tune HitNet (TCN, 51 features) on rally segments with dataset hit frames.

Sources: VideoBadminton amateur rallies (no camera, so no foot positions) and, when extracted,
BFMD professional rallies (foot positions from the published court corners, randomly dropped so
the model works with and without calibration). Starts from the released hitnet_single_v2 weights.
The decoder contract (threshold 0.4, 0.30 s gap) is unchanged. Selection uses development splits only.
"""
import argparse, json, time
from pathlib import Path
import numpy as np, torch
from torch import nn
import hitlib as hl
from app.services.tracking import hitnet_core as core

ap = argparse.ArgumentParser()
ap.add_argument('--name', required=True); ap.add_argument('--bfmd', type=int, default=0); ap.add_argument('--s041', type=int, default=0)
ap.add_argument('--epochs', type=int, default=60); ap.add_argument('--lr', type=float, default=5e-4); ap.add_argument('--seed', type=int, default=0)
ap.add_argument('--pose', type=int, default=0); ap.add_argument('--scratch', type=int, default=0); ap.add_argument('--pos-weight', type=float, default=4.0); ap.add_argument('--batch', type=int, default=64)
a = ap.parse_args()
torch.manual_seed(20261118 + a.seed); rng = np.random.default_rng(20261118 + a.seed)
out = Path('/dev/shm/claude/hitruns') / a.name; out.mkdir(parents=True, exist_ok=True)
segs = hl.load_vb(); sides = hl.vb_sides()
for s in segs: s['sides'] = sides.get(s['id'])
if a.bfmd: segs += hl.load_bfmd()
train = [s for s in segs if s['split'] == 'train']
dev = {'vb': [s for s in segs if s['domain'] == 'vb' and s['split'] == 'development'], 'bfmd': [s for s in segs if s['domain'] == 'bfmd' and s['split'] == 'dev']}
print('train segments', len(train), {d: sum(s['domain'] == d for s in train) for d in ('vb', 'bfmd')}, 'dev', {k: len(v) for k, v in dev.items()}, flush=True)
ck = torch.load(hl.HITNET, map_location='cpu', weights_only=True)
N_IN = 77 if a.pose else 51
net = core.HitTCN(N_IN, int(ck['hidden']))
if not a.scratch:
    state = dict(ck['state'])
    if a.pose:                                  # start as the released model: new pose channels enter with zero weight
        w = torch.zeros(state['inp.weight'].shape[0], N_IN, 1); w[:, :51] = state['inp.weight']; state['inp.weight'] = w
    net.load_state_dict(state)
net = net.cuda()
W = 384


def augment(raw):
    raw = raw.copy()
    if rng.random() < .5: raw[:, 12:] = np.nan              # no court calibration
    raw[:, :2] += rng.normal(0, .002, raw[:, :2].shape); raw[:, 4:12] += rng.normal(0, .002, raw[:, 4:12].shape)
    for _ in range(rng.integers(0, 3)):                     # shuttle track holes
        k = int(rng.integers(2, 9)); i = int(rng.integers(0, max(1, len(raw) - k)))
        raw[i:i + k, :3] = np.nan; raw[i:i + k, 3] = 0
    if rng.random() < .1: raw[:, 4 + 4 * int(rng.integers(0, 2)):][:, :4] = np.nan   # one player missing
    return raw


def batch_of(items, aug):
    X = np.zeros((len(items), W, N_IN), np.float32); Y = np.zeros((len(items), W), np.float32); M = np.zeros((len(items), W), np.float32)
    S = np.zeros((len(items), W), np.float32); SM = np.zeros((len(items), W), np.float32)
    for b, s in enumerate(items):
        n = len(s['raw']); a0 = int(rng.integers(0, n - W + 1)) if n > W else 0; e = min(n, a0 + W)
        sub = dict(s, raw=s['raw'][a0:e], kp=s['kp'][a0:e], box=s['box'][a0:e]); x = hl.features(sub, N_IN, augment(sub['raw']) if aug else None)
        X[b, :e - a0] = x; M[b, max(0, s.get('valid_from', 0) - a0):max(0, min(e, s['valid_to']) - a0)] = 1
        for k, h in enumerate(s['hits']):
            for d, v in ((0, 1.), (-1, .5), (1, .5)):
                t = h + d - a0
                if 0 <= t < e - a0:
                    Y[b, t] = max(Y[b, t], v)
                    if s['sides'] is not None and s['sides'][k] >= 0: S[b, t] = 1. - s['sides'][k]; SM[b, t] = 1   # target: hitter is far/Top
    return [torch.from_numpy(z).cuda() for z in (X, Y, M, S, SM)]


@torch.inference_mode()
def detect(model, items):
    model.eval(); res = {}
    for s in items:
        x = torch.from_numpy(hl.features(s, N_IN))[None].cuda()
        res[s['id']] = core.decode_nms(core.sigmoid(model(x)[0, :, 0].float().cpu().numpy()), s['fps'], .4, .3)
    return res


opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=.01)
steps = a.epochs * max(1, len(train) // a.batch); sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps, pct_start=.1)
bce = nn.BCEWithLogitsLoss(reduction='none', pos_weight=torch.tensor(a.pos_weight).cuda()); bce1 = nn.BCEWithLogitsLoss(reduction='none')
dom_w = np.array([1.0 if s['domain'] == 'vb' else 1.5 for s in train]); dom_w /= dom_w.sum()
best = None; log = []; began = time.time()
for epoch in range(a.epochs):
    net.train(); tot = 0.
    for _ in range(max(1, len(train) // a.batch)):
        X, Y, M, S, SM = batch_of([train[i] for i in rng.choice(len(train), a.batch, p=dom_w)], True)
        lg = net(X)
        loss = (bce(lg[..., 0], Y) * M).sum() / M.sum() + .5 * (bce1(lg[..., 1], S) * SM).sum() / SM.sum().clamp_min(1)
        opt.zero_grad(set_to_none=True); loss.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.); opt.step(); sched.step(); tot += float(loss.detach())
    row = dict(epoch=epoch + 1, loss=tot / max(1, len(train) // a.batch))
    for k, items in dev.items():
        if items: row[k] = hl.score(items, detect(net, items))['F1']
    row['score'] = float(np.mean([row[k] for k in dev if k in row])); log.append(row)
    if best is None or row['score'] > best[0]: best = (row['score'], epoch + 1, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()})
    if (epoch + 1) % 10 == 0: print(json.dumps(row), flush=True)
torch.save(dict(arch='tcn', n_in=N_IN, hidden=int(ck['hidden']), state=best[2], decoder=dict(thr=.4, gap_s=.3, lam=0.0)), out / 'hitnet.pt')
(out / 'log.json').write_text(json.dumps(dict(config=vars(a), best_epoch=best[1], best_score=best[0], seconds=time.time() - began, log=log), indent=1))
print(a.name, 'best epoch', best[1], json.dumps(log[best[1] - 1]), flush=True)
