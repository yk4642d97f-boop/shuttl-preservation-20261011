"""Freeze one preselected real frame and cached-feature BST outputs for archive replay."""
import json
import numpy as np
import torch
import hashlib
from adapters import HERE, ROOT, sha
from panel import R, write_new
from app.services.tracking.video_io import iter_frames


def main():
    torch.set_num_threads(2)
    comparison = HERE / 'results/small/comparison_cpu.json'
    if not comparison.exists():
        raise ValueError('Run the checked three-arm comparison first')
    panel = json.loads((HERE / 'panels/small.json').read_text())
    fid = panel['events'][0]['frame']
    _, image = next(iter_frames(str(ROOT / 'research/shuttleset/videos/041.mp4'), start=fid, stop=fid + 1))
    frames = R.MatchFrames('041')
    clip, reason = frames.raw_clip(fid)
    if clip is None:
        raise ValueError(reason)
    data = dict(frame=np.array(fid), pixel_sha256=np.array(hashlib.sha256(image.tobytes()).hexdigest()),
                box=frames.data['player_box'][frames.indices[fid]], bst_logits=R.classify([clip], 'cpu'))
    for name in ['rtmpose_m', 'rtmpose_x', 'vitpose_plus_base']:
        with np.load(HERE / 'results/small' / f'{name}_cpu' / 'outputs.npz') as z:
            data['kp_' + name] = z['kp'][int(np.flatnonzero(z['frame'] == fid)[0])]
    out = HERE / 'checks/reference.npz'
    with out.open('xb') as f:
        np.savez_compressed(f, **data)
    write_new(out.with_suffix('.json'), dict(frame=fid, sha256=sha(out), comparison_sha256=sha(comparison),
               scope='first event by frozen panel order; BST on cached baseline features, not candidate tuning'))
    print(out)


if __name__ == '__main__':
    main()
