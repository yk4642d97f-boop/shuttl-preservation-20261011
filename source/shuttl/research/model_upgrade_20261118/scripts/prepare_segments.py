"""Build the rally-segment manifests the GPU extractors read, from the locally acquired public datasets.

The manifests themselves are not kept in the repository (they restate third-party annotations);
this script regenerates them from the original downloads:

  python3 prepare_segments.py vb    --audit-root .../training-data-audit-20261101 --out DIR
  python3 prepare_segments.py bfmd  --audit-root .../training-data-audit-20261101 --out DIR
  python3 prepare_segments.py fineb --audit-root .../training-data-audit-20261101 --out DIR

vb    -> vb_queue.json (one row per curated clip) and vb_segments.json (frame-contiguous clips chained into rallies)
bfmd  -> bfmd_segments.json (manual Rally ranges +/-20 frames, typed hit frames)
fineb -> fineb_segments.json (rally intervals +/-20 frames; stroke action-interval starts, mapped type sets, hitter side)
"""
import argparse, collections, glob, hashlib, json, os
from pathlib import Path


def vb(root, out):
    rows = [json.loads(l) for l in open(root / 'downloads/videobadminton/curated-candidates.jsonl')]
    q = []
    for r in rows:
        f = r['raw_filename_fields']
        q.append(dict(id=r['sha256'][:24], sha256=r['sha256'], zip_member=r['archive_path'], raw_class=r['raw_class'], class_id=r['class_id'],
                      date=r['split_group'], session=r['source_session_group'], recording=r['source_recording_group'],
                      player=f.get('player'), start=int(f['start']), end=int(f['end']), clip=f.get('clip'), set=f.get('set'),
                      fps=r['fps'], frames=r['decoded_frames'], width=r['width'], height=r['height']))
    q.sort(key=lambda r: r['sha256'])
    assert len({r['id'] for r in q}) == len(q)
    json.dump(q, open(out / 'vb_queue.json', 'w'))
    by = collections.defaultdict(list)
    for r in q: by[r['recording']].append(r)
    segs = []
    for rec, items in sorted(by.items()):
        items.sort(key=lambda r: (r['start'], r['end'])); cur = [items[0]]
        for a, b in zip(items, items[1:]):
            if b['start'] == a['end']: cur.append(b)          # the next clip starts on the frame this one ends: same rally
            else: segs.append(cur); cur = [b]
        segs.append(cur)
    res = []
    for s in segs:
        sid = hashlib.sha256('|'.join(c['id'] for c in s).encode()).hexdigest()[:20]
        res.append(dict(id=sid, recording=s[0]['recording'], session=s[0]['session'], date=s[0]['date'], fps=s[0]['fps'],
                        frames=sum(c['frames'] for c in s), start=s[0]['start'], end=s[-1]['end'],
                        clips=[dict(id=c['id'], zip_member=c['zip_member'], start=c['start'], end=c['end'], frames=c['frames'],
                                    raw_class=c['raw_class'], class_id=c['class_id'], player=c['player']) for c in s]))
    res.sort(key=lambda s: -s['frames'])
    json.dump(res, open(out / 'vb_segments.json', 'w'))
    print('clips', len(q), 'segments', len(res), 'frames', sum(s['frames'] for s in res))


