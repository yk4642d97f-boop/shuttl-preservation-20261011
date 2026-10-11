"""Replay already prepared tensors to separate preprocessing from ORT changes."""
import argparse
from pathlib import Path
import sys
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'research/rtmpose'))
import fast_pose as F
from rtmlib.tools.pose_estimation.pre_processings import get_warp_matrix


def main(source, dest):
    z = np.load(source)
    s = F.make_session(F.MODEL_BODY7, ['CPUExecutionProvider'], threads=2)
    rows, mats = [], []
    for x, c, scale in zip(z['input'], z['centers'], z['scales']):
        out = s.run([o.name for o in s.get_outputs()], {s.get_inputs()[0].name: x})
        loc, sc = F.get_simcc_maximum(*out)
        kp = loc / 2. / np.array(F.INPUT_SIZE, np.float32) * scale[:, None]
        kp = kp + c[:, None] - scale[:, None] / 2
        rows.append(np.concatenate((kp, sc[..., None]), -1))
        mats.append([get_warp_matrix(ci, si, 0, output_size=F.INPUT_SIZE) for ci, si in zip(c, scale)])
    with Path(dest).open('xb') as f:
        np.savez_compressed(f, kp=rows, matrices=mats)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    main(a.input, a.out)
