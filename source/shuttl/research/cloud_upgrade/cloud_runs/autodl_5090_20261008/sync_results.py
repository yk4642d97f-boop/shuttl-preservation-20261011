"""Back up this experiment only; optionally wait for its finite pipeline to finish."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

HERE = Path(__file__).resolve().parent
BASE = '/root/autodl-tmp/shuttl-5090-20261008'
HOST = 'root@connect.westc.seetacloud.com'
SSH = ['ssh', '-S', '/Users/yangcong/.ssh/shuttl_5090_session/control',
       '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-p', '49996']
MAPPING = {'logs': 'logs', 'bst-first': 'bst-first', 'bst-comparison': 'bst-comparison',
           'integration-gpu': 'integration-gpu',
           'pose-eval/research/cloud_upgrade/pose_benchmark/results/full': 'pose-full',
           'shuttl-cloud/research/cloud_upgrade/cloud_runs': 'detectors'}

def remote_python(code):
    command = f'{BASE}/env/bin/python -'
    result = subprocess.run([*SSH, HOST, command], input=code, text=True,
                            capture_output=True, check=True, timeout=180)
    return json.loads(result.stdout)

def status():
    return remote_python(f'''
import json
from pathlib import Path
base=Path({BASE!r})
stage=(base/'logs/current-stage.txt').read_text().strip()
lines=(base/'logs/stages.log').read_text().splitlines()
markers=[line for line in lines if line.startswith(('START ', 'PASS ', 'FAILED '))]
log=base/'logs'/f'{{stage}}.log'
print(json.dumps(dict(stage=stage, last_event=markers[-1],
                     recent_log=log.read_text()[-1600:] if log.exists() else '')))
''')

def sync(final=False):
    destination = HERE / 'results'
    destination.mkdir(exist_ok=True)
    available = remote_python(f'''
import json
from pathlib import Path
print(json.dumps([name for name in {list(MAPPING)!r} if (Path({BASE!r})/name).exists()]))
''')
    for name in available:
        target = destination / MAPPING[name]
        target.mkdir(exist_ok=True)
        subprocess.run(['rsync', '-a', '--partial', '--exclude', 'cache/',
                        '-e', shlex.join(SSH), f'{HOST}:{BASE}/{name}/', str(target) + '/'],
                       check=True, timeout=600)
    if not final:
        return
    receipt = remote_python(f'''
import hashlib,json
from pathlib import Path
base=Path({BASE!r}); result={{}}
for name,target in {MAPPING!r}.items():
    root=base/name
    for path in sorted(root.rglob('*')):
        rel=path.relative_to(root)
        if not path.is_file() or 'cache' in rel.parts or path.name.endswith('.lock'):
            continue
        with path.open('rb') as handle: digest=hashlib.file_digest(handle,'sha256').hexdigest()
        result[str(Path(target)/rel)]=dict(bytes=path.stat().st_size,sha256=digest)
print(json.dumps(result))
''')
    for name, row in receipt.items():
        path = destination / name
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if path.stat().st_size != row['bytes'] or digest != row['sha256']:
            raise ValueError('Backup hash mismatch: ' + name)
    (destination / 'verified-backup.json').write_text(json.dumps(dict(
        verified_at_unix=time.time(), files=receipt, complete=True), indent=2) + '\n')
    print('Final backup verified:', len(receipt), 'files', flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    previous = None
    while True:
        report = status()
        (HERE / 'status.json').write_text(json.dumps(dict(checked_at_unix=time.time(), **report), indent=2) + '\n')
        terminal = report['stage'] == 'COMPLETE' or report['last_event'].startswith('FAILED ')
        if report['stage'] != previous or terminal or not args.watch:
            print(report['stage'], report['last_event'], flush=True)
            sync(final=terminal)
            previous = report['stage']
        if terminal or not args.watch:
            return
        time.sleep(45)

if __name__ == '__main__':
    main()
