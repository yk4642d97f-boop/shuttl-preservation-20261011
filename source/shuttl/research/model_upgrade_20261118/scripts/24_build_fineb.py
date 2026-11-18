"""FineBadminton (70 professional broadcast videos) as BST training data.

Its annotations give a stroke type, the hitter (top/bottom) and an ACTION interval per stroke; the
interval starts 0.2-0.4 s before the contact, so the contact frame is not annotated. It is taken
from the new hit detector: an interval is used only when exactly one hit is detected inside it
(92% of intervals), and the production window is cut around that detected frame, which is also what
production does. Type sets follow the source vocabulary ('push shot' covers pushes and flat lifts).
"""
import collections, json, sys
from pathlib import Path
import numpy as np, torch
import hitlib as hl, bstlib as bo, vblib as vb
from app.services.tracking import bst, hitnet_core as core
T = bo.TYPES
ck = torch.load(sys.argv[1], map_location='cpu', weights_only=True); net = core.HitTCN(int(ck['n_in']), int(ck['hidden'])); net.load_state_dict(ck['state']); net = net.cuda().eval()
out = collections.defaultdict(lambda: collections.defaultdict(list)); stats = collections.Counter()
for m in json.loads((hl.HERE / 'fineb_segments.json').read_text()):
    split = 'test' if int(m['video'][:4]) % 5 == 0 else 'train'
    for sg in m['segments']:
        f = Path('/dev/shm/claude/fineb/feat') / (sg['id'] + '.npz')
        if not f.exists(): stats['rally_not_extracted'] += 1; continue
        z = np.load(f)
        if len(z['hitnet_raw']) != len(z['covered']): continue
        fps = float(z['meta'][0]); seg = dict(raw=z['hitnet_raw'], kp=z['kp'], box=z['box'], wh=z['meta'][1:3], fps=fps)
        with torch.inference_mode():
            p = core.sigmoid(net(torch.from_numpy(hl.features(seg, int(ck['n_in'])))[None].cuda())[0, :, 0].float().cpu().numpy())
        det = core.decode_nms(p, fps, .4, .3); starts = [h['frame'] for h in sg['hits']] + [len(p) - 20]
        for h, a, b in zip(sg['hits'], starts, starts[1:]):
            inside = [d for d in det if a <= d < b]
            if len(inside) != 1: stats['interval_without_single_hit'] += 1; continue
            if not h['allowed']: stats['type_unmapped'] += 1; continue
            c = inside[0]; j, s, info = vb.window(z, c, fps, center=True)
            jnb, sh, pos, length = vb.to_model(j, s)
            al = np.zeros(25, bool)
            for t in h['allowed']:
                i = T.index(t)
                if h['side'] != 1: al[1 + i] = True
                if h['side'] != 0: al[13 + i] = True
            o = out[split]; o['jnb'].append(jnb); o['shuttle'].append(sh); o['pos'].append(pos); o['length'].append(length); o['allowed'].append(al)
            o['side'].append(h['side']); o['match'].append(m['match']); o['seg'].append(sg['id']); o['source_type'].append(h['types'][0]); o['offset'].append(c - a)
            o['gate_prod'].append(info['covered_all'] and info['resolved_any']); stats['used'] += 1
for split, o in sorted(out.items()):
    arrays = {k: (np.stack(v) if k in ('jnb', 'shuttle', 'pos', 'allowed') else np.array(v)) for k, v in o.items()}
    np.savez_compressed(hl.HERE / 'data' / f'fineb_{split}.npz', **arrays)
    print(split, 'n', len(arrays['side']), 'videos', len(set(arrays['match'])), 'gate', round(float(arrays['gate_prod'].mean()), 4), dict(collections.Counter(arrays['source_type']).most_common(12)))
print(dict(stats))
