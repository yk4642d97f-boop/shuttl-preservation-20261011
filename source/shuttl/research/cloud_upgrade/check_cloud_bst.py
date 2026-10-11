"""Production feature/model parity with the frozen BST reference on validation 041."""
from pathlib import Path
import sys,json
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import stroke_chain as reference
from app.services.tracking import bst
from app.services.tracking.data_types import Track2D,VideoMeta,PlayerObservation

def main():
 torch.set_num_threads(4)
 frames=reference.MatchFrames('041');d=frames.data
 with np.load(ROOT/'research/rtmpose/pose/041.npz') as z:
  kp,box=z['kp'],z['box']
 n=len(d['frame']);ts=d['t']
 track=Track2D(ts,d['shuttle_xy'],d['shuttle_conf'],d['shuttle_visible'],d['shuttle_interp'])
 meta=VideoMeta(float(d['fps']),int(d['width']),int(d['height']),n,ts)
 players=[PlayerObservation(i,p+1,box[i,p],1.,side,d['player_foot_world'][i,p],kp[i,p]) for i in range(n) for p,side in enumerate(('far','near'))]
 arrays=bst.frame_features(track,meta,players)
 for actual,expected in zip(arrays,(frames.joints,frames.pos,frames.shuttle,frames.covered,frames.resolved)):
  np.testing.assert_array_equal(actual,expected,strict=True)
 clips=[]
 for f in d['rally_hit_frames'][::max(1,len(d['rally_hit_frames'])//20)]:
  clip,reason=frames.raw_clip(int(f))
  if clip is not None: clips.append(clip)
 expected_inputs=[]
 for clip in clips:
  data,n_valid=reference.B.model_inputs(*clip)
  expected_inputs.append((reference.B.reference_jnb(data['joints'][0]).reshape(30,2,72),data['shuttle'][0],data['pos'][0],n_valid))
 for actual,expected in zip(bst.model_inputs(clips),[np.stack(a) for a in zip(*expected_inputs)]):
  np.testing.assert_array_equal(actual,expected,strict=True)
 model=bst.load(HERE/'artifacts/bst_seq30/manifest.json')
 actual=model.logits(clips)
 expected=reference.classify(clips,'cpu')
 np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-6)
 report={'match':'041','frames':len(d['frame']),'clips':len(clips),'raw_features_exact':True,'model_inputs_exact':True,'max_abs_logit_error':float(np.abs(actual-expected).max()),'classes_exact':bool(np.array_equal(actual.argmax(1),expected.argmax(1))),'ensemble_members':len(model.nets),'manifest_sha256':model.sha256,'torch':torch.__version__,'device':'cpu'}
 (HERE/'cloud_bst_parity.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
