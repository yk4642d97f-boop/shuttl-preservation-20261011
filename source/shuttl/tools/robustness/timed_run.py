#!/usr/bin/env python3
"""timed_run.py <timeout_s> <out.json> -- <cmd...>
Runs cmd in its own process group (meant to be launched INSIDE /tmp/heavy.sh so the lock
wait is not counted), kills the whole group on timeout, and writes one JSON record:
exit code / signal, wall seconds, child max RSS (MB), timed_out, last stdout line, stderr tail."""
import json, os, resource, signal, subprocess, sys, time

def main():
    timeout, out = float(sys.argv[1]), sys.argv[2]
    cmd = sys.argv[sys.argv.index('--') + 1:]
    t0 = time.monotonic()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    timed_out = False
    try:
        so, se = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(p.pid, signal.SIGKILL)
        so, se = p.communicate()
    wall = time.monotonic() - t0
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    lines = [l for l in (so or '').splitlines() if l.strip().startswith('{')]
    rec = {'exit': p.returncode, 'signal': -p.returncode if p.returncode and p.returncode < 0 else None,
           'timed_out': timed_out, 'timeout_s': timeout, 'wall_s': round(wall, 3),
           'max_rss_mb': round(ru.ru_maxrss / 1048576, 1), 'stdout_json': lines[-1] if lines else None,
           'stdout_tail': (so or '')[-3000:], 'stderr_tail': (se or '')[-6000:],
           'load1': round(os.getloadavg()[0], 1)}
    with open(out, 'w') as f:
        json.dump(rec, f, ensure_ascii=False)

if __name__ == '__main__':
    main()
