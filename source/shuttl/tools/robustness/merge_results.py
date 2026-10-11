#!/usr/bin/env python3
"""raw/<clip>.<engine>.json -> results.csv (one row per corpus input, both engines).
Classes: CRASH, HANG, OOM, SILENT-EMPTY, IMPLAUSIBLE, OK; plus a PY/SWIFT DIVERGENCE column.
Python 'SILENT-EMPTY' = analyze_video returned 0 rallies with no failure; the server task
(tasks.py:71-79) would store it as status 'done'. Swift uses the app gate (MatchPipeline.swift:395-402)."""
import csv, json, pathlib

ROB = pathlib.Path(__file__).resolve().parent
EXTS = ('.mp4', '.mov', '.m4v', '.wav')
NON_COURT = {'content_black', 'content_white', 'content_random', 'empty', 'cut_moov', 'cut_mdat', 'audio_only',
             'real_audioonly'}
OOM_MB = 3000     # iPhone jetsam territory for a foreground app on 6 GB devices

def load(clip, engine):
    p = ROB / 'raw' / f'{clip}.{engine}.json'
    return json.loads(p.read_text()) if p.exists() else None

def classify(rec, engine, stem):
    if rec is None: return 'NOT_RUN', 'no raw result'
    st = rec['status']; r = rec.get('result') or {}
    if st == 'timeout': return 'HANG', f'killed after {rec["timeout_s"]:.0f} s'
    if st.startswith('crash'):
        return ('OOM' if rec.get('signal') == 9 else 'CRASH'), (rec.get('stderr_tail') or '')[-300:].replace('\n', ' | ')
    if rec.get('max_rss_mb', 0) > OOM_MB or (r.get('peak_footprint_mb') or 0) > OOM_MB:
        return 'OOM', f'peak {max(rec.get("max_rss_mb", 0), r.get("peak_footprint_mb") or 0):.0f} MB'
    if st == 'clean_failure':
        return 'OK', ('clear failure: ' + (r.get('app_message') if engine == 'swift' else r.get('error', '')))[:200]
    notes = []
    if r.get('implausible'): return 'IMPLAUSIBLE', '; '.join(r['implausible'])
    if r.get('camera') and stem in NON_COURT: return 'IMPLAUSIBLE', 'camera accepted on a scene without a court'
    if engine == 'swift':
        if r.get('rallies', 0) == 0 and r.get('app_done'): return 'SILENT-EMPTY', 'app would mark 0-rally match done'
        return 'OK', ('done: ' if r.get('app_done') else 'app failure: ') + (r.get('app_message') or '')
    if r.get('server_reason'):
        return 'OK', ('server clear failure: ' + r['server_reason'])[:200]
    if r.get('rallies', 0) == 0:
        return 'SILENT-EMPTY', 'returned 0 rallies, stages ok -> server stores status done'
    return 'OK', '; '.join(notes)

def divergence(a, b):
    if not a or not b: return ''
    ra, rb = a.get('result') or {}, b.get('result') or {}
    if a['status'] != 'returned' or b['status'] != 'returned':
        return '' if a['status'] == b['status'] else f'py {a["status"]} vs swift {b["status"]}'
    out = []
    for k in ('frames', 'camera', 'rallies'):
        if ra.get(k) != rb.get(k): out.append(f'{k} {ra.get(k)}/{rb.get(k)}')
    if abs((ra.get('hits') or 0) - (rb.get('hits') or 0)) > 1: out.append(f'hits {ra.get("hits")}/{rb.get("hits")}')
    fa, fb = ra.get('fps') or 0, rb.get('fps') or 0
    if fa and fb and abs(fa - fb) / max(fa, fb) > 0.05: out.append(f'fps {fa:.2f}/{fb:.2f}')
    return ('PY/SWIFT DIVERGENCE: ' + ', '.join(out)) if out else ''

FIELDS = ['clip', 'group', 'py_class', 'py_status', 'py_note', 'py_frames', 'py_fps', 'py_camera', 'py_visible', 'py_hits',
          'py_rallies', 'py_max_kmh', 'py_s', 'py_rss_mb', 'py_stage_failures',
          'swift_class', 'swift_status', 'swift_note', 'swift_frames', 'swift_fps', 'swift_camera', 'swift_visible',
          'swift_hits', 'swift_rallies', 'swift_max_kmh', 'swift_app_done', 'swift_s', 'swift_peak_mb', 'swift_stage_failures',
          'divergence']

def main():
    man = json.loads((ROB / 'corpus/manifest.json').read_text())
    groups = {c['file']: c['group'] for c in man['clips']}
    rows = []
    for p in sorted(x for x in (ROB / 'corpus').iterdir() if x.suffix.lower() in EXTS):
        row = {'clip': p.name, 'group': groups.get(p.name, '')}
        recs = {}
        for e, pre in (('py', 'py'), ('swift', 'swift')):
            rec = recs[e] = load(p.name, e); r = (rec or {}).get('result') or {}
            cls, note = classify(rec, e, p.stem)
            row.update({f'{pre}_class': cls, f'{pre}_status': (rec or {}).get('status', 'NOT_RUN'), f'{pre}_note': note,
                        f'{pre}_frames': r.get('frames', ''), f'{pre}_fps': round(r['fps'], 3) if r.get('fps') else '',
                        f'{pre}_camera': r.get('camera', ''), f'{pre}_visible': r.get('visible', ''),
                        f'{pre}_hits': r.get('hits', ''), f'{pre}_rallies': r.get('rallies', ''),
                        f'{pre}_max_kmh': round(r['max_speed_kmh'], 1) if r.get('max_speed_kmh') else (0 if r else ''),
                        f'{pre}_s': (rec or {}).get('wall_s', ''),
                        f'{pre}_stage_failures': ' | '.join(r.get('stage_failures') or [])[:300]})
        row['py_rss_mb'] = (recs['py'] or {}).get('max_rss_mb', '')
        row['swift_peak_mb'] = ((recs['swift'] or {}).get('result') or {}).get('peak_footprint_mb') or (recs['swift'] or {}).get('max_rss_mb', '')
        row['swift_app_done'] = ((recs['swift'] or {}).get('result') or {}).get('app_done', '')
        row['divergence'] = divergence(recs['py'], recs['swift'])
        rows.append(row)
    with (ROB / 'results.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    n = sum(1 for r in rows for k in ('py_class', 'swift_class') if r[k] == 'NOT_RUN')
    print(f'wrote {len(rows)} inputs to results.csv; NOT_RUN cells: {n}')

if __name__ == '__main__':
    main()