def bfmd(root, out):
    B = root / 'downloads/bfmd-round3'
    TYPES = {'serve', 'flick_serve', 'net_shot', 'lift', 'smash', 'block', 'drive', 'push', 'drop', 'clear', 'press', 'net_kill'}
    res = []
    for f in sorted(glob.glob(str(B / 'shot_type/*.json'))):
        name = os.path.basename(f)[:-5]
        ev = [(rg['start'], rg['end'], lab) for r in json.load(open(f))['annotations'][0]['result'] for rg in r['value']['ranges'] for lab in r['value']['timelinelabels']]
        rallies = sorted((s, e) for s, e, l in ev if l == 'Rally'); hits = sorted(s for s, e, l in ev if l == 'hit')
        typ = collections.defaultdict(list)
        for s, e, l in ev:
            if l in TYPES: typ[s].append(l)
        court = json.load(open(B / f'court/{name}_court.json'))
        meta = json.load(open(B / f'metadata/{name}.json')); meta = meta[0] if isinstance(meta, list) else meta
        segs = []; prev_b = 0
        for ri, (s, e) in enumerate(rallies):
            hs = [h for h in hits if s - 3 <= h <= e + 3]
            if not hs: continue
            a = max(prev_b, min(s, hs[0]) - 20); b = max(e, hs[-1]) + 21; prev_b = b
            segs.append(dict(id=hashlib.sha256(f'{name}|{s}|{e}'.encode()).hexdigest()[:20], rally=ri, a=a, b=b, start=s, end=e,
                             hits=[dict(frame=h - a, types=sorted(typ[h])) for h in hs]))
        res.append(dict(match=name, video=name + '.mp4', court=court['court'], net=court['net'], game1_top_player=meta.get('game1_top_player'),
                        games={g: [(r['start'], r['end']) for r in v['rallies']] for g, v in meta['games'].items()}, segments=segs))
    json.dump(res, open(out / 'bfmd_segments.json', 'w'))
    print('matches', len(res), 'rallies', sum(len(m['segments']) for m in res), 'hits', sum(len(s['hits']) for m in res for s in m['segments']))


def fineb(root, out):
    A = root / 'ingestion/artifacts'
    R = {}
    for l in open(A / 'rallies.jsonl'):
        r = json.loads(l); rr = r['raw_rally']
        R[r['rally_id']] = dict(video=rr['video'], fps=rr.get('fps'), start=rr.get('start_frame'), end=rr.get('end_frame'), hits=[])
    for l in open(A / 'samples.jsonl'):
        s = json.loads(l); iv = s['interval']; lab = s['labels']
        R[s['rally_id']]['hits'].append(dict(start=iv['start'], type=lab['hit_type'], subtype=lab['subtype'], hitter=lab['hitter']))
    MAP = {'push shot': ['push', 'lift'], 'kill': ['smash'], 'net shot': ['net'], 'block': ['block'], 'drive': ['drive'], 'drop shot': ['drop'], 'clear': ['clear'],
           'net lift': ['lift'], 'cross-court net shot': ['cross_net'], 'net kill': ['kill']}
    by = collections.defaultdict(list)
    for rid, r in R.items():
        if r['start'] is None or r['end'] is None or not r['hits']: continue
        a = max(0, r['start'] - 20); b = r['end'] + 21; hits = []
        for h in r['hits']:
            if h['start'] is None or not (r['start'] - 2 <= h['start'] <= r['end'] + 2): continue
            if h['type'] == 'serve':
                st = h['subtype'] or []
                allowed = ['short_serve'] if 'short serve' in st else (['long_serve'] if ('high serve' in st or 'flick serve' in st) else ['short_serve', 'long_serve'])
            else: allowed = MAP.get(h['type'], [])
            hits.append(dict(frame=h['start'] - a, types=[h['type']], allowed=allowed, side={'top': 0, 'bottom': 1}.get(h['hitter'], -1)))
        if hits: by[r['video']].append(dict(id=hashlib.sha256(rid.encode()).hexdigest()[:20], a=a, b=b, fps=r['fps'] or 30.0, hits=hits))
    res = []
    for v, segs in sorted(by.items()):
        segs.sort(key=lambda s: s['a']); keep = []; prev = 0
        for s in segs:
            if s['a'] < prev: s['a'] = prev
            if s['b'] - s['a'] < 10 or any(h['frame'] < 0 for h in s['hits']): continue
            keep.append(s); prev = s['b']
        res.append(dict(match='fineb-' + v[:-4], video=v, segments=keep))
    json.dump(res, open(out / 'fineb_segments.json', 'w'))
    print('videos', len(res), 'rallies', sum(len(m['segments']) for m in res), 'hits', sum(len(s['hits']) for m in res for s in m['segments']))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('dataset', choices=['vb', 'bfmd', 'fineb'])
    ap.add_argument('--audit-root', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    {'vb': vb, 'bfmd': bfmd, 'fineb': fineb}[a.dataset](a.audit_root, a.out)
