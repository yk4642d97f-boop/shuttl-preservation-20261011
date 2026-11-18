"""BST fine-tuning with corrected public labels, hit-centred windows and label-free augmentation.

Every training source is a set of hit-centred windows with a per-row set of allowed classes
(25-way: unknown, 12 far types, 12 near types). A singleton set is ordinary supervision; a larger
set expresses what the source labels really say (hitter side undecided, or a source class that
covers two BST types) and is trained by maximising the summed probability of the set.
Checkpoints are chosen on development data only (professional match 041 and the VideoBadminton
development date); holdout data is never read here.
"""
import argparse, json, time
from pathlib import Path
import numpy as np, torch
from torch import nn
import bstlib as bo

DATA = Path('/root/shuttl-claude-20261118/data')
LR = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]
PERM = list(range(17))
for a_, b_ in LR: PERM[a_], PERM[b_] = b_, a_
PAIRS = [(0, 1), (0, 2), (1, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]


def rebuild(j):
    """joints (...,17,2) -> jnb (...,72) with the released bone rule."""
    s = j[..., [p[0] for p in PAIRS], :]; e = j[..., [p[1] for p in PAIRS], :]
    bones = torch.where((s != 0) & (e != 0), e - s, torch.zeros_like(e))
    return torch.cat((j, bones), dim=-2).flatten(-2)


def flip(j, s, p, mask):
    """Mirror left/right for rows in mask. Types and sides are unchanged by a mirror."""
    if not mask.any(): return j, s, p
    jj = j[mask][..., :34].unflatten(-1, (17, 2)).clone()
    jj[..., 0] = -jj[..., 0]; jj = jj[..., PERM, :]
    j = j.clone(); j[mask] = rebuild(jj)
    s = s.clone(); sm = s[mask]; seen = (sm != 0).any(-1)
    sm[..., 0] = torch.where(seen, 1 - sm[..., 0], sm[..., 0]); s[mask] = sm
    p = p.clone(); pm = p[mask]; seen = (pm != 0).any(-1)
    pm[..., 0] = torch.where(seen, 1 - pm[..., 0], pm[..., 0]); p[mask] = pm
    return j, s, p


def shift(j, s, p, l, k):
    """Move content by k frames (k>0 later, k<0 earlier) with zero fill; emulates hit-time error."""
    if k == 0: return j, s, p, l
    out = []
    for x in (j, s, p):
        y = torch.zeros_like(x)
        if k > 0: y[:, k:] = x[:, :-k]
        else: y[:, :k] = x[:, -k:]
        out.append(y)
    return out[0], out[1], out[2], (l + k).clamp(2, 30)


def drop_prefix(j, s, p, g, prob, max_k=15):
    """Zero the first k frames of some rows (segment starts have no pre-contact frames)."""
    n = len(j); pick = torch.rand(n, generator=g, device=j.device) < prob
    if not pick.any(): return j, s, p
    k = torch.randint(1, max_k + 1, (n,), generator=g, device=j.device)
    t = torch.arange(j.shape[1], device=j.device)[None]
    m = pick[:, None] & (t < k[:, None])
    return j.masked_fill(m[:, :, None, None], 0), s.masked_fill(m[:, :, None], 0), p.masked_fill(m[:, :, None, None], 0)


def drop_frames(j, s, g, prob, rate=.15):
    """Zero both players' poses on random frames of some rows (pose coverage holes)."""
    n = len(j); pick = torch.rand(n, generator=g, device=j.device) < prob
    if not pick.any(): return j, s
    m = pick[:, None] & (torch.rand(j.shape[:2], generator=g, device=j.device) < rate)
    return j.masked_fill(m[:, :, None, None], 0), s.masked_fill(m[:, :, None], 0)


def set_loss(logits, allowed, eps=.1):
    """Label-smoothed negative log of the probability mass on each row's allowed classes."""
    logp = torch.log_softmax(logits.float(), 1)
    inside = torch.logsumexp(logp.masked_fill(~allowed, -torch.inf), 1)
    return -((1 - eps) * inside + eps * logp.mean(1)).mean()


def allowed_from(types, side):
    """types (N,12) bool, side (N,) in {-1,0,1} -> (N,25) bool."""
    n = len(side); a = torch.zeros(n, 25, dtype=torch.bool)
    a[:, 1:13] = types & (side != 1)[:, None]; a[:, 13:25] = types & (side != 0)[:, None]
    return a


class Source:
    def __init__(self, name, arrays, allowed, batch, weight, balance='none', occl=(.3, .05, .3), pos_drop=.5):
        self.name = name; self.x = [t.cuda() for t in arrays]; self.allowed = allowed.cuda(); self.n = len(allowed)
        self.batch = batch; self.weight = weight; self.occl = occl; self.pos_drop = pos_drop
        key = self.allowed[:, 1:13].float() + self.allowed[:, 13:25].float(); key = key / key.sum(1, keepdim=True).clamp_min(1)
        counts = key.sum(0).clamp_min(1)
        per = {'inv': 1 / counts, 'sqrt': counts.rsqrt(), 'none': torch.ones_like(counts)}[balance]
        self.w = (key * per).sum(1).clamp_min(1e-6)

    def sample(self, g):
        i = torch.multinomial(self.w, self.batch, replacement=True, generator=g)
        return [t[i] for t in self.x], self.allowed[i]


def one_hot25(label):
    return torch.nn.functional.one_hot(label, 25).bool()


def load_vb(style, split, labels='new', use_side=True):
    z = np.load(DATA / f'vb_{style}_{split}.npz', allow_pickle=False)
    if labels == 'new': types = torch.from_numpy(z['allowed12']); keep = types.any(1)
    else:
        t = z['old_type']; keep = torch.from_numpy(t >= 0); types = torch.nn.functional.one_hot(torch.from_numpy(np.maximum(t, 0)), 12).bool()
    side = torch.from_numpy(z['side']) if use_side else torch.full((len(t),), -1)
    arrays = [torch.from_numpy(z[k])[keep] for k in ('jnb', 'shuttle', 'pos', 'length')]
    return arrays, allowed_from(types, side)[keep]


def load_set(name):
    z = np.load(DATA / f'{name}.npz', allow_pickle=False)
    arrays = [torch.from_numpy(z[k]) for k in ('jnb', 'shuttle', 'pos', 'length')]
    allowed = torch.from_numpy(z['allowed']); keep = allowed.any(1)
    return [t[keep] for t in arrays], allowed[keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True); ap.add_argument('--members', default='0,1,2')
    ap.add_argument('--epochs', type=int, default=20); ap.add_argument('--batch', type=int, default=256)
    ap.add_argument('--vb', choices=['none', 'hit', 'clip'], default='hit'); ap.add_argument('--vb-labels', choices=['new', 'old'], default='new')
    ap.add_argument('--vb-batch', type=int, default=128); ap.add_argument('--vb-weight', type=float, default=.5)
    ap.add_argument('--vb-side', type=int, default=1, help='1: supervise far/near with the inferred hitter side; 0: marginalise')
    ap.add_argument('--vb-balance', choices=['inv', 'sqrt', 'none'], default='sqrt')
    ap.add_argument('--extra', default='', help='comma list of extra hit-centred labelled sets in data/ (e.g. bfmd_train)')
    ap.add_argument('--extra-weight', type=float, default=1.0); ap.add_argument('--extra-batch', type=int, default=192)
    ap.add_argument('--flip', type=float, default=.5); ap.add_argument('--jitter', type=int, default=2)
    ap.add_argument('--prefix', type=float, default=.1); ap.add_argument('--holes', type=float, default=.3)
    ap.add_argument('--lr', type=float, default=1e-4); ap.add_argument('--smooth', type=float, default=.1)
    ap.add_argument('--out', type=Path, default=Path('/dev/shm/claude/runs'))
    a = ap.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    out = a.out / a.name; out.mkdir(parents=True, exist_ok=True)
    (out / 'config.json').write_text(json.dumps(vars(a), default=str, indent=1))
    released = bo.released_paths()
    tj, ts, tp, tl, ty = bo.load_split('train'); n = len(ty)
    sources = [Source('pro', [tj, ts, tp, tl], one_hot25(ty), a.batch, 1.0)]
    if a.vb != 'none':
        arrays, allowed = load_vb(a.vb, 'train', a.vb_labels, bool(a.vb_side))
        sources.append(Source('vb', arrays, allowed, a.vb_batch, a.vb_weight, a.vb_balance, occl=(.1, .05, .2), pos_drop=0.))
    for name in [x for x in a.extra.split(',') if x]:
        arrays, allowed = load_set(name)
        sources.append(Source(name, arrays, allowed, a.extra_batch, a.extra_weight))
    vj, vs, vp, vl, vy = bo.load_split('val')
    dz = np.load(DATA / 'vb_hit_development.npz', allow_pickle=False)
    dev_arrays = [torch.from_numpy(dz[k]) for k in ('jnb', 'shuttle', 'pos', 'length')]; dev_type = dz['type']
    steps_per_epoch = (n + a.batch - 1) // a.batch
    for member in [int(x) for x in a.members.split(',')]:
        if (out / f'member-{member}.json').exists(): continue
        seed = 20261118 + member; torch.manual_seed(seed)
        g = torch.Generator(device='cuda').manual_seed(seed)
        net = bo.load_net(released[member])
        opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=.01)
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * steps_per_epoch, pct_start=.1)
        best = None; log = []; began = time.time()
        for epoch in range(a.epochs):
            net.train(); tot = 0.
            for _ in range(steps_per_epoch):
                loss = 0.
                for src in sources:
                    (j, s, p, l), allowed = src.sample(g)
                    j, s, p = bo.occlude(j, s, p, g, *src.occl)
                    if src.pos_drop: p[torch.rand(len(j), generator=g, device='cuda') < src.pos_drop] = 0
                    if a.jitter:
                        j, s, p, l = shift(j, s, p, l, int(torch.randint(-a.jitter, a.jitter + 1, (1,), generator=g, device='cuda')))
                    if a.flip: j, s, p = flip(j, s, p, torch.rand(len(j), generator=g, device='cuda') < a.flip)
                    if a.prefix: j, s, p = drop_prefix(j, s, p, g, a.prefix)
                    if a.holes: j, s = drop_frames(j, s, g, a.holes)
                    part = set_loss(net(j, s, p, l), allowed, a.smooth)
                    if src.name == 'pro': tot += float(part.detach())
                    loss = loss + src.weight * part
                opt.zero_grad(set_to_none=True); loss.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.)
                opt.step(); sched.step()
            clean = bo.pro_metrics(bo.logits_of([net], (vj, vs, vp, vl)), vy)['acc12']
            nopos = bo.pro_metrics(bo.logits_of([net], (vj, vs, torch.zeros_like(vp), vl)), vy)['acc12']
            dk = dev_type >= 0; dm = bo.clip_metrics(bo.type_prediction(bo.logits_of([net], dev_arrays).numpy())[dk], dev_type[dk])
            score = .5 * dm['macro_recall'] + .25 * clean + .25 * nopos
            log.append(dict(epoch=epoch + 1, loss=tot / steps_per_epoch, clean=clean, nopos=nopos, dev_acc=dm['accuracy'], dev_macro=dm['macro_recall'], score=score))
            if best is None or score > best[0]:
                best = (score, epoch + 1, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()})
        torch.save(best[2], out / f'member-{member}.pt')
        torch.save({k: v.detach().cpu() for k, v in net.state_dict().items()}, out / f'member-{member}-last.pt')
        (out / f'member-{member}.json').write_text(json.dumps(dict(member=member, seed=seed, best_epoch=best[1], best_score=best[0], seconds=time.time() - began, log=log), indent=1))
        print(a.name, 'member', member, 'best epoch', best[1], json.dumps(log[best[1] - 1]), flush=True)


if __name__ == '__main__': main()
