"""Real validation video crop/inference parity against the original RTMPose reference."""
from pathlib import Path
import sys,json
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'research/rtmpose'))
import fast_pose as reference
from app.services.tracking.rtmpose import Pose
from app.services.tracking.video_io import iter_frames

def main():
 model=Pose(reference.MODEL_BODY7)
 with np.load(ROOT/'research/extract/out/041.npz',allow_pickle=True) as z:
  frames,boxes=z['frame'],z['player_box']
 slots=[i for i in range(min(150,len(frames))) if np.isfinite(boxes[i]).all()][:4]
 wanted={int(frames[i]):boxes[i] for i in slots}
 maximum=0.;count=0
 for frame,image in iter_frames(str(ROOT/'research/shuttleset/videos/041.mp4'),start=min(wanted),stop=max(wanted)+1):
  if frame not in wanted: continue
  boxes=wanted[frame];h,w=image.shape[:2]
  expected=[]
  # Original one-box inference vs production batched inference.
  for box in boxes:
   kp,sc=reference.run_batch(model.session,model.input.name,model.outputs,image,reference.pad_box(box,w,h)[None])
   expected.append(np.concatenate((kp[0],sc[0,:,None]),-1))
  expected=np.stack(expected);actual=model.estimate(image,boxes)
  np.testing.assert_allclose(actual,expected,rtol=0,atol=.01)
  maximum=max(maximum,float(np.abs(actual-expected).max()));count+=len(boxes)
 assert count==len(slots)*2
 report={'match':'041','frames':len(slots),'poses':count,'max_abs_coordinate_or_score_error':maximum,'onnx_sha256':model.sha256,'providers':model.providers,'scope':'real BGR frames, original boxes, one-box reference vs batch production'}
 (HERE/'cloud_pose_parity.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
