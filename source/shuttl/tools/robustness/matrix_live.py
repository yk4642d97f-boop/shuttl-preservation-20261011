#!/usr/bin/env python3
"""Real-pipeline cancellation / resume / checkpoint-corruption matrix (Swift app path).
Driver = RobustnessDriver analyze: LiveStages + AnalysisPipeline + the app's FileCheckpointStore
(same fingerprint function), cancelled with a real Task.cancel() from another task.
Phases: reference x2 (determinism) · cancel in every stage at seeded random offsets, resume ·
cancel after the Nth detect-partial save, resume, double interruption · mutate every checkpoint
file (truncate / empty / bit flips / valid-JSON edits / fingerprint / structure), resume.
Run: /tmp/heavy.sh T10-matrix env T10_IN_HEAVY=1 backend/.venv/bin/python tools/robustness/matrix_live.py
Out: tools/robustness/matrix_live.jsonl (one row per case) + matrix_live.csv."""
import json, os, pathlib, random, shutil, subprocess, sys

ROB = pathlib.Path(__file__).resolve().parent; ROOT = ROB.parents[1]
PY = str(ROOT / 'backend/.venv/bin/python'); DRV = '/tmp/luna10/driver/release/RobustnessDriver'
CLIP = str(ROB / 'corpus/real_reencode.mp4')
W = pathlib.Path('/tmp/luna10/matrix'); OUT = ROB / 'matrix_live.jsonl'
STAGES = ['detect', 'link', 'calibrate', 'players', 'hits', 'reconstruct3d', 'rallies', 'shots', 'score']
rng = random.Random(81010)

def drive(*args, timeout=240):
    tmp = W / 'timed.json'
    subprocess.run([PY, str(ROB / 'timed_run.py'), str(timeout), str(tmp), '--', DRV, 'analyze', CLIP, *args], check=False)
    rec = json.loads(tmp.read_text())
    res = json.loads(rec['stdout_json']) if rec.get('stdout_json') else {}
    status = 'timeout' if rec['timed_out'] else f'crash(signal {rec["signal"]})' if rec['signal'] else res.get('status', 'no-output')
    return status, res, rec

def resumed_stages(res):
    return sorted(k for k, v in (res.get('stages') or {}).items() if isinstance(v, dict) and v.get('resumed'))

def diff(res, ref):
    a, b = res.get('signature') or {}, ref['signature']
    return sorted(k for k in b if k != 'all' and a.get(k) != b[k])

def row(**kw):
    with OUT.open('a') as f: f.write(json.dumps(kw, ensure_ascii=False) + '\n')
    print(json.dumps(kw, ensure_ascii=False)[:400], flush=True)

def fresh(name):
    d = W / name; shutil.rmtree(d, ignore_errors=True); return d

def verdict_after(status, res, ref):
    if status != 'returned': return 'NON_OK:' + status
    return 'EQUAL' if res['signature']['all'] == ref['signature']['all'] else 'DIFFERENT:' + ','.join(diff(res, ref))

def reference():
    s1, r1, _ = drive(); s2, r2, _ = drive()
    assert s1 == s2 == 'returned', (s1, s2, r1, r2)
    det = r1['signature']['all'] == r2['signature']['all']
    row(phase='reference', case='uninterrupted x2', result='DETERMINISTIC' if det else 'NON_DETERMINISTIC',
        signature=r1['signature']['all'], stages={k: v.get('seconds') for k, v in r1['stages'].items()},
        hits=r1['hits'], rallies=r1['rallies'], camera=r1['camera'])
    return r1

def cancel_matrix(ref, per_stage=3):
    for st in STAGES:
        secs = (ref['stages'].get(st) or {}).get('seconds', 0.01)
        for k in range(per_stage):
            ms = [0, int(rng.uniform(0.2, 0.9) * secs * 1000), int(rng.uniform(0, 1.2) * secs * 1000)][k]
            d = fresh(f'cancel-{st}-{k}')
            s, r, rec = drive('--store', str(d), '--cancel-stage', st, '--cancel-ms', str(ms))
            files = sorted(p.name for p in d.iterdir()) if d.exists() else []
            s2, r2, _ = drive('--store', str(d))
            row(phase='cancel', case=f'{st}+{ms}ms', first=s, cancel_latency_s=r.get('cancel_latency_s'),
                thrown_in=r.get('stage_when_thrown'), cancel_ignored=r.get('cancel_ignored', False),
                checkpoints_left=files, resume=s2, resumed=resumed_stages(r2), result=verdict_after(s2, r2, ref),
                store_cleared_after_resume=not d.exists())

