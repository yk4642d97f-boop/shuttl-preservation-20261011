"""Exercise training, interruption/resume, freeze protection and split rejection locally."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OUT=HERE/'cloud_runs/bst_smoke';DATA=OUT/'data'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(args,ok=True):
 p=subprocess.run([sys.executable,str(HERE/'cloud/run_bst.py'),*args],cwd=ROOT,text=True,capture_output=True)
 if (p.returncode==0)!=ok:raise AssertionError(p.stdout+p.stderr)
 return p.stdout+p.stderr

def main():
 global HERE,ROOT,OUT,DATA
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--root',type=Path,default=ROOT)
 ap.add_argument('--device',choices=['cpu','cuda'],default='cpu')
 ap.add_argument('--out',type=Path)
 ap.add_argument('--report',type=Path)
 a=ap.parse_args()
 ROOT=a.root.resolve();HERE=ROOT/'research/cloud_upgrade'
 OUT=a.out.resolve() if a.out else HERE/'cloud_runs/bst_smoke';DATA=OUT/'data'
 if a.device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; refusing CPU fallback')
 report_path=a.report.resolve() if a.report else HERE/'cloud/bst_smoke.json'
 if report_path.exists():raise SystemExit('Smoke report exists; choose a new report path')
 if OUT.exists():raise SystemExit('Smoke output exists; do not overwrite')
 DATA.mkdir(parents=True)
 source=json.loads((HERE/'data/bst_fixed30/manifest.json').read_text())
 manifest={'classes':source['classes'],'splits':{},'purpose':'mechanics smoke only; not performance evidence'}
 for split,count in [('train',16),('val',8)]:
  with np.load(HERE/'data/bst_fixed30'/f'{split}.npz') as z:data={k:z[k][:count] for k in z.files}
  dest=DATA/f'{split}.npz';np.savez_compressed(dest,**data)
  manifest['splits'][split]={'file':dest.name,'sha256':sha(dest),'matches':sorted({n.split('/')[0] for n in data['name']})}
 (DATA/'manifest.json').write_text(json.dumps(manifest))
 init=HERE/'artifacts/bst_seq30/bst_CG_AP_JnB_bone_merged.pt'
 base=['train','--data',str(DATA/'manifest.json'),'--init',str(init),'--steps','6','--batch','4','--eval-every','3','--hours','.2','--device',a.device]
 reports={}
 reports['uninterrupted']=run([*base,'--out',str(OUT/'full')])
 reports['interrupted']=run([*base,'--out',str(OUT/'resumed'),'--stop-after','3'])
 reports['resumed']=run([*base,'--out',str(OUT/'resumed'),'--resume'])
 first=torch.load(OUT/'full/last.pt',map_location='cpu',weights_only=True)
 second=torch.load(OUT/'resumed/last.pt',map_location='cpu',weights_only=True)
 delta=max(float((first['state'][k]-second['state'][k]).abs().max()) for k in first['state'])
 assert delta==0 and first['step']==second['step']==6
 reports['freeze']=run(['freeze','--out',str(OUT/'resumed')])
 refused=run([*base,'--out',str(OUT/'resumed'),'--resume'],ok=False)
 assert 'Frozen run cannot' in refused
 # Reject hidden validation/test membership even with a valid file checksum.
 bad=json.loads(json.dumps(manifest));bad['splits']['train']=dict(bad['splits']['val'])
 (DATA/'leak.json').write_text(json.dumps(bad))
 leaked=list(base);leaked[leaked.index('--data')+1]=str(DATA/'leak.json')
 rejected=run([*leaked,'--out',str(OUT/'leak')],ok=False)
 assert 'Held-out match' in rejected
 history_equal=first['history']==second['history']
 assert history_equal, 'Resumed validation history changed'
 result={'device':a.device,'torch':torch.__version__,'steps':6,'interruption_after':3,'resumed_parameters_max_abs_error':delta,'validation_history_exact':history_equal,'frozen_retrain_refused':True,'held_out_training_refused':True,'scope':f'{a.device} training mechanics only; no quality claim','logs':reports}
 report_path.parent.mkdir(parents=True,exist_ok=True)
 report_path.write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k!='logs'})
if __name__=='__main__':main()
