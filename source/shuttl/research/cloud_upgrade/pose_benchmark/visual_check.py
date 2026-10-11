"""Fixed first panel frame, three pose arms; visual alignment only, no keypoint GT."""
from pathlib import Path
import argparse
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from adapters import HERE, ROOT
from app.services.tracking.video_io import iter_frames


def main(device):
    panel = json.loads((HERE / 'panels/small.json').read_text())
    fid = panel['events'][0]['frame']  # chosen by frozen panel order, never model success
    _, frame = next(iter_frames(str(ROOT / 'research/shuttleset/videos/041.mp4'), start=fid, stop=fid + 1))
    names = ['rtmpose_m', 'rtmpose_x', 'vitpose_plus_base']
    edges = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
             (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
    canvas = Image.new('RGB', (1080, 760), '#111827')
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype('Arial.ttf', 22)
        small = ImageFont.truetype('Arial.ttf', 16)
    except OSError:
        font = ImageFont.load_default(size=22)
        small = ImageFont.load_default(size=16)
    draw.text((22, 15), f'Match041 / fixed first panel event / frame {fid}', font=font, fill='white')
    for c, name in enumerate(names):
        with np.load(HERE / 'results/small' / f'{name}_{device}' / 'outputs.npz') as z:
            index = int(np.flatnonzero(z['frame'] == fid)[0])
            box, kp = z['box'][index], z['kp'][index]
        draw.text((c * 360 + 20, 53), name, font=font, fill='white')
        for person in range(2):
            x1, y1, x2, y2 = box[person]
            pad = .45 * max(x2 - x1, y2 - y1)
            lo = np.maximum(np.floor([x1 - pad, y1 - pad]), 0).astype(int)
            hi = np.minimum(np.ceil([x2 + pad, y2 + pad]), [frame.shape[1], frame.shape[0]]).astype(int)
            crop = frame[lo[1]:hi[1], lo[0]:hi[0]].copy()
            points = np.rint(kp[person, :, :2] - lo).astype(int)
            for a, b in edges:
                cv2.line(crop, tuple(points[a]), tuple(points[b]), (50, 235, 255), 1, cv2.LINE_AA)
            for x, y in points:
                cv2.circle(crop, (int(x), int(y)), 2, (180, 70, 255), -1, cv2.LINE_AA)
            image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            image.thumbnail((330, 275))
            y = 117 + person * 305
            canvas.paste(image, (c * 360 + (360 - image.width) // 2, y))
            draw.text((c * 360 + 20, y - 25), 'far player' if person == 0 else 'near player', font=small, fill='#CBD5E1')
    draw.text((22, 727), 'No pose ground truth: this image checks alignment, not model accuracy.', font=small, fill='#CBD5E1')
    target = HERE / 'results/small' / f'visual_check_{device}.png'
    canvas.save(target)
    print(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    main(p.parse_args().device)
