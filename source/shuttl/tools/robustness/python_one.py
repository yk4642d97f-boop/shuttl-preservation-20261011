#!/usr/bin/env python3
"""Analyze one clip with pipeline_v2 and print ONE JSON line with the same fields as the
Swift driver (camera/visible/hits/rallies/max speed/implausible) plus what the server task
(tasks.py:71-79) would do with it: it stores status 'done' whenever analyze_video returns."""
import json, math, os, resource, sys, time, traceback
import numpy as np
from app.services.tracking import pipeline_v2, serialize
from app.services.tracking.pipeline_v2 import PipelineOptions

HALL_X, HALL_Y = 6.70 + 4, 3.05 + 3

def implausible(a):
    bad = []
    speeds = [s.segment.speed0_kmh for r in a.rallies for s in r.shots if s.segment is not None]
    speeds += [g.speed0_kmh for g in a.segments]
    if any(not math.isfinite(v) for v in speeds): bad.append('non-finite speed')
    fin = [v for v in speeds if math.isfinite(v)]
    if fin and max(fin) > 450: bad.append(f'speed {max(fin):.0f} km/h > 450')
    lands = [g.landing_xy for g in a.segments if g.landing_xy is not None]
    lands += [r.landing_xy for r in a.rallies if getattr(r, 'landing_xy', None) is not None]
    if any(not (abs(l[0]) <= HALL_X and abs(l[1]) <= HALL_Y) for l in lands): bad.append('landing outside hall')
    ts = np.asarray(a.meta.timestamps)
    if len(ts) > 1 and not np.all(np.diff(ts) > 0): bad.append('meta timestamps not increasing')
    if any(h.frame < 0 or h.frame >= a.meta.n_frames for h in a.hits): bad.append('hit frame outside clip')
    if a.track is not None and len(a.track.t) != a.meta.n_frames: bad.append('track length != frames')
    return bad

def server_verdict(a):
    """What backend tasks.analyze_match does with this result (tasks.py: unusable_reason → AnalysisUnusable, no retry)."""
    try:
        from app.services.tracking import tasks
        why = tasks.unusable_reason(a) if hasattr(tasks, 'unusable_reason') else None
    except Exception as e:                      # celery/db imports unavailable → fall back to the old rule
        why = None if a.rallies else f'(tasks import failed: {type(e).__name__})'
    if why is None:
        return {'server_status': 'done', 'server_empty_done': len(a.rallies) == 0, 'server_reason': None}
    return {'server_status': 'failed (unusable, not retried)', 'server_empty_done': False, 'server_reason': why}

def main():
    p = sys.argv[1]; start = time.monotonic()
    r = {'clip': os.path.basename(p), 'traceback': None}
    try:
        a = pipeline_v2.analyze_video(p, PipelineOptions())
        d = serialize.to_dict(a)
        fin = [s.segment.speed0_kmh for x in a.rallies for s in x.shots if s.segment is not None]
        fin = [v for v in fin if math.isfinite(v)]
        stages = d.get('diagnostics', {}).get('stages', {})
        r.update(status='returned', frames=a.meta.n_frames, fps=a.meta.fps, size=[a.meta.width, a.meta.height],
                 rotation=a.meta.rotation_deg, duration_s=float(a.meta.timestamps[-1]) if a.meta.n_frames else 0.0,
                 camera=a.camera is not None,
                 visible=int(np.sum(a.track.visible)) if a.track is not None else 0,
                 hits=len(a.hits), rallies=len(a.rallies), shots=sum(len(x.shots) for x in a.rallies),
                 hit_frames=[h.frame for h in a.hits], max_speed_kmh=max(fin) if fin else 0.0,
                 implausible=implausible(a), detector=d.get('diagnostics', {}).get('detector'),
                 stages=stages, stage_failures=[f'{k}: {v.get("error")}' for k, v in stages.items() if not v.get('ok')],
                 calibration_auto=d.get('diagnostics', {}).get('calibration_auto'),
                 **server_verdict(a))
    except Exception as e:
        r.update(status='clean_failure', error=f'{type(e).__name__}: {e}', traceback=traceback.format_exc()[-4000:],
                 server_status='failed (after 2 Celery retries)')
    r['seconds'] = round(time.monotonic() - start, 3)
    r['max_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576, 1)
    print(json.dumps(r, ensure_ascii=False, allow_nan=True, default=str), flush=True)

if __name__ == '__main__':
    main()
