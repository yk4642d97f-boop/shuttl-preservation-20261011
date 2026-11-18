"""Label-free check that FineBadminton interval starts are contact frames in the decoded video: the new
hit detector (trained on other datasets) should fire on them. Reports per-video F1 and the offset histogram."""
import collections, json, sys, numpy as np, torch
import hitlib as hl
from app.services.tracking import hitnet_core as core
segs = hl.load_generic(hl.HERE / 'fineb_segments.json', '/dev/shm/claude/fineb/feat', 'fineb', 'all')
ck = torch.load(sys.argv[1], map_location='cpu', weights_only=True); net = core.HitTCN(int(ck['n_in']), int(ck['hidden'])); net.load_state_dict(ck['state']); net = net.cuda().eval()
det = {}
with torch.inference_mode():
    for s in segs:
        x = torch.from_numpy(hl.features(s, int(ck['n_in'])))[None].cuda()
        det[s['id']] = core.decode_nms(core.sigmoid(net(x)[0, :, 0].float().cpu().numpy()), s['fps'], .4, .3)
by = collections.defaultdict(list)
for s in segs: by[s['group']].append(s)
print('rallies', len(segs), 'videos', len(by), 'overall', json.dumps({k: v for k, v in hl.score(segs, det).items() if k in ('F1', 'P', 'R', 'first_hit_recall')}))
rows = []
for g, items in sorted(by.items()):
    off = collections.Counter()
    for s in items:
        for h in s['hits']:
            d = [p - h for p in det[s['id']] if abs(p - h) <= 8]
            if d: off[min(d, key=abs)] += 1
    r = hl.score(items, det); mode = off.most_common(1)[0][0] if off else None
    rows.append((g, len(items), items[0]['fps'], r['F1'], mode, r['tp'] + r['fn']))
for g, n, fps, f1, mode, hits in rows: print(f'  {g:<12} rallies {n:<4} fps {fps:<7.2f} hits {hits:<5} F1@±2 {f1:.3f}  modal offset {mode}')
bad = [r for r in rows if r[3] < .75]; print('videos with F1 < 0.75:', [(r[0], r[2], r[3], r[4]) for r in bad])
