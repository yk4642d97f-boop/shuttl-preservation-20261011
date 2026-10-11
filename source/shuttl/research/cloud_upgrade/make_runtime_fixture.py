"""Save compact CPU reference tensors for a relocated runtime self-check."""
from pathlib import Path
import sys,json,shutil,hashlib
import numpy as np
import torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import stroke_chain as R
from app.services.tracking import hitnet,bst,rtmpose

def main():
 torch.set_num_threads(4)
 out=HERE/'artifacts/runtime';out.mkdir(exist_ok=True)
 onnx=Path.home()/'.cache/rtmlib/hub/checkpoints/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.onnx'
 if not (out/'rtmpose_m_body7.onnx').exists():shutil.copy2(onnx,out/'rtmpose_m_body7.onnx')
 raw=R.E.C.load_match('033')['rallies'][0]
 h=hitnet.load(HERE/'artifacts/hitnet_single_v2.pt')
 frames=R.MatchFrames('041')
 clips=[frames.raw_clip(int(f))[0] for f in frames.data['rally_hit_frames'][:30]]
 clip=next(c for c in clips if c is not None)
 b=bst.load(HERE/'artifacts/bst_seq30/manifest.json')
 pose=rtmpose.load(out/'rtmpose_m_body7.onnx')
 rng=np.random.default_rng(20261007);img=rng.integers(0,256,(256,384,3),dtype=np.uint8)
 boxes=np.array([[20,10,100,240],[220,50,290,150]],np.float32)
 np.savez_compressed(out/'reference.npz',hit_raw=raw['raw'],fps=raw['fps'],hit_logits=h.logits(raw['raw'],raw['fps']),
                     joints=clip[0],pos=clip[1],shuttle=clip[2],bst_logits=b.logits([clip]),
                     image_bgr=img,boxes=boxes,pose=pose.estimate(img,boxes))
 doc={'purpose':'portability fixture, not an accuracy benchmark','hit_source':'033 first annotated rally','bst_source':'041 first usable annotated hit window',
      'pose_source':'deterministic synthetic pixels','files':[{ 'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (out/'reference.npz',out/'rtmpose_m_body7.onnx')]}
 (out/'manifest.json').write_text(json.dumps(doc,indent=2)+'\n')
 print(doc)
if __name__=='__main__':main()