def partial_matrix(ref):
    for n in (1, 2):
        d = fresh(f'partial-{n}')
        s, r, _ = drive('--store', str(d), '--checkpoint-s', '0.5', '--cancel-after-partial', str(n))
        files = sorted(p.name for p in d.iterdir()) if d.exists() else []
        s2, r2, _ = drive('--store', str(d), '--checkpoint-s', '0.5')
        row(phase='detect_partial', case=f'cancel after partial save #{n}', first=s, cancel_at=r.get('cancel_at'),
            checkpoints_left=files, resume=s2, resume_offered=(r2.get('stages') or {}).get('detect', {}).get('resume_offered_frame'),
            result=verdict_after(s2, r2, ref))
    d = fresh('double')
    s1, r1, _ = drive('--store', str(d), '--checkpoint-s', '0.5', '--cancel-after-partial', '1')
    s2, r2, _ = drive('--store', str(d), '--checkpoint-s', '0.5', '--cancel-after-partial', '1')
    s3, r3, _ = drive('--store', str(d), '--cancel-stage', 'players', '--cancel-ms', '300')
    s4, r4, _ = drive('--store', str(d))
    row(phase='double_interrupt', case='partial#1 -> partial#1 again -> players+300ms -> resume',
        runs=[s1, s2, s3, s4], cancel_points=[r1.get('cancel_at'), r2.get('cancel_at'), r3.get('cancel_at')],
        resumed=resumed_stages(r4), result=verdict_after(s4, r4, ref))

# ---- checkpoint mutation -------------------------------------------------------------
def flip(b, i, bit):  b = bytearray(b); b[i] ^= 1 << bit; return bytes(b)

def edit_first_number(key, new):
    """Valid-JSON semantic edit: replace the first number that follows "key": (possibly nested
    in arrays) with `new`. Returns a mutator for the file text."""
    import re
    def m(data):
        s = data.decode(); i = s.index(f'"{key}"') + len(key) + 2
        mt = re.compile(r'-?\d+(\.\d+)?([eE][-+]?\d+)?').search(s, i)
        return (s[:mt.start()] + new + s[mt.end():]).encode()
    return m

def json_edit(fn):
    def m(data): o = json.loads(data); fn(o); return json.dumps(o).encode()
    return m

def players_count(v):
    """players.bin header: 'SHPO' u16 ver u16 flags u32 fpLen fp u64 count (little endian)."""
    import struct
    def m(b):
        fl = struct.unpack('<I', b[8:12])[0]; o = 12 + fl; c = struct.unpack('<Q', b[o:o + 8])[0]
        return b[:o] + struct.pack('<Q', v if v is not None else max(c - 1, 0)) + b[o + 8:]
    return m

