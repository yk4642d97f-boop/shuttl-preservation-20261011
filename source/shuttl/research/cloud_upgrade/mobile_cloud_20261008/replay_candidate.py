"""Replay the fixed public validation cases; never alter deployed or frozen model bundles."""
import json,sys,hashlib
from pathlib import Path
B=Path('/root/autodl-tmp/shuttl-5090-20261008');R=B/'shuttl-runtime'
sys.path.insert(0,str(R/'backend'));sys.path.insert(0,str(R/'research/cloud_upgrade/cloud'))
from run_inference import configure,verify_bundle
from app.services.tracking.pipeline_v2 import PipelineOptions,analyze_video
assert verify_bundle();configure('cuda')
checkpoint=B/'shuttl-cloud/research/cloud_upgrade/cloud_runs/tracknetv3/best.pth.tar'
art=R/'research/cloud_upgrade/artifacts';rows=json.loads((B/'incoming/integration-inputs/manifest.json').read_text())
out=B/'candidate-integration';out.mkdir(exist_ok=True)
report={'candidate_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),'scope':'two fixed validation clips only; no held-out tuning','cases':[]}
for row in rows:
    video=B/'incoming/integration-inputs'/row['file']
    assert hashlib.sha256(video.read_bytes()).hexdigest()==row['sha256']
    opts=PipelineOptions(device='cuda',weights_dir=str(checkpoint),manual_corners=row['corners'],calibration_frames=4,
        hitnet_weights=str(art/'hitnet_single_v2.pt'),bst_manifest=str(art/'bst_seq30/manifest.json'),rtmpose_weights=str(art/'runtime/rtmpose_m_body7.onnx'))
    res=analyze_video(str(video),opts)
    report['cases'].append({'rally':row['rally'],'truth':row['truth'],'hits':[h.frame for h in res.hits],
        'rallies':len(res.rallies),'seconds':res.processing_time_seconds,'stages':res.diagnostics['stages']})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
