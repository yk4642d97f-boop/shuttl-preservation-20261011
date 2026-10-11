"""Replay both previously recorded public validation cases on the cloud GPU."""
import hashlib
import json
import sys
from pathlib import Path
import torch

base = Path('/root/autodl-tmp/shuttl-5090-20261008')
root = base / 'shuttl-runtime'
sys.path.insert(0, str(root / 'backend'))
sys.path.insert(0, str(root / 'research/cloud_upgrade/cloud'))
from run_inference import configure, verify_bundle
from app.services.tracking.pipeline_v2 import PipelineOptions, analyze_video
from app.services.tracking.serialize import to_dict

assert verify_bundle()
configure('cuda')
out = base / 'integration-gpu'
out.mkdir(exist_ok=False)
art = root / 'research/cloud_upgrade/artifacts'
rows = json.loads((base / 'incoming/integration-inputs/manifest.json').read_text())
reports = []
for row in rows:
    video = base / 'incoming/integration-inputs' / row['file']
    assert hashlib.sha256(video.read_bytes()).hexdigest() == row['sha256']
    opts = PipelineOptions(device='cuda', manual_corners=row['corners'], calibration_frames=4,
                           hitnet_weights=str(art / 'hitnet_single_v2.pt'),
                           bst_manifest=str(art / 'bst_seq30/manifest.json'),
                           rtmpose_weights=str(art / 'runtime/rtmpose_m_body7.onnx'))
    result = analyze_video(str(video), opts, progress=lambda p, s: print(f'{p:.0f}% {s}', flush=True))
    (out / f"rally-{row['rally']}.json").write_text(json.dumps(to_dict(result), ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    report = dict(rally=row['rally'], video_sha256=row['sha256'], frames=result.meta.n_frames,
                  truth=row['truth'], predicted=[h.frame for h in result.hits],
                  diagnostics=result.diagnostics, seconds=result.processing_time_seconds)
    reports.append(report)
    (out / 'report.json').write_text(json.dumps(dict(device='cuda', torch=torch.__version__, cases=reports,
        scope='Previously selected public validation cases with supplied calibration; not full-video/doubles accuracy or isolated throughput'),
        ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    assert all(stage['ok'] for stage in result.diagnostics['stages'].values())
    assert result.diagnostics['hit_model']['used'] == 'hitnet_single_v2'
    print({k: v for k, v in report.items() if k != 'diagnostics'}, flush=True)
