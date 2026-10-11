"""Idempotent native deployment for the already-owned AutoDL instance; no shutdown."""
from pathlib import Path
import json, os, pwd, secrets, shutil, subprocess, sys
B=Path('/root/autodl-tmp/shuttl-service')
R=Path('/root/autodl-tmp/shuttl-5090-20261008')
PUBLIC='https://u1207069-82c4-95dc741d.westc.seetacloud.com:8443'
for name in ['config','logs','run','media','redis','backups']:(B/name).mkdir(exist_ok=True)
# Reuse validated CUDA libraries without replacing the model experiment environment.
site=B/'env/lib/python3.12/site-packages'
(site/'gpu-overlay.pth').write_text(str(R/'env/lib/python3.12/site-packages')+'\n')
# Both detector families and person weights remain in the verified runtime bundle.
ml=B/'app/ml';ml.mkdir(parents=True,exist_ok=True)
weights=ml/'weights'
if not weights.exists():weights.symlink_to(R/'shuttl-runtime/backend/ml/weights',target_is_directory=True)
credentials=B/'config/secrets.json'
if not credentials.exists():
    credentials.write_text(json.dumps({k:secrets.token_urlsafe(48) for k in ['database','jwt']}))
credentials.chmod(0o600)
secret=json.loads(credentials.read_text())
subprocess.run(['setfacl','-m','u:postgres:x','/root','/root/autodl-tmp',str(B)],check=True)
pg=B/'postgres';uid=pwd.getpwnam('postgres')
pg.mkdir(exist_ok=True);os.chown(pg,uid.pw_uid,uid.pw_gid);pg.chmod(0o700)
runpg=B/'run/postgres';runpg.mkdir(exist_ok=True);os.chown(runpg,uid.pw_uid,uid.pw_gid)
if not (pg/'PG_VERSION').exists():
    subprocess.run(['runuser','-u','postgres','--','/usr/lib/postgresql/14/bin/initdb','-D',str(pg),'--auth-host=reject','--auth-local=trust','--encoding=UTF8','--locale=C.UTF-8'],check=True)
(pg/'postgresql.auto.conf').write_text("listen_addresses = '127.0.0.1'\nport = 5433\nunix_socket_directories = '"+str(runpg)+"'\nshared_buffers = '256MB'\nmax_connections = 40\n")
# Local socket directory is PostgreSQL-owned; TCP always requires a password.
(pg/'pg_hba.conf').write_text('local all all trust\nhost all all 127.0.0.1/32 scram-sha-256\n')
art=R/'shuttl-runtime/research/cloud_upgrade/artifacts'
env={
 'DATABASE_URL':f"postgresql+asyncpg://shuttl:{secret['database']}@127.0.0.1:5433/shuttl",
 'REDIS_URL':'redis://127.0.0.1:6381/0','SECRET_KEY':secret['jwt'],
 'STORAGE_BACKEND':'local','MEDIA_DIR':str(B/'media'),'PUBLIC_BASE_URL':PUBLIC,
 'INFERENCE_DEVICE':'cuda','SHUTTL_WEIGHTS_DIR':str(weights),
 'SHUTTL_HITNET_WEIGHTS':str(art/'hitnet_single_v2.pt'),
 'SHUTTL_BST_MANIFEST':str(art/'bst_seq30/manifest.json'),
 'SHUTTL_RTMPOSE_WEIGHTS':str(art/'runtime/rtmpose_m_body7.onnx'),
 'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4','MKL_NUM_THREADS':'4',
 'PYTHONUNBUFFERED':'1','PYTHONPATH':str(B/'app'),
}
(B/'config/environment.json').write_text(json.dumps(env));(B/'config/environment.json').chmod(0o600)
(B/'launch.py').write_text('''import json,os,sys
from pathlib import Path
base=Path(__file__).resolve().parent
os.environ.update(json.loads((base/'config/environment.json').read_text()))
os.chdir(base/'app')
os.execv(str(base/'env/bin/python'),[str(base/'env/bin/python'),*sys.argv[1:]])
''')
(B/'config/redis.conf').write_text(f'bind 127.0.0.1\nprotected-mode yes\nport 6381\ndir {B}/redis\nappendonly yes\nappendfsync everysec\nmaxmemory 256mb\nmaxmemory-policy noeviction\nloglevel notice\n')
(B/'config/nginx.conf').write_text('''worker_processes 2;
pid BASE/run/nginx.pid;
error_log BASE/logs/nginx-error.log warn;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    server_tokens off;
    # $uri intentionally excludes signed upload tokens from logs.
    log_format safe '$time_iso8601 $request_method $uri $status $body_bytes_sent $request_time';
    access_log BASE/logs/nginx-access.log safe;
    client_body_temp_path BASE/run/nginx-body;
    proxy_temp_path BASE/run/nginx-proxy;
    sendfile on;
    keepalive_timeout 65;
    gzip on;
    gzip_types application/json;
    gzip_min_length 1024;
    gzip_vary on;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
    limit_req_status 429;
    server {
        listen 0.0.0.0:6006;
        server_name _;
        client_max_body_size 4096m;
        client_body_timeout 300s;
        add_header X-Content-Type-Options nosniff always;
        add_header Cache-Control "no-store" always;
        location ~ ^/(docs|redoc|openapi.json) { return 404; }
        location /auth/ {
            limit_req zone=auth burst=20 nodelay;
            include BASE/config/proxy.conf;
        }
        location / {
            include BASE/config/proxy.conf;
        }
    }
}
'''.replace('BASE',str(B)))
(B/'config/proxy.conf').write_text('''proxy_pass http://127.0.0.1:8000;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header Connection "";
proxy_request_buffering off;
proxy_buffering off;
proxy_connect_timeout 5s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;
''')
programs=[
 ('postgres',f'/usr/lib/postgresql/14/bin/postgres -D {pg}',10,'postgres'),
 ('redis',f'/usr/bin/redis-server {B}/config/redis.conf',10,'root'),
 ('api',f'{B}/env/bin/python {B}/launch.py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log',30,'root'),
 ('worker',f'{B}/env/bin/python {B}/launch.py -m celery -A app.worker.celery_app worker --loglevel=info --concurrency=1 --pool=solo',40,'root'),
 ('dispatcher',f'{B}/env/bin/python {B}/launch.py -m app.services.analysis_jobs dispatch',40,'root'),
 ('nginx',f'/usr/sbin/nginx -c {B}/config/nginx.conf -g "daemon off;"',50,'root'),
]
config=f'''[unix_http_server]
file={B}/run/supervisor.sock
chmod=0700
[supervisord]
logfile={B}/logs/supervisor.log
pidfile={B}/run/supervisor.pid
childlogdir={B}/logs
[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix://{B}/run/supervisor.sock
'''
for name,command,priority,user in programs:
    config+=f'''\n[program:{name}]
command={command}
user={user}
directory={B}/app
priority={priority}
autostart={'true' if name in ['postgres','redis'] else 'false'}
autorestart=true
startsecs=5
startretries=20
stopasgroup=true
killasgroup=true
stopwaitsecs=120
stdout_logfile={B}/logs/{name}.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=3
redirect_stderr=true
'''
(B/'config/supervisor.conf').write_text(config)
print('Service configuration prepared; credentials kept in private files.')
