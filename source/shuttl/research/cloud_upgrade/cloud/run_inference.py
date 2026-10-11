"""Portable local/cloud inference entry point. No API, upload, billing or deployment side effects."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[3]
HERE=ROOT/'research/cloud_upgrade';ART=HERE/'artifacts'
sys.path.insert(0,str(ROOT/'backend'))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_bundle():
    path=ROOT/'RUNTIME_MANIFEST.json'
    if not path.exists():return False
    for item in json.loads(path.read_text())['files']:
        p=(ROOT/item['path']).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or sha(p)!=item['sha256']:
            raise ValueError(f"Runtime checksum mismatch: {item['path']}")
    return True


def configure(device):
    torch.set_num_threads(4)
    if device.startswith('cuda'):
        if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; refusing CPU fallback')
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
    elif device!='cpu':raise ValueError('Use cpu or cuda[:index] for the complete portable chain')


def preflight(device):
    from app.services.tracking import hitnet,bst,rtmpose,detector,players
    verified=verify_bundle();configure(device);start=time.monotonic()
    h=hitnet.load(ART/'hitnet_single_v2.pt',device)
    b=bst.load(ART/'bst_seq30/manifest.json',device)
    pose=rtmpose.load(ART/'runtime/rtmpose_m_body7.onnx',device)
    with np.load(ART/'runtime/reference.npz',allow_pickle=False) as z:
        hit=h.logits(z['hit_raw'],float(z['fps']));stroke=b.logits([(z['joints'],z['pos'],z['shuttle'])])
        keypoints=pose.estimate(z['image_bgr'],z['boxes'])
        np.testing.assert_allclose(hit,z['hit_logits'],rtol=0,atol=1e-4)
        np.testing.assert_allclose(stroke,z['bst_logits'],rtol=0,atol=1e-4)
        assert int(stroke.argmax())==int(z['bst_logits'].argmax())
        np.testing.assert_allclose(keypoints[:,:,:2],z['pose'][:,:,:2],rtol=0,atol=.25)
        np.testing.assert_allclose(keypoints[:,:,2],z['pose'][:,:,2],rtol=0,atol=1e-3)
        errors={'hit_logits':float(np.abs(hit-z['hit_logits']).max()),'bst_logits':float(np.abs(stroke-z['bst_logits']).max()),
                'pose':float(np.abs(keypoints-z['pose']).max())}
    checks=[]
    for kind in ('tracknetv3','wasb'):
        path=detector.find_weights(kind);net,spec=detector.load_model(path,kind)
        net=net.to(device)
        with torch.inference_mode():output=net(torch.zeros(1,spec.in_channels,288,512,device=device))
        if tuple(output.shape)!=(1,spec.seq_len,288,512) or not torch.isfinite(output).all():raise ValueError(f'{kind} forward failed')
        checks.append({'kind':kind,'shape':list(output.shape),'sha256':sha(path)})
        del net,output
    # Confirm the existing person detector loads offline and can execute NMS.
    person=players.make_yolo_detector('yolov8s-pose.pt',device,imgsz=320)
    person([np.zeros((320,320,3),np.uint8)],[0])
    report={'device':device,'torch':torch.__version__,'cuda':torch.version.cuda,'bundle_verified':verified,
            'reference_max_abs_error':errors,'detectors':checks,'person_forward':True,
            'pose_providers':pose.providers,'seconds':time.monotonic()-start,
            'scope':'runtime portability only; not full-video model accuracy'}
    return report


def analyze(a):
    from app.services.tracking.pipeline_v2 import analyze_video,PipelineOptions
    from app.services.tracking.serialize import to_dict
    verify_bundle();configure(a.device)
    if a.output.exists():raise ValueError('Output exists; choose a new filename')
    corners=json.loads(a.corners.read_text()) if a.corners else None
    os.environ['SHUTTL_DETECTOR']=a.detector
    opts=PipelineOptions(device=a.device,doubles=a.doubles,manual_corners=corners,
                         hitnet_weights=str(ART/'hitnet_single_v2.pt'),
                         bst_manifest=str(ART/'bst_seq30/manifest.json'),
                         rtmpose_weights=str(ART/'runtime/rtmpose_m_body7.onnx'))
    result=analyze_video(str(a.video),opts,progress=lambda p,s:print(f'{p:.0f}% {s}',flush=True))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(to_dict(result),ensure_ascii=False,allow_nan=False,indent=2)+'\n')
    failures={k:v for k,v in result.diagnostics.get('stages',{}).items() if not v['ok']}
    print(json.dumps({'output':str(a.output),'rallies':len(result.rallies),'failed_stages':failures,
                      'hit_model':result.diagnostics.get('hit_model'),'stroke_model':result.diagnostics.get('stroke_model',{}).get('used')},ensure_ascii=False))
    if failures:raise SystemExit(2)


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('preflight');p.add_argument('--device',default='cpu');p.add_argument('--report',type=Path)
    p=sub.add_parser('analyze');p.add_argument('--video',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--device',default='cpu');p.add_argument('--doubles',action='store_true',default=None)
    p.add_argument('--detector',choices=['tracknetv3','wasb'],default='tracknetv3')
    p.add_argument('--corners',type=Path,help='JSON with normalized named court corners')
    a=ap.parse_args()
    if a.command=='preflight':
        result=preflight(a.device)
        if a.report:
            a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    else:analyze(a)
if __name__=='__main__':main()
