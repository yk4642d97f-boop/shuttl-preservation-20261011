"""Public validation video through real TLS/auth/upload/queue/GPU/archive, no private media."""
from pathlib import Path
import json,secrets,time,uuid,hashlib
import httpx
BASE='https://u1207069-82c4-95dc741d.westc.seetacloud.com:8443'
OUT=Path(__file__).resolve().parent
VIDEOS=OUT.parent/'cloud_runs/autodl_5090_20261008/integration-inputs'
row=json.loads((VIDEOS/'manifest.json').read_text())[1]
video=VIDEOS/row['file'];assert hashlib.sha256(video.read_bytes()).hexdigest()==row['sha256']
report={'base_url':BASE,'video_sha256':row['sha256'],'video_bytes':video.stat().st_size,'scope':'public validation clip with supplied court corners; detector training completed before this run','timings':{}}
client=httpx.Client(timeout=90,follow_redirects=False)
def call(method,path,**kwargs):
    response=client.request(method,BASE+path,**kwargs)
    if response.status_code>=400:raise RuntimeError(f'{method} {path.split("?")[0]}: {response.status_code} {response.text[:300]}')
    return response
assert client.get(BASE+'/matches/'+str(uuid.uuid4())).status_code==401
assert call('GET','/ready').json()['status']=='ready'
accounts=[]
for n in range(2):
    payload={'email':f'cloud-smoke-{uuid.uuid4().hex}@example.com','password':secrets.token_urlsafe(32),'nickname':'云端链路验证'}
    tokens=call('POST','/auth/register',json=payload).json()
    accounts.append({'Authorization':'Bearer '+tokens['access_token']})
headers=accounts[0];mid=str(uuid.uuid4());report['match_id']=mid
call('POST','/matches',headers=headers,json={'id':mid,'duration_seconds':5.37})
assert client.get(BASE+f'/matches/{mid}',headers=accounts[1]).status_code==404
upload=call('POST',f'/matches/{mid}/upload',headers=headers).json()['upload_url']
assert upload.startswith(BASE+'/matches/')
t=time.monotonic()
with video.open('rb') as stream:
    response=client.put(upload,content=stream,headers={'Content-Type':'video/mp4','Content-Length':str(video.stat().st_size)})
assert response.status_code==200,(response.status_code,response.text[:200])
report['timings']['upload_seconds']=time.monotonic()-t
job=call('POST',f'/matches/{mid}/analyze',headers=headers,json={'corners':row['corners'],'corners_normalized':True,'doubles':False}).json()['job_id']
report['job_id']=job;print('Uploaded public clip; GPU job submitted.',flush=True)
t=time.monotonic();last=None
while time.monotonic()-t<900:
    status=call('GET',f'/matches/{mid}/job/{job}',headers=headers).json()
    if status!=last:print(json.dumps(status,ensure_ascii=False),flush=True);last=status
    if status['state']=='FAILURE':raise RuntimeError(status)
    if status['state']=='SUCCESS':break
    time.sleep(3)
else:raise TimeoutError('job deadline')
report['timings']['queue_and_analysis_seconds']=time.monotonic()-t
t=time.monotonic();response=call('GET',f'/matches/{mid}/analysis/archive',headers=headers)
archive=response.json();report['timings']['archive_download_seconds']=time.monotonic()-t
assert archive['rallies'] and archive['track'] and archive['camera']
assert len(archive['meta']['timestamps'])==archive['meta']['n_frames']
assert all(stage['ok'] for stage in archive['diagnostics']['stages'].values())
assert client.get(BASE+f'/matches/{mid}/analysis/archive',headers=accounts[1]).status_code==404
report.update(processing_seconds=archive['processing_time_seconds'],frames=archive['meta']['n_frames'],rallies=len(archive['rallies']),hits=[h['frame'] for h in archive['hits']],archive_encoding=response.headers.get('content-encoding'),stages=archive['diagnostics']['stages'],passed=True)
(OUT/'https-smoke-archive.json').write_text(json.dumps(archive,ensure_ascii=False,allow_nan=False)+'\n')
(OUT/'https-smoke-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
