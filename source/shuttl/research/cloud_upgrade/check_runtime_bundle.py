"""Extract an allowlisted runtime archive elsewhere and run its own reference checks."""
from pathlib import Path
import hashlib,json,subprocess,sys,tarfile,tempfile
HERE=Path(__file__).resolve().parent

def main():
 archive=HERE/'dist/shuttl-cloud-runtime-v3.tar.gz'
 expected=archive.with_suffix(archive.suffix+'.sha256').read_text().split()[0]
 actual=hashlib.sha256(archive.read_bytes()).hexdigest()
 assert actual==expected
 with tempfile.TemporaryDirectory(prefix='shuttl-runtime-relocated-') as folder:
  with tarfile.open(archive) as tar:
   members=tar.getmembers()
   for m in members:
    if not m.isfile() and not m.isdir():raise ValueError('Links and special files forbidden')
    p=Path(m.name)
    if p.is_absolute() or '..' in p.parts or p.parts[0]!='shuttl-runtime':raise ValueError('Archive path escape')
   tar.extractall(folder,filter='data')
  root=Path(folder)/'shuttl-runtime'
  report=Path(folder)/'preflight.json'
  result=subprocess.run([sys.executable,str(root/'research/cloud_upgrade/cloud/run_inference.py'),'preflight','--report',str(report)],
                        cwd=root,text=True,capture_output=True,timeout=120)
  if result.returncode:raise RuntimeError(result.stdout+result.stderr)
  data=json.loads(report.read_text());assert data['bundle_verified']
  # All computation imports must resolve inside the relocated package.
  check=subprocess.run([sys.executable,'-c',
   "import sys,pathlib;sys.path.insert(0,'backend');from app.services.tracking import hitnet,bst,rtmpose;assert all(pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path.cwd()) for m in (hitnet,bst,rtmpose))"],cwd=root,capture_output=True,text=True)
  assert check.returncode==0,check.stderr
  data.update(archive_sha256=actual,relocated_imports=True,archive_bytes=archive.stat().st_size)
  (HERE/'dist/runtime_verification.json').write_text(json.dumps(data,indent=2)+'\n')
  print(json.dumps(data,indent=2))
if __name__=='__main__':main()
