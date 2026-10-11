from pathlib import Path
import json,os,subprocess
import psycopg2
from psycopg2 import sql
B=Path('/root/autodl-tmp/shuttl-service')
secret=json.loads((B/'config/secrets.json').read_text())
with psycopg2.connect(host=str(B/'run/postgres'),port=5433,user='postgres',dbname='postgres') as db:
    db.autocommit=True
    with db.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname='shuttl'")
        if cur.fetchone() is None:cur.execute(sql.SQL('CREATE ROLE shuttl LOGIN PASSWORD {}').format(sql.Literal(secret['database'])))
# CREATE DATABASE must be outside even an implicit transaction.
db=psycopg2.connect(host=str(B/'run/postgres'),port=5433,user='postgres',dbname='postgres');db.autocommit=True
with db.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_database WHERE datname='shuttl'")
    if cur.fetchone() is None:cur.execute('CREATE DATABASE shuttl OWNER shuttl')
db.close()
subprocess.run([str(B/'env/bin/python'),str(B/'launch.py'),'-c','import asyncio;from app.core.database import create_tables;asyncio.run(create_tables())'],check=True)
subprocess.run(['/usr/sbin/nginx','-t','-c',str(B/'config/nginx.conf')],check=True)
p=B/'config/supervisor.conf';p.write_text(p.read_text().replace('autostart=false','autostart=true'))
for args in [('reread',),('update',),('status',)]:
    subprocess.run([str(B/'env/bin/python'),'-m','supervisor.supervisorctl','-c',str(p),*args],check=True)
print('Database initialized and all application services started.')
