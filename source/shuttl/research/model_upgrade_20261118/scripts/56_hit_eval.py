"""Hit detection: released HitNet v2, the production rule detector, and fine-tuned candidates.
Usage: 56_hit_eval.py [--final] [--rules] NAME=weights.pt ...   (released = hitnet_single_v2)"""
import sys, json, numpy as np, torch
import hitlib as hl
from app.services.tracking import hitnet_core as core
final = '--final' in sys.argv; rules = '--rules' in sys.argv; arms = [x for x in sys.argv[1:] if not x.startswith('--')]
sets = {}
vb = hl.load_vb()
for sp in ['development'] + (['holdout'] if final else []): sets['vb/' + sp] = ([s for s in vb if s['split'] == sp], '/dev/shm/claude/vbr/feat')
try:
    bf = hl.load_bfmd()
    for sp in ['dev'] + (['test'] if final else []):
        sub = [s for s in bf if s['split'] == sp]
        if sub: sets['bfmd/' + sp] = (sub, '/dev/shm/claude/bfmd/feat')
except Exception as e: print('bfmd unavailable', e)
s41 = hl.load_generic(hl.HERE / 's041_segments.json', '/dev/shm/claude/s041/feat', 's041', 'val') if (hl.HERE / 's041_segments.json').exists() else []
if s41: sets['shuttleset041'] = (s41, '/dev/shm/claude/s041/feat')


@torch.inference_mode()
def detect(net, items, drop_foot=False):
    res = {}; n_in = net.inp.in_channels
    for s in items:
        raw = s['raw'].copy()
        if drop_foot: raw[:, 12:] = np.nan
        x = torch.from_numpy(hl.features(s, n_in, raw))[None].cuda()
        res[s['id']] = core.decode_nms(core.sigmoid(net(x)[0, :, 0].float().cpu().numpy()), s['fps'], .4, .3)
    return res


def offsets(items, det):
    c = {}
    for s in items:
        for h in s['hits']:
            if h >= s['valid_to'] or h < s.get('valid_from', 0): continue
            d = [p - h for p in det.get(s['id'], []) if abs(p - h) <= 6]
            if d:
                k = min(d, key=abs); c[k] = c.get(k, 0) + 1
    return ' '.join(f'{k:+d}:{c[k]}' for k in sorted(c))


def show(tag, r): print(f"  {tag:<26} F1@±2 {r['F1']:.4f}  P {r['P']:.3f} R {r['R']:.3f}  first-hit R {r['first_hit_recall']:.3f} interior R {r['interior_recall']:.3f}  FP/min {r['fp_per_min']:<6} hits {r['tp'] + r['fn']}", flush=True)


report = {}
for name, (items, feat) in sets.items():
    print(name, 'segments', len(items)); report[name] = {}
    if rules:
        det = {s['id']: hl.rules_detect(s['id'], feat) for s in items}; r = hl.score(items, det); show('rules (production default)', r); report[name]['rules'] = r
        print('      offsets (detection - label, interior hits):', offsets(items, det))
    for arm in arms:
        tag, _, path = arm.partition('='); path = str(hl.HITNET) if tag == 'released' else path
        ck = torch.load(path, map_location='cpu', weights_only=True); net = core.HitTCN(int(ck['n_in']), int(ck['hidden'])); net.load_state_dict(ck['state']); net = net.cuda().eval()
        det = detect(net, items); r = hl.score(items, det); show(tag, r); report[name][tag] = r
        print('      offsets (detection - label, interior hits):', offsets(items, det), '| F1@±1 %.4f F1@±3 %.4f' % (hl.score(items, det, 1)['F1'], hl.score(items, det, 3)['F1']))
        if name.startswith('bfmd') or name.startswith('shuttleset'):
            r = hl.score(items, detect(net, items, True)); show(tag + ' (no court pos)', r); report[name][tag + '_nofoot'] = r
        r1 = hl.score(items, detect(net, items), 1); report[name][tag + '_tol1'] = r1
out = [x.split('=', 1)[1] for x in sys.argv if x.startswith('--out=')]
if out: open(out[0], 'w').write(json.dumps(report, indent=1))
