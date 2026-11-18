"""Shared harness for BST stroke-type experiments on the GPU box (2026-11-18).

Rebuilt from the released runtime (bst_vendor) and yesterday's persisted scripts;
the original support module lived on a RAM disk and was lost on reboot.
Class layout: 0 unknown, 1..12 far(Top) types, 13..24 near(Bottom) types.
"""
import json, os, sys
from pathlib import Path
import numpy as np
import torch

RUNTIME = Path('/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime')
ART = RUNTIME / 'research/cloud_upgrade/artifacts/bst_seq30'
FIXED = RUNTIME / 'research/cloud_upgrade/data/bst_fixed30'
PUBLIC = Path('/root/shuttl-codex-public-20261117-results/prepared_features')
PREV = Path('/root/shuttl-codex-public-20261117-results')
sys.path.insert(0, str(RUNTIME / 'backend'))
TYPES = ('net', 'block', 'smash', 'lift', 'clear', 'drive', 'drop', 'push', 'kill', 'cross_net', 'short_serve', 'long_serve')


def make_net(**kw):
    from app.services.tracking.bst_vendor.bst import BST_CG_AP
    args = dict(in_dim=72, n_class=25, seq_len=30, depth_tem=2, depth_inter=1)
    args.update(kw)
    return BST_CG_AP(**args)


def load_net(path, device='cuda', **kw):
    net = make_net(**kw)
    net.load_state_dict(torch.load(path, map_location='cpu', weights_only=True), strict=True)
    return net.to(device).eval()


def released_paths():
    doc = json.loads((ART / 'manifest.json').read_text())
    return [ART / w['file'] for w in doc['weights']]


def load_split(name):
    z = np.load(FIXED / f'{name}.npz', allow_pickle=False)
    return [torch.from_numpy(z[k]) for k in ('jnb', 'shuttle', 'pos', 'length', 'label')]


def split_names(name):
    return np.load(FIXED / f'{name}.npz', allow_pickle=False)['name']


def load_public(name):
    z = np.load(PUBLIC / f'public_{name}.npz', allow_pickle=False)
    arrays = [torch.from_numpy(z[k]) for k in ('jnb', 'shuttle', 'pos', 'length')]
    return arrays, z['type'], z['group'], z['id']


@torch.inference_mode()
def logits_of(nets, arrays, device='cuda', batch=2048):
    """Mean logits over members; returns a CPU float tensor (N,25)."""
    n = len(arrays[0])
    out = torch.zeros(n, 25)
    for net in nets:
        net.eval()
        for i in range(0, n, batch):
            args = [a[i:i + batch].to(device) for a in arrays[:4]]
            out[i:i + batch] += net(*args).float().cpu() / len(nets)
    return out


def type_prediction(logits):
    """Runtime rule: argmax over 25 logits, map to 12 types; class 0 = abstain (-1)."""
    cls = np.asarray(logits).argmax(1)
    return np.where(cls > 0, (cls - 1) % 12, -1)


def pro_metrics(logits, y):
    logits = torch.as_tensor(logits); y = torch.as_tensor(y)
    cls = logits.argmax(1)
    typ = torch.where(cls > 0, (cls - 1) % 12, torch.full_like(cls, -1))
    ty = (y - 1) % 12
    far = y <= 12
    ok = typ == ty
    return {'acc25': float((cls == y).float().mean()), 'acc12': float(ok.float().mean()),
            'acc12_far_hitter': float(ok[far].float().mean()), 'acc12_near_hitter': float(ok[~far].float().mean())}


def clip_metrics(pred, truth):
    pred = np.asarray(pred); truth = np.asarray(truth)
    classes = np.unique(truth); recall = []; f1 = []; per = {}
    for c in classes:
        tp = int(((pred == c) & (truth == c)).sum()); fp = int(((pred == c) & (truth != c)).sum()); fn = int(((pred != c) & (truth == c)).sum())
        r = tp / (tp + fn); f = 2 * tp / max(2 * tp + fp + fn, 1)
        recall.append(r); f1.append(f); per[TYPES[int(c)]] = {'n': int((truth == c).sum()), 'recall': round(r, 4), 'f1': round(f, 4)}
    return {'n': len(truth), 'accuracy': float((pred == truth).mean()), 'macro_recall': float(np.mean(recall)),
            'macro_f1': float(np.mean(f1)), 'answered': int((pred >= 0).sum()), 'per_class': per}


def occlude(j, s, p, g, p_far=.3, p_near=.05, p_shuttle=.3):
    """Zero one player's pose stream and/or the shuttle stream for a random subset of clips."""
    j = j.clone(); s = s.clone(); p = p.clone()
    n = len(j); dev = j.device
    r = torch.rand(n, 3, generator=g, device=dev)
    far = r[:, 0] < p_far; near = (r[:, 1] < p_near) & ~far
    j[far, :, 0] = 0; p[far, :, 0] = 0
    j[near, :, 1] = 0; p[near, :, 1] = 0
    s[r[:, 2] < p_shuttle] = 0
    return j, s, p
