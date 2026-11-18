"""Where do detected contacts fall inside FineBadminton action intervals?"""
import collections, json, sys, numpy as np, torch
import hitlib as hl
from app.services.tracking import hitnet_core as core
segs = hl.load_generic(hl.HERE / 'fineb_segments.json', '/dev/shm/claude/fineb/feat', 'fineb', 'all')
ck = torch.load(sys.argv[1], map_location='cpu', weights_only=True); net = core.HitTCN(int(ck['n_in']), int(ck['hidden'])); net.load_state_dict(ck['state']); net = net.cuda().eval()
cnt = collections.Counter(); rel = []; absoff = collections.Counter(); per = collections.defaultdict(list)
with torch.inference_mode():
    for s in segs:
        x = torch.from_numpy(hl.features(s, int(ck['n_in'])))[None].cuda()
        p = core.sigmoid(net(x)[0, :, 0].float().cpu().numpy()); det = core.decode_nms(p, s['fps'], .4, .3)
        hits = list(s['hits']) + [len(p) - 20]
        for a, b in zip(hits, hits[1:]):
            inside = [d for d in det if a <= d < b]; cnt[min(len(inside), 3)] += 1
            if len(inside) == 1 and b > a:
                rel.append((inside[0] - a) / (b - a)); absoff[min(inside[0] - a, 40)] += 1; per[s['group']].append(inside[0] - a)
        before = [d for d in det if d < hits[0]]; cnt['det_before_first_interval'] += len(before)
print('intervals by number of detections inside:', dict(cnt))
rel = np.array(rel); print('relative position of the single detection inside its interval: quartiles', np.round(np.percentile(rel, [10, 25, 50, 75, 90]), 2))
print('absolute offset (frames after interval start):', ' '.join(f'{k}:{absoff[k]}' for k in sorted(absoff)))
print('per-video median offset:', {g[-4:]: (float(np.median(v)), round(float(np.std(v)), 1)) for g, v in sorted(per.items())})
