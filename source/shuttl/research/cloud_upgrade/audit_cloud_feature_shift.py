"""Attribute a validation integration failure by changing one input group at a time."""
from pathlib import Path
import sys,json
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'research/hitnet'))
import common as C
from app.services.tracking import hitnet

def main():
 torch.set_num_threads(4)
 model=hitnet.load(HERE/'artifacts/hitnet_single_v2.pt')
 reference=C.load_match('041')['rallies'][10]
 with np.load(HERE/'cloud_runs/runtime_integration/raw_inputs.npz') as z:cloud=z['raw'];fps=float(z['fps'])
 original=reference['raw']
 assert original.shape==cloud.shape
 arms={'reference':original,'cloud':cloud,
       'reference_shuttle_cloud_players':np.column_stack([original[:,:4],cloud[:,4:]]),
       'cloud_shuttle_reference_players':np.column_stack([cloud[:,:4],original[:,4:]]),
       'cloud_boxes_reference_feet_shuttle':np.column_stack([original[:,:4],cloud[:,4:12],original[:,12:]])}
 report={'match':'041','rally_index':10,'ground_truth_relative_frames':reference['hits'].tolist(),
         'scope':'single validation failure attribution; not candidate selection or an accuracy benchmark','arms':{},'feature_groups':{}}
 for name,raw in arms.items():
  logits=model.logits(raw,fps)
  pred=hitnet.core.decode_nms(hitnet.core.sigmoid(logits[:,0]),fps,.4,.3)
  report['arms'][name]={'relative_frames':list(map(int,pred)),'probability_at_gt':[float(hitnet.core.sigmoid(logits[int(i),0])) for i in reference['hits']]}
 for name,start,stop in [('shuttle',0,4),('boxes',4,12),('feet',12,16)]:
  x,y=original[:,start:stop],cloud[:,start:stop];mask=np.isfinite(x)&np.isfinite(y)
  report['feature_groups'][name]={'reference_finite_fraction':float(np.isfinite(x).mean()),'cloud_finite_fraction':float(np.isfinite(y).mean()),
                                'mean_abs_error_where_both_finite':float(np.abs(x[mask]-y[mask]).mean()) if mask.any() else None,
                                'reference_at_gt':x[reference['hits'].astype(int)].tolist(),'cloud_at_gt':y[reference['hits'].astype(int)].tolist()}
 def clean(x):
  if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
  if isinstance(x,list):return [clean(v) for v in x]
  if isinstance(x,float) and not np.isfinite(x):return None
  return x
 report=clean(report)
 (HERE/'cloud_feature_shift.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
