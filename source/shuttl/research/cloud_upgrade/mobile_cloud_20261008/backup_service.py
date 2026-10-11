"""Make a verified, self-contained deployed-service snapshot without logging secrets."""
from pathlib import Path
import json,os,sys
B=Path('/root/autodl-tmp/shuttl-service');R=Path('/root/autodl-tmp/shuttl-5090-20261008/shuttl-runtime')
sys.path.insert(0,str(B/'app'))
from app.maintenance.recovery import Database,backup
values=json.loads((B/'config/environment.json').read_text())
config=B/'config/recovery.env'
config.write_text(''.join(f'{k}={v}\n' for k,v in values.items()));config.chmod(0o600)
result=backup(Database(values['DATABASE_URL']),B/'backups',B/'media',config,{
 'backend':B/'app/app','weights':R/'backend/ml/weights','models':R/'research/cloud_upgrade/artifacts','deployment':B/'config'})
(B/'backups/latest-snapshot.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
