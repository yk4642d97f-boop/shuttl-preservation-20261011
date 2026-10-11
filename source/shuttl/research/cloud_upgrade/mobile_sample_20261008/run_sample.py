"""Run the preselected public clip through the deployed HTTPS service."""
import hashlib
import json
from pathlib import Path
import secrets
import time
import uuid

import httpx

OUT = Path(__file__).resolve().parent
BASE = 'https://u1207069-82c4-95dc741d.westc.seetacloud.com:8443'
manifest = json.loads((OUT / 'manifest.json').read_text())
video = OUT / manifest['file']
assert hashlib.sha256(video.read_bytes()).hexdigest() == manifest['sha256']
client = httpx.Client(timeout=120)


def request(method, path, **kwargs):
    response = client.request(method, BASE + path, **kwargs)
    response.raise_for_status()
    return response


tokens = request('POST', '/auth/register', json={
    'email': f'cloud-smoke-{uuid.uuid4().hex}@example.com',
    'password': secrets.token_urlsafe(32), 'nickname': '公开回合验证',
}).json()
headers = {'Authorization': 'Bearer ' + tokens['access_token']}
mid = str(uuid.uuid4())
request('POST', '/matches', headers=headers,
        json={'id': mid, 'duration_seconds': manifest['duration_seconds']})
upload = request('POST', f'/matches/{mid}/upload', headers=headers).json()['upload_url']
started = time.monotonic()
with video.open('rb') as stream:
    response = client.put(upload, content=stream,
                          headers={'Content-Type': 'video/mp4', 'Content-Length': str(video.stat().st_size)})
response.raise_for_status()
upload_seconds = time.monotonic() - started
job = request('POST', f'/matches/{mid}/analyze', headers=headers,
              json={'doubles': False}).json()['job_id']
print('Public clip submitted with automatic court calibration.', flush=True)
started = time.monotonic()
last = None
while time.monotonic() - started < 900:
    status = request('GET', f'/matches/{mid}/job/{job}', headers=headers).json()
    if status != last:
        print(json.dumps(status, ensure_ascii=False), flush=True)
        last = status
    if status['state'] in ('SUCCESS', 'FAILURE'):
        break
    time.sleep(2)
else:
    raise TimeoutError('Analysis exceeded 900 seconds')
report = {'match_id': mid, 'job_id': job, 'video_sha256': manifest['sha256'],
          'client': 'computer HTTPS', 'calibration': 'automatic',
          'upload_seconds': upload_seconds,
          'analysis_and_poll_seconds': time.monotonic() - started, 'job': status}
(OUT / 'computer-run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
assert status['state'] == 'SUCCESS', status
archive = request('GET', f'/matches/{mid}/analysis/archive', headers=headers).json()
(OUT / 'computer-archive.json').write_text(json.dumps(archive, ensure_ascii=False, allow_nan=False) + '\n')
print(json.dumps({'processing_seconds': archive['processing_time_seconds'],
                  'hits': [h['frame'] for h in archive['hits']], 'rallies': len(archive['rallies']),
                  'has_camera': archive['camera'] is not None}, ensure_ascii=False), flush=True)
