"""End-to-end stroke chain: detect hits, cut the production BST window at each DETECTED hit, classify.
A labelled hit counts only when a detection lies within +/-2 frames (one-to-one) AND the predicted type
is in the label's allowed set. Misses, false alarms and wrong types all cost.
Usage: 60_chain_eval.py [--final] NAME=HIT:BST ...   HIT in {rules, released, path.pt}; BST as in 40_eval.py"""
import json, sys
from pathlib import Path
import cv2, numpy as np, torch
import bstlib as bo, hitlib as hl, vblib as vb
from importlib import import_module
from app.services.tracking import bst as rt_bst, hitnet_core as core, players
ev = import_module('40_eval')
final = '--final' in sys.argv; arms = [x for x in sys.argv[1:] if not x.startswith('--')]
T = bo.TYPES


def vb_items(split):
    z = np.load(ev.DATA / f'vb_hit_{split}.npz', allow_pickle=False); lab = {}
    for seg, k, al, t in zip(z['seg'], z['k'], z['allowed12'], z['type']): lab.setdefault(str(seg), {})[int(k)] = al if t >= 0 else np.zeros(12, bool)
    out = []
    for s in [s for s in hl.load_vb() if s['split'] == split]:
        f = np.load(Path('/dev/shm/claude/vbr/feat') / (s['id'] + '.npz'))
        s.update(joints=f['joints'], shuttle=f['shuttle'], pos=None, allowed=[lab[s['id']][k] for k in range(len(s['hits']))], feat='/dev/shm/claude/vbr/feat'); out.append(s)
    return out


def bfmd_items(split):
    segs = {sg['id']: (m, sg) for m in json.loads((hl.HERE / 'bfmd_segments.json').read_text()) for sg in m['segments']}
    MAP = {'serve': ['short_serve'], 'flick_serve': ['long_serve'], 'net_shot': ['net', 'cross_net'], 'lift': ['lift'], 'smash': ['smash'], 'block': ['block'],
           'drive': ['drive'], 'push': ['push'], 'drop': ['drop'], 'clear': ['clear'], 'net_kill': ['kill'], 'press': []}
    out = []
    for s in [s for s in hl.load_bfmd() if s['split'] == split]:
        m, sg = segs[s['id']]; c = m['court']; f = np.load(Path('/dev/shm/claude/bfmd/feat') / (s['id'] + '.npz'))
        Hm = cv2.getPerspectiveTransform(np.float32([c['top_left'], c['top_right'], c['bottom_right'], c['bottom_left']]), np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]))
        pos = np.zeros((len(f['covered']), 2, 2), np.float32)
        for p in (0, 1):
            ok = np.isfinite(f['box'][:, p]).all(-1) & np.isfinite(f['kp'][:, p]).all((-1, -2)) & f['joints'][:, p].any((-1, -2))
            if ok.any(): pos[ok, p] = cv2.perspectiveTransform(players.foot_pixels(f['box'][ok, p].astype(float), f['kp'][ok, p].astype(float))[0][None].astype(np.float32), Hm)[0]
        al = []
        for h in sg['hits']:
            a = np.zeros(12, bool); a[[T.index(t) for x in h['types'] for t in MAP[x]]] = True; al.append(a)
        s.update(joints=f['joints'], shuttle=f['shuttle'], pos=pos, allowed=al, feat='/dev/shm/claude/bfmd/feat'); out.append(s)
    return out


def windows(s, frames):
    rows = []
    for h in frames:
        half = int(round(s['fps'])) // 2; a, b = max(0, h - half), min(len(s['joints']), h + half + 1); pad = max(0, half - h)
        j, sh = s['joints'][a:b], s['shuttle'][a:b]; p = np.zeros((b - a, 2, 2), np.float32) if s['pos'] is None else s['pos'][a:b]
        if pad: j = np.concatenate((np.zeros((pad,) + j.shape[1:], j.dtype), j)); sh = np.concatenate((np.zeros((pad, 2), sh.dtype), sh)); p = np.concatenate((np.zeros((pad, 2, 2), p.dtype), p))
        rows.append(rt_bst.model_inputs([(j, p, sh)]))
    return rows


@torch.inference_mode()
def run(items, hit, nets):
    if hit == 'rules': det = {s['id']: hl.rules_detect(s['id'], s['feat']) for s in items}
    else:
        ck = torch.load(str(hl.HITNET) if hit == 'released' else hit, map_location='cpu', weights_only=True)
        net = core.HitTCN(int(ck['n_in']), int(ck['hidden'])); net.load_state_dict(ck['state']); net = net.cuda().eval(); det = {}
        for s in items:
            x = torch.from_numpy(hl.features(s, int(ck['n_in'])))[None].cuda()
            det[s['id']] = core.decode_nms(core.sigmoid(net(x)[0, :, 0].float().cpu().numpy()), s['fps'], .4, .3)
    tp = fp = fn = jt = n_det = n_truth = 0
    for s in items:
        lo, hi = s.get('valid_from', 0), s['valid_to']
        truth = [(int(h), al) for h, al in zip(s['hits'], s['allowed']) if lo <= h < hi]; pred = [int(p) for p in det[s['id']] if lo <= p < hi]
        types = {}
        if pred:
            rows = windows(s, pred); arr = [torch.from_numpy(np.concatenate([r[c] for r in rows])) for c in range(4)]
            for p, t in zip(pred, bo.type_prediction(bo.logits_of(nets, arr).numpy())): types[p] = int(t)
        used = set()
        for h, al in truth:
            cand = [p for p in pred if p not in used and abs(p - h) <= 2]
            if not cand:
                fn += 1; n_truth += bool(al.any()); continue
            p = min(cand, key=lambda p: abs(p - h)); used.add(p); tp += 1
            if al.any():
                n_truth += 1; n_det += 1; jt += bool(types[p] >= 0 and al[types[p]])
        extra = len(pred) - len(used); fp += extra; n_det += extra
    P = tp / max(tp + fp, 1); R = tp / max(tp + fn, 1); jp = jt / max(n_det, 1); jr = jt / max(n_truth, 1)
    return dict(hit_f1=round(2 * P * R / max(P + R, 1e-9), 4), hit_precision=round(P, 4), hit_recall=round(R, 4), type_accuracy_on_detected=round(jt / max(n_det - fp, 1), 4),
                joint_precision=round(jp, 4), joint_recall=round(jr, 4), joint_f1=round(2 * jp * jr / max(jp + jr, 1e-9), 4), typed_hits=n_truth, joint_correct=jt)


sets = {'vb_development': vb_items('development'), 'bfmd_dev': bfmd_items('dev')}
if final: sets.update(vb_holdout=vb_items('holdout'), bfmd_test=bfmd_items('test'))
report = {}
for arm in arms:
    name, _, spec = arm.partition('='); hit, _, bspec = spec.partition(':')
    nets = [bo.load_net(p) for p in ev.paths(bspec)]; report[name] = {}
    for k, items in sets.items():
        if not items: continue
        r = run(items, hit, nets); report[name][k] = r
        print(f"{name:<22} {k:<15} hit F1 {r['hit_f1']:.4f}  type acc on detected {r['type_accuracy_on_detected']:.4f}  JOINT F1 {r['joint_f1']:.4f} (P {r['joint_precision']:.3f} R {r['joint_recall']:.3f}) correct {r['joint_correct']}/{r['typed_hits']}", flush=True)
out = [x.split('=', 1)[1] for x in sys.argv if x.startswith('--out=')]
if out: open(out[0], 'w').write(json.dumps(report, indent=1))
