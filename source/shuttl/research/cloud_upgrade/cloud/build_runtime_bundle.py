"""Allowlisted portable inference + BST experiment package; no private videos or credentials."""
from pathlib import Path
import argparse,hashlib,io,json,tarfile
ROOT=Path(__file__).resolve().parents[3]
HERE=ROOT/'research/cloud_upgrade'


def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 if a.output.exists():raise SystemExit('Choose a new output filename; existing bundles are immutable')
 paths=[ROOT/p for p in ['backend/app/__init__.py','backend/app/services/__init__.py',
   'backend/requirements-cloud-models.txt','backend/requirements-cloud-models-cuda.txt',
   'backend/ml/weights/ckpts/TrackNet_best.pt','backend/ml/weights/wasb_badminton_best.pth.tar',
   'backend/ml/weights/yolov8s-pose.pt']]
 paths += [p for p in (ROOT/'backend/app/services/tracking').rglob('*') if p.is_file() and (p.suffix in {'.py','.json'} or p.name=='LICENSE')]
 paths += [p for p in (HERE/'artifacts').rglob('*') if p.is_file() and (p.suffix in {'.pt','.json','.npz','.onnx'} or p.name=='LICENSE')]
 paths += list((HERE/'data/bst_fixed30').glob('*.npz'))+list((HERE/'data/bst_fixed30').glob('*.json'))
 paths += [HERE/p for p in ['cloud/run_inference.py','cloud/setup_inference.sh','cloud/requirements-inference.txt',
    'cloud/run_bst.py','cloud/build_runtime_bundle.py','cloud/runtime_smoke.json','cloud/runtime_integration.json','cloud/bst_smoke.json',
    'MODEL_CARD.md','MODEL_SURVEY.md','STROKE_CHAIN_REPORT.md','CLOUD_INFERENCE.md','PRE_GPU_READINESS.md','DOUBLE_DATA_PROTOCOL.md',
    'cloud_hitnet_parity.json','cloud_bst_parity.json','cloud_pose_parity.json','cloud_feature_shift.json',
    'cloud/runtime_integration_041_r69.json']]
 files=[]
 for p in sorted(set(paths)):
  if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(ROOT):raise ValueError(f'Unsafe/missing input: {p}')
  files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':digest(p)})
 manifest={'version':2,'scope':'CLI inference + BST train/validation preparation; not an API deployment','files':files}
 a.output.parent.mkdir(parents=True,exist_ok=True);tmp=a.output.with_suffix('.partial')
 with tarfile.open(tmp,'w:gz',compresslevel=1) as archive:
  for item in files:archive.add(ROOT/item['path'],arcname='shuttl-runtime/'+item['path'],recursive=False)
  raw=json.dumps(manifest,ensure_ascii=False,indent=2).encode();info=tarfile.TarInfo('shuttl-runtime/RUNTIME_MANIFEST.json');info.size=len(raw)
  archive.addfile(info,io.BytesIO(raw))
 tmp.replace(a.output)
 a.output.with_suffix(a.output.suffix+'.sha256').write_text(digest(a.output)+'  '+a.output.name+'\n')
 a.output.with_suffix(a.output.suffix+'.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'path':str(a.output),'bytes':a.output.stat().st_size,'files':len(files),'sha256':digest(a.output)},indent=2))
if __name__=='__main__':main()
