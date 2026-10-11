#!/usr/bin/env python3
"""Evidence for the timing findings: per-segment start/end frame, time span, end reason, speed and
landing for a clip, via pipeline_v2 (Python reference). Also proves the rotation fix works in this
OpenCV build: CAP_PROP_ORIENTATION_AUTO defaults to 0 here, setting it to 1 rotates the frame.
Usage (from backend/): .venv/bin/python ../tools/robustness/diag_segments.py <clip> [...]"""
import json, math, sys
import cv2
from app.services.tracking import pipeline_v2

def segs(path):
    a = pipeline_v2.analyze_video(path)
    t = a.meta.timestamps
    out = {'clip': path.split('/')[-1], 'hits': [(h.frame, round(h.t, 3), h.hitter) for h in a.hits], 'segments': []}
    for g in a.segments:
        span = [g.frames[0], g.frames[-1]] if len(g.frames) else [g.start_frame, g.end_frame]
        gaps = [round(t[b] - t[a_], 3) for a_, b in zip(g.frames[:-1], g.frames[1:]) if t[b] - t[a_] > 0.1] if len(g.frames) else []
        out['segments'].append({'frames': span, 't': [round(t[span[0]], 3), round(t[span[1]], 3)],
            'obs_gaps_s': gaps, 'end': str(g.end_reason), 'speed_kmh': round(g.speed0_kmh, 1),
            'landing': None if g.landing_xy is None else [round(float(v), 2) for v in g.landing_xy],
            'landing_t': g.landing_t})
    out['rallies'] = [{'frames': [r.start_frame, r.end_frame], 'shots': len(r.shots), 'end': str(r.end_reason),
                       'landing': None if r.landing_xy is None else [round(float(v), 2) for v in r.landing_xy]} for r in a.rallies]
    return out

def rotation(path):
    c = cv2.VideoCapture(path); d = {'default_auto': c.get(cv2.CAP_PROP_ORIENTATION_AUTO),
        'meta': c.get(cv2.CAP_PROP_ORIENTATION_META), 'default_shape': c.read()[1].shape[:2]}
    c = cv2.VideoCapture(path); c.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1); d['auto_on_shape'] = c.read()[1].shape[:2]
    return d

if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = rotation(p) if 'rot' in p else segs(p)
        print(json.dumps({'clip': p.split('/')[-1], **r}, default=str), flush=True)
