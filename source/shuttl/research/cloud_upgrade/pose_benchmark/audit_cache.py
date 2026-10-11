"""Diagnose old/new pose-cache differences without changing evaluation or caches.

Run with both Python environments and distinct --out. This intentionally imports
only the original NumPy/ORT pose reference so the old NumPy2 environment can run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np
import onnxruntime as ort

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'research/rtmpose'))
import fast_pose as F


def main(out):
    selected = json.loads((HERE / 'checks/cache_audit_selection.json').read_text())['frames']
    with np.load(ROOT / 'research/extract/out/041.npz') as z:
        ix = {int(f): i for i, f in enumerate(z['frame'])}
        boxes = z['player_box'][[ix[f] for f in selected]]
    session = F.make_session(F.MODEL_BODY7, ['CPUExecutionProvider'], threads=2)
    images, tensors, kps, crops, pads, scales, centers = [], [], [], [], [], [], []
    for fid, bs in zip(selected, boxes):
        cap = cv2.VideoCapture(str(ROOT / 'research/shuttleset/videos/041.mp4'))
        cap.set(cv2.CAP_PROP_POS_FRAMES, fid)
        ok, image = cap.read()
        cap.release()
        if not ok:
            raise ValueError(fid)
        images.append(hashlib.sha256(image.tobytes()).hexdigest())
        h, w = image.shape[:2]
        padded = np.stack([F.pad_box(b, w, h) for b in bs])
        inp, cs, ss, cr = [], [], [], []
        for box in padded:
            c, s = F.bbox_xyxy2cs(box, padding=1.25)
            crop, s = F.top_down_affine(F.INPUT_SIZE, s, c, image)
            cr.append(crop)
            inp.append(((crop.astype(np.float32) - F.MEAN) / F.STD).transpose(2, 0, 1))
            cs.append(c); ss.append(s)
        tensors.append(np.stack(inp)); crops.append(np.stack(cr)); pads.append(padded)
        centers.append(cs); scales.append(ss)
        kp, sc = F.run_batch(session, session.get_inputs()[0].name,
                             [o.name for o in session.get_outputs()], image, padded)
        kps.append(np.concatenate((kp, sc[..., None]), -1))
    with Path(out).open('xb') as f:
        np.savez_compressed(f, frame=selected, kp=kps, input=tensors, pixel_sha256=images,
                            crop=crops, pads=pads, centers=centers, scales=scales)
    Path(out).with_suffix('.json').write_text(json.dumps(dict(numpy=np.__version__, opencv=cv2.__version__,
          onnxruntime=ort.__version__, frames=selected, scope='diagnostic worst cache deltas; not a new model-selection panel'), indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    main(p.parse_args().out)
