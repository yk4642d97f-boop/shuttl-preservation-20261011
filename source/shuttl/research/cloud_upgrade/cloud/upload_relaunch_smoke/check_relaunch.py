"""Use a signed fixture app and a running loopback server to check actual process recovery.

Only the com.ycyangcong.shuttl.uploadsmoke test app is installed/removed or killed.
The simulator must already be booted. This never accesses the main Shuttl app's data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--simulator', required=True)
args = parser.parse_args()
folder = Path(__file__).resolve().parent
bundle = 'com.ycyangcong.shuttl.uploadsmoke'
app = folder / 'build/Build/Products/Debug-iphonesimulator/UploadRelaunchSmoke.app'
port = int((folder/'server-port.txt').read_text())

def sim(*parts, **kwargs):
    return subprocess.check_output(['xcrun', 'simctl', *parts], text=True, **kwargs).strip()

def wait_for(check, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(.1)
    raise TimeoutError('fixture did not reach required state')

def server_state():
    path = folder/'server-state.json'
    return json.loads(path.read_text()) if path.exists() else []

assert not server_state(), 'Start a fresh test server; preserving prior evidence instead of mixing runs'
subprocess.run(['xcrun', 'simctl', 'uninstall', args.simulator, bundle], capture_output=True)
sim('install', args.simulator, str(app))
launch_env = dict(os.environ, SIMCTL_CHILD_UPLOAD_SMOKE_URL=f'http://127.0.0.1:{port}/video')
first_launch = sim('launch', args.simulator, bundle, env=launch_env)
first_pid = int(first_launch.rsplit(':', 1)[1])
container = Path(sim('get_app_container', args.simulator, bundle, 'data'))
sources = ['ios/Sources/Services/Network/VideoUploadService.swift',
           'ios/Sources/Services/Network/UploadTransport.swift',
           'ios/Sources/Core/Storage/VideoStore.swift', 'ios/Sources/App/Orientation.swift']
report = {'first_pid': first_pid, 'first_launch': first_launch,
          'source_sha256': {name: hashlib.sha256((folder.parents[3]/name).read_bytes()).hexdigest() for name in sources}}
try:
    wait_for(lambda: server_state() and server_state()[0]['received'] >= 512 * 1024)
    command = subprocess.check_output(['ps', '-p', str(first_pid), '-o', 'command='], text=True).strip()
    assert '/UploadRelaunchSmoke.app/UploadRelaunchSmoke' in command, 'Refusing to signal an unrelated process'
    report['bytes_received_before_kill'] = server_state()[0]['received']
    os.kill(first_pid, signal.SIGKILL)
    print(f'Killed owned fixture pid={first_pid} during upload', flush=True)
    second_launch = sim('launch', args.simulator, bundle)
    report['second_launch'] = second_launch
    print(second_launch, flush=True)
    def result():
        path = container/'Documents/smoke.json'
        if path.exists():
            state = json.loads(path.read_text())
            if state.get('state') in {'done', 'failed'}:
                return state
        return None
    final = wait_for(result)
    report['app'] = final
    report['server'] = server_state()
    assert final['state'] == 'done', final
    assert final['launches'] == 2 and final['target_requests'] == 1, final
    assert len(report['server']) == 1 and report['server'][0]['done'], report['server']
    assert report['server'][0]['sha256'] == final['sha256']
    report['result'] = 'passed'
    print('PASS: two app processes; one target request; one complete 16 MiB PUT; matching SHA256', flush=True)
except BaseException as exc:
    report['result'] = 'failed'
    report['error'] = repr(exc)
    report['server'] = server_state()
    raise
finally:
    (folder/'relaunch-verification.json').write_text(json.dumps(report, indent=2)+'\n')
