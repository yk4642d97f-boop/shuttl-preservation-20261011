"""CPU integration smoke on one complete public validation rally; calibration supplied."""
from pathlib import Path
import sys,json,argparse
import cv2,numpy as np,torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.tracking.camera import CameraModel
from app.services.tracking.court_model import COURT_KEYPOINTS
from app.services.tracking.video_io import iter_frames
from app.services.tracking.pipeline_v2 import PipelineOptions,analyze_video
from app.services.tracking.serialize import to_dict
from app.services.tracking.hitnet import raw_matrix

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--rally',type=int,default=10);args=parser.parse_args()
 torch.set_num_threads(4)
 out=HERE/f'cloud_runs/runtime_integration_041_r{args.rally}';out.mkdir(parents=True,exist_ok=True)
 with np.load(ROOT/'research/extract/out/041.npz',allow_pickle=True) as z:
  i=args.rally;a,b=map(int,z['rally_row_start'][i:i+2]);first,last=int(z['frame'][a]),int(z['frame'][b-1])
  ha,hb=map(int,z['rally_hit_start'][i:i+2]);truth=(z['rally_hit_frames'][ha:hb]-first).tolist()
  w,h,fps=int(z['width']),int(z['height']),float(z['fps'])
  cam=CameraModel(z['rally_cam_K'][i],z['rally_cam_R'][i],z['rally_cam_t'][i],(w,h))
 corners={name:tuple(cam.project([[*COURT_KEYPOINTS[name],0]])[0]/[w,h]) for name in ('nb_ld','nb_rd','fb_ld','fb_rd')}
 clip=out/f'041_rally{i}.mp4'
 writer=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
 for frame,img in iter_frames(str(ROOT/'research/shuttleset/videos/041.mp4'),start=first,stop=last+1):writer.write(img)
 writer.release()
 opts=PipelineOptions(device='cpu',manual_corners=corners,calibration_frames=4,
                      hitnet_weights=str(HERE/'artifacts/hitnet_single_v2.pt'),
                      bst_manifest=str(HERE/'artifacts/bst_seq30/manifest.json'),
                      rtmpose_weights=str(HERE/'artifacts/runtime/rtmpose_m_body7.onnx'))
 res=analyze_video(str(clip),opts,progress=lambda p,s:print(f'{p:.0f}% {s}',flush=True))
 np.savez_compressed(out/'raw_inputs.npz',raw=raw_matrix(res.track,res.meta,res.players),fps=res.meta.fps,
                     timestamps=res.meta.timestamps)
 doc=to_dict(res)
 (out/'analysis.json').write_text(json.dumps(doc,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
 report={'scope':'one public validation rally, supplied court corners; integration smoke only',
         'match':'041','rally_index':i,'source_frames':[first,last],'frames':res.meta.n_frames,
         'hits':len(res.hits),'rallies':len(res.rallies),'shots':sum(len(r.shots) for r in res.rallies),
         'seconds':res.processing_time_seconds,'diagnostics':res.diagnostics,
         'ground_truth_relative_frames':truth,'predicted_relative_frames':[h.frame for h in res.hits]}
 (HERE/f'cloud/runtime_integration_041_r{i}.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
 assert all(s['ok'] for s in res.diagnostics['stages'].values())
 assert res.diagnostics['hit_model']['used']=='hitnet_single_v2'
 assert res.diagnostics['stroke_model'].get('evaluated_model')=='BST_CG_AP_seq30'
 print({k:v for k,v in report.items() if k!='diagnostics'})
if __name__=='__main__':main()
