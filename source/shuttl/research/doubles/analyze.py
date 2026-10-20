"""Doubles evidence from public data: (1) inter-hit intervals vs HitNet's 0.30 s NMS gap,
(2) which partner hit, given the hitting side.

S2Doubles (HuangYuHsien/S2DoublesDataset; 3 BWF matches, 6 sets, 30 fps): per shot the
hitter A–D, feet of all four players and the annotated contact projection (hit_x, hit_y),
all in video pixels; homography to the court figure; TrackNet shuttle per rally.
kwyoke am_doubles / am_singles (amateur, 30 fps) and FineBadminton singles (broadcast) for
interval contrast. No videos are needed.
"""
import collections, csv, glob, json, os, sys
import numpy as np
DATA = os.environ.get('AUDIO_STUDY_DATA', '/home/user/workspace/data')
S2D = os.path.join(DATA, 's2d')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'audio'))


def s2d_rallies():
    meta = {r['id']: r for r in csv.DictReader(open(f'{S2D}/Match.csv'))}
    out = []
    for mid in ('1', '2', '3'):
        m = f'Match {int(mid):03d}'
        H = np.array(json.loads(meta[mid]['homography_matrix']))
        seg = sorted(csv.DictReader(open(f'{S2D}/{m}/RallySeg.csv')), key=lambda r: int(r['Start']))
        for setf in sorted(glob.glob(f'{S2D}/{m}/label/set*.csv')):
            sn = os.path.basename(setf)[3]
            by = collections.defaultdict(list)
            for l in csv.DictReader(open(setf)):
                by[int(l['rally'])].append(l)
            keys = [r for r in seg if r['Score'].startswith(sn + '_')]
            for i, r in enumerate(keys):
                shots = sorted(by.get(i + 1, []), key=lambda s: int(s['ball_round']))
                if not shots or not (int(r['Start']) <= int(shots[0]['start_frame']) <= int(r['End'])):
                    continue
                p = f"{S2D}/{m}/tracknet/{r['Score']}.csv"
                tn = {int(t['index']): (float(t['x']), float(t['y'])) for t in csv.DictReader(open(p))} if os.path.exists(p) else {}
                out.append(dict(match=m, set=sn, key=r['Score'], start=int(r['Start']), shots=shots, tn=tn, H=H,
                                up=r['UpCourt'], down=r['DownCourt']))
    return out


def to_court(H, x, y):
    v = H @ np.array([x, y, 1.0])
    return v[:2] / v[2]


def intervals_s2d(R):
    gaps = []
    for r in R:
        f = [int(s['start_frame']) for s in r['shots']]
        gaps += list(np.diff(f) / 30.0)
    return np.array(gaps)


def intervals_kwyoke(kind):
    gaps = []
    for p in glob.glob(f'{DATA}/kwyoke/{kind}/*/player_hit/*.csv'):
        rows = list(csv.DictReader(open(p)))
        f = [int(x['frame']) for x in rows if x['player_hit'] != '0']
        gaps += list(np.diff(f) / 30.0)
    return np.array(gaps)


def intervals_fineb():
    import data as audio_data
    gaps = []
    for c in audio_data.fineb_clips():
        t = np.asarray(c.hits_t)
        d = np.diff(t)
        gaps += list(d[(d > 0) & (d < 3.0)])  # within rallies only
    return np.array(gaps)


def summary(g):
    g = np.asarray(g)
    return dict(n=int(len(g)), median_s=round(float(np.median(g)), 3), min_s=round(float(g.min()), 3),
                **{f'lt_{t:.2f}s': round(float(np.mean(g < t)), 4) for t in (0.15, 0.20, 0.25, 0.30, 0.35)})


