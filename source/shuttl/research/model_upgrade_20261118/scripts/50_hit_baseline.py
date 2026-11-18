"""Released HitNet v2 and the rule detector on amateur (VideoBadminton) and professional (BFMD) rallies."""
import json, sys, numpy as np, torch
import hitlib as hl
from app.services.tracking import hitnet_core as core
ck = torch.load(hl.HITNET, map_location='cpu', weights_only=True)
net = core.HitTCN(51, int(ck['hidden'])); net.load_state_dict(ck['state']); net = net.cuda().eval()


@torch.inference_mode()
def detect(segs, thr=.4, gap=.3, drop_foot=False):
    out = {}
    for s in segs:
        raw = s['raw'].copy()
        if drop_foot: raw[:, 12:] = np.nan
        x = torch.from_numpy(core.derive(raw, s['fps']))[None].cuda()
        p = core.sigmoid(net(x)[0, :, 0].float().cpu().numpy())
        out[s['id']] = core.decode_nms(p, s['fps'], thr, gap)
    return out


sets = {'vb': hl.load_vb()}
if '--bfmd' in sys.argv: sets['bfmd'] = hl.load_bfmd()
for dom, segs in sets.items():
    for split in sorted({s['split'] for s in segs}):
        sub = [s for s in segs if s['split'] == split]
        for tol in (2,):
            r = hl.score(sub, detect(sub), tol)
            print(f"{dom}/{split:<12} HitNet v2 F1@±{tol} {r['F1']:.4f} P {r['P']:.3f} R {r['R']:.3f} first {r['first_hit_recall']:.3f} interior {r['interior_recall']:.3f} FP/min {r['fp_per_min']} hits {r['tp']+r['fn']} segs {r['segments']}", flush=True)
        if dom == 'bfmd':
            r = hl.score(sub, detect(sub, drop_foot=True), 2); print(f"{dom}/{split:<12}   without court positions F1@±2 {r['F1']:.4f} R {r['R']:.3f}")