def mutations(files):
    out = []
    for f in files:
        out += [(f, 'truncate_half', lambda b: b[:len(b) // 2]), (f, 'empty', lambda b: b'')]
        for seed in range(4):
            out.append((f, f'bitflip_seed{seed}', lambda b, s=seed: flip(b, random.Random(s).randrange(len(b)), random.Random(s + 99).randrange(8))))
        if f.endswith('.json'):
            out.append((f, 'wrong_fingerprint', json_edit(lambda o: o.__setitem__('fingerprint', 'v2-deadbeef'))))
            out.append((f, 'value_wrong_type', json_edit(lambda o: o.__setitem__('value', {'bogus': 1}))))
    out += [
        ('candidates.json', 'valid_json_x_shift', edit_first_number('x', '999.5')),
        ('track.json', 'valid_json_xy_null', json_edit(lambda o: o['value']['xy'].__setitem__(0, None))),
        ('track.json', 'valid_json_len_mismatch', json_edit(lambda o: o['value']['xy'].pop())),
        ('track.json', 'valid_json_visible_all_false', json_edit(lambda o: o['value'].__setitem__('visible', [False] * len(o['value']['visible'])))),
        ('camera.json', 'valid_json_t_edit', json_edit(lambda o: o['value'].__setitem__('t', [v + 3.0 for v in o['value']['t']]))),
        ('camera.json', 'valid_json_K_nan', json_edit(lambda o: o['value']['K'][0].__setitem__(0, None))),
        ('camera.json', 'valid_json_t_two_values', json_edit(lambda o: o['value']['t'].pop())),
        ('camera.json', 'valid_json_K_two_rows', json_edit(lambda o: o['value']['K'].pop())),
        ('camera.json', 'valid_json_size_zero', json_edit(lambda o: o['value'].__setitem__('image_size', [0, 0]))),
        ('players.bin', 'count_huge', players_count(2**40)),
        ('players.bin', 'count_minus_one', players_count(None)),
        ('candidates.json', 'directory_in_place', None),
    ]
    return out

def run_mutations(ref, pristine, label):
    files = sorted(p.name for p in pristine.iterdir() if p.is_file())
    for fname, name, fn in mutations(files):
        if fname not in files and name != 'directory_in_place': continue
        d = fresh(f'mut-{label}'); shutil.copytree(pristine, d)
        p = d / fname
        try:
            if name == 'directory_in_place': p.unlink(missing_ok=True); p.mkdir()
            else: p.write_bytes(fn(p.read_bytes()))
        except Exception as e:
            row(phase='mutate', store=label, file=fname, case=name, result=f'SKIPPED (mutator: {e})'); continue
        extra = ['--checkpoint-s', '0.5'] if label == 'partial' else []
        s, r, rec = drive('--store', str(d), *extra)
        row(phase='mutate', store=label, file=fname, case=name, resume=s, resumed=resumed_stages(r),
            result=verdict_after(s, r, ref), app_done=r.get('app_done'), hits=r.get('hits'), rallies=r.get('rallies'),
            implausible=r.get('implausible'), detect_resume=(r.get('stages') or {}).get('detect', {}).get('resume_offered_frame'),
            stderr=(rec.get('stderr_tail') or '')[-600:] if s != 'returned' else '')

def mutate_matrix(ref):
    pristine = fresh('pristine-full'); d = fresh('snap-src')
    s, r, _ = drive('--store', str(d), '--snapshot-at', 'score', str(pristine))
    row(phase='mutate', case='snapshot before finish()', files=sorted(p.name for p in pristine.iterdir()), first=s)
    run_mutations(ref, pristine, 'full')
    part = fresh('pristine-partial'); d = fresh('snap-part')
    drive('--store', str(d), '--checkpoint-s', '0.5', '--cancel-after-partial', '2')
    shutil.copytree(d, part)
    row(phase='mutate', case='partial snapshot', files=sorted(p.name for p in part.iterdir()))
    run_mutations(ref, part, 'partial')

def rebuild_driver():
    """Rebuild inside the heavy slot so the matrix always tests the current package sources."""
    log = pathlib.Path('/tmp/luna10/drvbuild-matrix.log')
    with log.open('w') as f:
        rc = subprocess.run(['swift', 'build', '-c', 'release', '-j', '2', '--scratch-path', '/tmp/luna10/driver'],
                            cwd=ROB / 'driver', stdout=f, stderr=subprocess.STDOUT).returncode
    row(phase='build', case='driver rebuild', result='OK' if rc == 0 else f'FAILED rc={rc} (see {log})',
        driver_mtime=os.path.getmtime(DRV) if os.path.exists(DRV) else None)
    if rc != 0: sys.exit(rc)

def main():
    W.mkdir(parents=True, exist_ok=True)
    if '--keep' not in sys.argv: OUT.write_text('')
    if '--no-build' not in sys.argv: rebuild_driver()
    ref = reference()
    phases = [a for a in sys.argv[1:] if not a.startswith('--')] or ['cancel', 'partial', 'mutate']
    if 'cancel' in phases: cancel_matrix(ref)
    if 'partial' in phases: partial_matrix(ref)
    if 'mutate' in phases: mutate_matrix(ref)

if __name__ == '__main__':
    main()
