"""Compare identical pose inputs across CPU and CUDA precision modes."""
import json
import sys
from pathlib import Path
import numpy as np
import torch
import onnxruntime as ort

base = Path('/root/autodl-tmp/shuttl-5090-20261008')
root = base / 'shuttl-runtime'
sys.path.insert(0, str(root / 'backend'))
from app.services.tracking.rtmpose_core import make_session, pad_box, run_batch

ort.preload_dlls()
art = root / 'research/cloud_upgrade/artifacts/runtime'
with np.load(art / 'reference.npz') as z:
    image, boxes, reference = z['image_bgr'], z['boxes'], z['pose']
h, w = image.shape[:2]
padded = np.stack([pad_box(b, w, h) for b in boxes])
results = {}
for name, providers, options in [
    ('cpu', ['CPUExecutionProvider'], None),
    ('cuda_tf32_off', ['CUDAExecutionProvider', 'CPUExecutionProvider'], [{'use_tf32': '0'}, {}]),
    ('cuda_tf32_on', ['CUDAExecutionProvider', 'CPUExecutionProvider'], [{'use_tf32': '1'}, {}]),
]:
    session = make_session(str(art / 'rtmpose_m_body7.onnx'), providers, options, threads=4)
    session.disable_fallback()
    assert session.get_providers()[0] == providers[0]
    kp, sc = run_batch(session, session.get_inputs()[0].name,
                       [o.name for o in session.get_outputs()], image, padded)
    out = np.concatenate((kp, sc[:, :, None]), -1)
    results[name] = dict(max_coordinate_error=float(np.abs(out[:, :, :2] - reference[:, :, :2]).max()),
                         max_score_error=float(np.abs(out[:, :, 2] - reference[:, :, 2]).max()),
                         providers=session.get_provider_options())
    print(name, results[name], flush=True)
    del session
(base / 'logs/pose-precision.json').write_text(json.dumps(results, indent=2) + '\n')
