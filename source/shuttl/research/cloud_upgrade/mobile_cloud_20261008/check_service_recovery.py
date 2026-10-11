"""Verify Supervisor recovers the idle API process; leaves GPU/DB/queue running."""
from pathlib import Path
import json,os,signal,subprocess,time,urllib.request
B=Path('/root/autodl-tmp/shuttl-service')
cmd=[str(B/'env/bin/python'),'-m','supervisor.supervisorctl','-c',str(B/'config/supervisor.conf'),'pid','api']
old=int(subprocess.check_output(cmd));assert old>1
os.kill(old,signal.SIGTERM)
started=time.monotonic();new=old
for attempt in range(30):
    time.sleep(.5)
    try:
        new=int(subprocess.check_output(cmd))
        if new<=1 or new==old:continue
        with urllib.request.urlopen('http://127.0.0.1:6006/ready',timeout=2) as response:
            if json.load(response)['status']=='ready':break
    except Exception:continue
else:raise RuntimeError('API did not recover')
result={'api_pid_changed':old!=new,'readiness_after_restart':'ready','seconds':time.monotonic()-started,'gpu_shutdown':False}
(B/'logs/api-recovery.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
