"""Restore the new snapshot into a new isolated database/directory; never touch live data."""
from pathlib import Path
import json,sys,hashlib
import psycopg2
from psycopg2 import sql
B=Path('/root/autodl-tmp/shuttl-service');sys.path.insert(0,str(B/'app'))
from app.maintenance.recovery import Database,restore
values=json.loads((B/'config/environment.json').read_text())
meta=json.loads((B/'backups/latest-snapshot.json').read_text())
name='shuttl_restore_check_20261008'
admin=psycopg2.connect(host=str(B/'run/postgres'),port=5433,user='postgres',dbname='postgres');admin.autocommit=True
with admin.cursor() as cur:
    cur.execute(sql.SQL('CREATE DATABASE {} OWNER shuttl').format(sql.Identifier(name)))
admin.close()
dsn=values['DATABASE_URL'].rsplit('/',1)[0]+'/'+name
result=restore(Database(dsn),B/'backups',meta['snapshot'],B/'restore-check-20261008',redis_url='redis://127.0.0.1:6381/15')
with Database(dsn).connect() as db:
    with db.cursor() as cur:
        cur.execute('SELECT analysis,video_oss_key FROM matches ORDER BY created_at')
        rows=cur.fetchall();assert rows
        for row in rows:
            assert row['analysis']['mobile_archive']['rallies']
            video=B/'restore-check-20261008/media'/row['video_oss_key']
            assert video.is_file()
            assert hashlib.sha256(video.read_bytes()).hexdigest()=='a5f699d7e96d6bb315c6cc328d31624c346c826cb0268c9863a3feca1f2b868b'
result['restored_matches_verified']=len(rows)
(B/'logs/restore-rehearsal.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