def attribution(R):
    """Given the hitting side, pick the partner. Ground truth = labelled hitter."""
    team = {'A': 'AB', 'B': 'AB', 'C': 'CD', 'D': 'CD'}
    partner = {'A': 'B', 'B': 'A', 'C': 'D', 'D': 'C'}
    res = collections.defaultdict(lambda: [0, 0])
    detail = collections.defaultdict(lambda: [0, 0])
    for r in R:
        H = r['H']
        for s in r['shots']:
            h = s['player']
            if h not in team:
                continue
            o = partner[h]
            try:
                fh = (float(s[f'player_{h}_x']), float(s[f'player_{h}_y']))
                fo = (float(s[f'player_{o}_x']), float(s[f'player_{o}_y']))
            except ValueError:
                continue
            serve = s['server'] == '1'
            def add(name, pick_h):
                if pick_h is None:
                    return
                res[name][0] += int(pick_h); res[name][1] += 1
                detail[(name, 'serve' if serve else 'rally')][0] += int(pick_h)
                detail[(name, 'serve' if serve else 'rally')][1] += 1
            # R0: nearest feet to the annotated contact projection (≈ a 3-D contact estimate)
            if s['hit_x'] not in ('', '0') and float(s['hit_x']) > 0:
                hp = (float(s['hit_x']), float(s['hit_y']))
                add('contact_projection_px', np.hypot(*np.subtract(fh, hp)) < np.hypot(*np.subtract(fo, hp)))
                ch, co, cp = to_court(H, *fh), to_court(H, *fo), to_court(H, *hp)
                add('contact_projection_court', np.linalg.norm(ch - cp) < np.linalg.norm(co - cp))
            # R1: nearest feet (|dx|) to the TrackNet shuttle at the labelled frame (best of small offsets)
            f = int(s['start_frame']) - r['start']
            for d in (0, -4, -10):
                if f + d in r['tn']:
                    sx, sy = r['tn'][f + d]
                    if sx > 0:
                        add(f'shuttle_dx_off{d}', abs(sx - fh[0]) < abs(sx - fo[0]))
                        # shuttle vs a point ~1.2 body-heights above the feet (court-scale aware)
                        def body(fp):
                            c = to_court(H, *fp)
                            # pixels per court unit near the feet, vertical direction proxy: width scale
                            c2 = to_court(H, fp[0] + 10, fp[1])
                            px_per_unit = 10 / max(np.linalg.norm(c2 - c), 1e-6)
                            return np.array([fp[0], fp[1] - 1.2 * 1.75 * px_per_unit * (312 / 6.1)])
                        add(f'shuttle_2d_off{d}', np.linalg.norm(body(fh) - (sx, sy)) < np.linalg.norm(body(fo) - (sx, sy)))
            # Serves (no contact projection in S2Doubles): the server stands in front of the partner.
            if serve:
                others = [p for p in 'ABCD' if p not in (h, o)]
                try:
                    opp_y = np.mean([float(s[f'player_{p}_y']) for p in others])
                except ValueError:
                    opp_y = None
                if opp_y is not None and fh[1] != fo[1]:   # image y: partner nearer the opponents
                    add('serve_front_player_px', abs(fh[1] - opp_y) < abs(fo[1] - opp_y))
                net_y = (100 + 784) / 2                      # net line on doubles_court.png
                add('serve_front_player_court', abs(to_court(H, *fh)[1] - net_y) < abs(to_court(H, *fo)[1] - net_y))
    return {k: dict(acc=round(v[0] / max(v[1], 1), 4), n=v[1]) for k, v in res.items()}, \
           {f'{k[0]}|{k[1]}': dict(acc=round(v[0] / max(v[1], 1), 4), n=v[1]) for k, v in detail.items()}


if __name__ == '__main__':
    R = s2d_rallies()
    out = {'s2doubles': dict(rallies=len(R), shots=sum(len(r['shots']) for r in R))}
    out['intervals'] = {'s2doubles_pro_doubles': summary(intervals_s2d(R)),
                        'kwyoke_amateur_doubles': summary(intervals_kwyoke('am_doubles')),
                        'kwyoke_amateur_singles': summary(intervals_kwyoke('am_singles')),
                        'finebadminton_pro_singles': summary(intervals_fineb())}
    acc, detail = attribution(R)
    out['partner_attribution'] = acc
    out['partner_attribution_by_phase'] = detail
    print(json.dumps(out, indent=1, ensure_ascii=False))
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results_doubles.json'), 'w'), indent=1, ensure_ascii=False)
