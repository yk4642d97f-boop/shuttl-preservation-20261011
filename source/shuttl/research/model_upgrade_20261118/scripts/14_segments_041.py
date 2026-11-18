"""ShuttleSet match 041 (HitNet's validation match) as rally segments with labelled hit frames."""
import csv, glob, hashlib, json, os
from pathlib import Path
base = Path('/root/autodl-tmp/shuttl-5090-20261008/pose-eval/research/shuttleset')
d = glob.glob(str(base / 'labels/ShuttleSet/set/Ng_Ka_Long*'))[0]
rallies = {}
for f in sorted(glob.glob(d + '/set*.csv')):
    s = int(os.path.basename(f)[3:-4])
    for r in csv.DictReader(open(f, encoding='utf-8')):
        fn = (r.get('frame_num') or '').strip()
        if not fn: continue
        rallies.setdefault((s, int(float(r['rally']))), []).append((int(float(fn)), r['type'], r['player']))
segs = []; prev = 0
for key in sorted(rallies, key=lambda k: min(x[0] for x in rallies[k])):
    hits = sorted(rallies[key]); a = max(prev, hits[0][0] - 30); b = hits[-1][0] + 31; prev = b
    segs.append(dict(id=hashlib.sha256(f'041|{key}'.encode()).hexdigest()[:20], set=key[0], rally=key[1], a=a, b=b,
                     hits=[dict(frame=f - a, types=[t], player=p) for f, t, p in hits]))
out = [dict(match='shuttleset-041', video='041.mp4', segments=segs)]
json.dump(out, open('/root/shuttl-claude-20261118/s041_segments.json', 'w'), ensure_ascii=False)
os.makedirs('/dev/shm/claude/s041/videos', exist_ok=True)
if not os.path.exists('/dev/shm/claude/s041/videos/041.mp4'): os.symlink(str(base / 'videos/041.mp4'), '/dev/shm/claude/s041/videos/041.mp4')
print('rallies', len(segs), 'hits', sum(len(s['hits']) for s in segs), 'frames', sum(s['b'] - s['a'] for s in segs))
