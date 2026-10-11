"""Research-only pose candidates. All outputs preserve input box order, COCO17, pixels.

The shipped RTMPose-m/BST baseline intentionally retains its audited BGR contract.
RTMPose-X follows its own SDK/training config: RGB, 384x288. Do not infer its
preprocessing from the stale 256x192 fields in the SDK sidecar.
"""
from pathlib import Path
import hashlib
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.tracking.rtmpose_core import pad_box, make_session

COCO17 = ['nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
          'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
          'left_wrist', 'right_wrist', 'left_hip', 'right_hip', 'left_knee',
          'right_knee', 'left_ankle', 'right_ankle']
BASELINE = Path.home() / '.cache/rtmlib/hub/checkpoints/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.onnx'
X_PATH = HERE / 'models/rtmpose_x/20230831/rtmpose_onnx/rtmpose-x_simcc-body7_pt-body7_700e-384x288-71d7b7e9_20230629/end2end.onnx'
VIT_PATH = HERE / 'models/vitpose_plus_base'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def padded_boxes(image, boxes):
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError('Expected uint8 BGR frame')
    b = np.asarray(boxes, np.float32)
    if b.size == 0:
        return np.empty((0, 4), np.float32)
    if b.ndim != 2 or b.shape[1] != 4 or not np.isfinite(b).all() or np.any(b[:, 2:] <= b[:, :2]):
        raise ValueError('Invalid pose boxes')
    h, w = image.shape[:2]
    p = np.stack([pad_box(x, w, h) for x in b])
    if np.any(p[:, 2:] <= p[:, :2]):
        raise ValueError('Pose box outside image')
    return p


def checked(result, n):
    result = np.asarray(result, np.float32)
    if result.shape != (n, 17, 3) or not np.isfinite(result).all():
        raise ValueError('Invalid COCO17 pose output')
    return result


class SimCC:
    def __init__(self, name, device='cpu', threads=2):
        import onnxruntime as ort
        if name not in ('rtmpose_m', 'rtmpose_x'):
            raise ValueError(name)
        self.path = BASELINE if name == 'rtmpose_m' else X_PATH
        self.size = (192, 256) if name == 'rtmpose_m' else (288, 384)
        self.rgb = name == 'rtmpose_x'
        if device == 'cpu':
            providers, options = ['CPUExecutionProvider'], None
        elif device == 'cuda':
            if 'CUDAExecutionProvider' not in ort.get_available_providers():
                raise RuntimeError('CUDA provider unavailable; refusing CPU fallback')
            providers, options = ['CUDAExecutionProvider', 'CPUExecutionProvider'], [{'device_id': '0'}, {}]
        else:
            raise ValueError('Choose cpu or cuda')
        self.session = make_session(str(self.path), providers, options, threads=threads)
        if providers[0] not in self.session.get_providers():
            raise RuntimeError('Requested provider failed to initialize')
        self.session.disable_fallback()
        self.input = self.session.get_inputs()[0]
        if self.input.shape[1:] != [3, self.size[1], self.size[0]]:
            raise ValueError('Model input dimensions differ from frozen contract')
        self.outputs = [o.name for o in self.session.get_outputs()]
        self.info = dict(name=name, weights_sha256=sha(self.path), input_wh=self.size,
                         color='RGB' if self.rgb else 'BGR', providers=self.session.get_providers(),
                         dtype='float32', threads=threads, flip_test=False)

    def estimate(self, image, boxes):
        from rtmlib.tools.pose_estimation.rtmpose import bbox_xyxy2cs, top_down_affine, get_simcc_maximum
        padded = padded_boxes(image, boxes)
        if not len(padded):
            return np.empty((0, 17, 3), np.float32)
        frame = image[:, :, ::-1] if self.rgb else image
        xs, centers, scales = [], [], []
        mean = np.array([123.675, 116.28, 103.53], np.float32)
        std = np.array([58.395, 57.12, 57.375], np.float32)
        for box in padded:
            c, s = bbox_xyxy2cs(box, padding=1.25)
            crop, s = top_down_affine(self.size, s, c, frame)
            xs.append(((crop.astype(np.float32) - mean) / std).transpose(2, 0, 1))
            centers.append(c)
            scales.append(s)
        out = self.session.run(self.outputs, {self.input.name: np.stack(xs)})
        expected = [(len(padded), 17, self.size[0] * 2), (len(padded), 17, self.size[1] * 2)]
        if [x.shape for x in out] != expected:
            raise ValueError('SimCC output dimensions differ from contract')
        kp, sc = get_simcc_maximum(*out)
        s, c = np.asarray(scales)[:, None], np.asarray(centers)[:, None]
        kp = kp / np.float32(2) / np.array(self.size, np.float32) * s + c - s / 2
        return checked(np.concatenate((kp, sc[..., None]), -1), len(padded))


class ViTPose:
    def __init__(self, device='cpu', threads=2):
        import torch
        from transformers import VitPoseImageProcessor, VitPoseForPoseEstimation
        if device not in ('cpu', 'cuda') or (device == 'cuda' and not torch.cuda.is_available()):
            raise RuntimeError('Requested torch device unavailable')
        torch.set_num_threads(threads)
        self.device = device
        self.processor = VitPoseImageProcessor.from_pretrained(VIT_PATH, local_files_only=True)
        self.model = VitPoseForPoseEstimation.from_pretrained(
            VIT_PATH, local_files_only=True, use_safetensors=True).eval().to(device)
        native_names = [n.replace('left_', 'L_').replace('right_', 'R_') for n in COCO17]
        native_names = ['_'.join(part.capitalize() for part in n.split('_')) for n in native_names]
        if [self.model.config.id2label[i] for i in range(17)] != native_names:
            raise ValueError('ViTPose keypoint order differs from COCO17')
        self.info = dict(name='vitpose_plus_base', weights_sha256=sha(VIT_PATH / 'model.safetensors'),
                         config_sha256=sha(VIT_PATH / 'config.json'),
                         processor_sha256=sha(VIT_PATH / 'preprocessor_config.json'),
                         dataset_index=0, color='RGB', input_wh=[192, 256], device=device,
                         dtype='float32', threads=threads, flip_test=False)

    def estimate(self, image, boxes):
        import torch
        padded = padded_boxes(image, boxes)
        if not len(padded):
            return np.empty((0, 17, 3), np.float32)
        xywh = padded.copy()
        xywh[:, 2:] -= xywh[:, :2]
        inputs = self.processor(image[:, :, ::-1].copy(), boxes=[xywh.tolist()], return_tensors='pt')
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.inference_mode():
            outputs = self.model(**inputs, dataset_index=torch.zeros(len(padded), dtype=torch.long, device=self.device))
        rows = self.processor.post_process_pose_estimation(outputs, boxes=[xywh.tolist()])[0]
        for row in rows:
            if row['labels'].tolist() != list(range(17)):
                raise ValueError('Native decoder dropped/reordered keypoints')
        return checked(np.stack([np.column_stack((r['keypoints'].numpy(), r['scores'].numpy())) for r in rows]), len(padded))


def load(name, device='cpu', threads=2):
    return ViTPose(device, threads) if name == 'vitpose_plus_base' else SimCC(name, device, threads)
