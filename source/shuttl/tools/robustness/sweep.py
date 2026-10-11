#!/usr/bin/env python3
"""Every corpus clip through Python pipeline_v2 and the Swift app pipeline, one heavy job at a
time via /tmp/heavy.sh (lock wait NOT counted in the timeout: timed_run.py runs inside it).
Results: raw/<clip>.<engine>.json. Resumable: existing results are kept unless --force.
Batch: /tmp/heavy.sh T10-sweep env T10_IN_HEAVY=1 python sweep.py (one lock for all).
Usage: sweep.py [--force] [--only substr] [--engine py|swift]"""
import json, os, pathlib, subprocess, sys
import cv2

ROB = pathlib.Path(__file__).resolve().parent; ROOT = ROB.parents[1]
CORP, RAW = ROB / 'corpus', ROB / 'raw'
PY = ROOT / 'backend/.venv/bin/python'; SWIFT = '/tmp/luna10/driver/release/RobustnessDriver'
EXTS = ('.mp4', '.mov', '.m4v', '.wav')

def seconds_of(p):
    c = cv2.VideoCapture(str(p)); n = c.get(cv2.CAP_PROP_FRAME_COUNT) or 0; f = c.get(cv2.CAP_PROP_FPS) or 30; c.release()
    return n / f if f > 0 else 0

def run(clip, engine, force):
    out = RAW / f'{clip.name}.{engine}.json'
    if out.exists() and not force: return json.loads(out.read_text())
    dur = seconds_of(clip)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2',
               NUMBA_CACHE_DIR='/tmp/luna10/numba', YOLO_CONFIG_DIR='/tmp/luna10/yolo', MPLCONFIGDIR='/tmp/luna10/mpl',
               PYTHONPATH=str(ROOT / 'backend'), SHUTTL_STAGE_METRICS=f'/tmp/luna10/metrics/{clip.name}.jsonl')
    if engine == 'py':
        timeout, cmd = 300 + 30 * dur, [str(PY), str(ROB / 'python_one.py'), str(clip)]
    else:
        timeout, cmd = 180 + 10 * dur, [SWIFT, 'analyze', str(clip)]
    os.makedirs('/tmp/luna10/metrics', exist_ok=True)
    tmp = f'/tmp/luna10/timed-{clip.name}.{engine}.json'
    inner = [str(PY), str(ROB / 'timed_run.py'), str(int(timeout)), tmp, '--', *cmd]
    # Inside a batch that already holds the heavy lock (run_all.sh) run directly; else queue.
    wrap = [] if os.environ.get('T10_IN_HEAVY') == '1' else ['/tmp/heavy.sh', f'T10-{engine}-{clip.stem}']
    subprocess.run(wrap + inner, cwd=ROOT / 'backend', env=env, check=False)
    rec = json.loads(pathlib.Path(tmp).read_text()); os.unlink(tmp)
    res = json.loads(rec['stdout_json']) if rec.get('stdout_json') else {}
    rec['result'] = res
    rec['status'] = ('timeout' if rec['timed_out'] else f'crash(signal {rec["signal"]})' if rec['signal']
                     else res.get('status') or f'crash(exit {rec["exit"]}, no result)')
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    return rec

def main():
    a = sys.argv[1:]; force = '--force' in a
    only = a[a.index('--only') + 1] if '--only' in a else ''
    engines = [a[a.index('--engine') + 1]] if '--engine' in a else ['py', 'swift']
    RAW.mkdir(exist_ok=True)
    for clip in sorted(p for p in CORP.iterdir() if p.suffix.lower() in EXTS and only in p.name):
        for e in engines:
            r = run(clip, e, force)
            res = r.get('result', {})
            print(f'{clip.name:28s} {e:5s} {r["status"]:14s} {r["wall_s"]:7.1f}s rss {r["max_rss_mb"]:7.1f}MB '
                  f'cam={res.get("camera")} hits={res.get("hits")} rallies={res.get("rallies")} '
                  f'app_done={res.get("app_done")} imp={res.get("implausible")}', flush=True)

if __name__ == '__main__':
    main()
