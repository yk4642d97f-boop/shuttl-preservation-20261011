"""Local-only slow PUT server for observing an app-process restart during upload."""
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time

folder = Path(__file__).resolve().parent
lock = threading.Lock()
requests = []

def save():
    temporary = folder / 'server-state.tmp'
    temporary.write_text(json.dumps(requests, indent=2))
    temporary.replace(folder / 'server-state.json')

class Handler(BaseHTTPRequestHandler):
    def do_PUT(self):
        total = int(self.headers['Content-Length'])
        if self.path != '/video' or not 0 < total <= 20 * 1024 * 1024:
            self.send_error(400); return
        record = {'expected': total, 'received': 0, 'done': False}
        digest = hashlib.sha256()
        with lock:
            requests.append(record); save()
        try:
            while record['received'] < total:
                chunk = self.rfile.read(min(64 * 1024, total - record['received']))
                if not chunk:
                    raise ConnectionError('client disconnected')
                digest.update(chunk)
                with lock:
                    record['received'] += len(chunk)
                    if record['received'] % (512 * 1024) == 0:
                        save()
                time.sleep(.05)
            with lock:
                record.update(done=True, sha256=digest.hexdigest()); save()
            self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers()
        except Exception as exc:
            with lock:
                record['error'] = type(exc).__name__; save()
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
(folder / 'server-port.txt').write_text(str(server.server_port))
print(f'loopback server port={server.server_port}', flush=True)
server.serve_forever()
