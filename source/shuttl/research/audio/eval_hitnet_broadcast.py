"""Broadcast-singles sanity check of HitNet v2 in the cloud pipeline (FineBadminton-20K, Apache-2.0).

Per video: production tracking → players (singles) → HitNet v2 curves, decoded as shipped;
the same curves with every player's foot_world removed (what a failed court calibration feeds
HitNet); the rule detector; and HitNet + audio fusion (default params, per-recording gate).
Scored one-to-one at ±2 frames, detections restricted to the annotated rally windows.
`labels` are FineBadminton's raw start_frame values (the stroke start, ~7 frames before the
contact); eval_hitnet_broadcast_offsets.py measures that offset and re-scores at it.

Run from source/shuttl/backend (GPU):
  SHUTTL_WEIGHTS_DIR=... SHUTTL_HITNET_WEIGHTS=.../hitnet_single_v2.pt FINEB_DIR=<dir with {id}.mp4
  and {id}.json> FINEB_OUT=results.json PYTHONPATH=. python ../research/audio/eval_hitnet_broadcast.py 0044 0045 0046 0047
"""
import dataclasses, json, os, sys
import numpy as np
from app.services.tracking import audio_hits, hit_fusion, hitnet
from app.services.tracking.pipeline_v2 import PipelineOptions, analyze_video

ROOT = os.environ.get('FINEB_DIR', 'fineb')


def match(det, gt, tol=2):
    cand = sorted((abs(int(a) - int(b)), i, j) for i, a in enumerate(det) for j, b in enumerate(gt)
                  if abs(int(a) - int(b)) <= tol)
    ud, ug = set(), set()
    for _, i, j in cand:
        if i not in ud and j not in ug:
            ud.add(i); ug.add(j)
    return len(ud)


def prf(tp, nd, ng):
    p, r = tp / max(1, nd), tp / max(1, ng)
    return dict(P=round(p, 3), R=round(r, 3), F1=round(2 * p * r / max(1e-9, p + r), 3), tp=tp, det=nd, gt=ng)


model = hitnet.load(os.environ['SHUTTL_HITNET_WEIGHTS'], 'cuda')
report, pooled = {}, {}
for vid in sys.argv[1:]:
    video, ann = f'{ROOT}/{vid}.mp4', json.load(open(f'{ROOT}/{vid}.json'))
    opts = PipelineOptions(weights_dir=os.environ['SHUTTL_WEIGHTS_DIR'], device='cuda')
    res = analyze_video(video, opts)
    n, fps = len(res.meta.timestamps), float(res.meta.fps)
    gt, windows = [], []
    for r in ann:
        hs = r.get('hitting') or []
        if not hs:
            continue
        gt += [int(h['start_frame']) for h in hs if int(h['start_frame']) < n]
        a = int(r.get('start_frame', hs[0]['start_frame'])); b = int(r.get('end_frame', hs[-1]['end_frame']))
        windows.append((a - int(fps / 2), b + int(fps / 2)))
    inside = lambda fr: [f for f in fr if any(a <= f <= b for a, b in windows)]  # noqa: E731
    gt = sorted(set(gt))
    curves = model.curves(res.track, res.meta, res.players)
    nofoot = [dataclasses.replace(o, foot_world=None) for o in res.players]
    curves_nf = model.curves(res.track, res.meta, nofoot)
    t = np.asarray(res.meta.timestamps, float)
    sound = audio_hits.impact_curve(video)
    out = {}
    for name, c, audio in (('hitnet', curves, None), ('hitnet_no_foot', curves_nf, None),
                           ('hitnet_audio', curves, sound)):
        frames, _, gate, moved = hitnet.decode(c, t, fps, thr=.4, gap_s=.30, audio_curve=audio,
                                               params=hit_fusion.FusionParams())
        det = inside(frames)
        out[name] = prf(match(det, gt), len(det), len(gt))
        out[name]['frames'] = [int(f) for f in det]
        if name == 'hitnet_audio':
            out[name]['gate'] = gate.as_dict() if gate else None
            out[name]['hits_changed_by_audio'] = moved
    det = inside([h.frame for h in res.hits])
    out['rules_or_pipeline'] = prf(match(det, gt), len(det), len(gt))
    out['rules_or_pipeline']['frames'] = [int(f) for f in det]
    out['labels'] = gt
    out['p_max'] = round(float(np.nanmax(curves.probability)), 3)
    foot = np.mean([o.foot_world is not None for o in res.players]) if res.players else 0.0
    out.update(frames=n, fps=fps, windows=len(windows), camera=res.camera is not None,
               foot_world_coverage=round(float(foot), 3), detector=res.diagnostics.get('hit_detector'),
               calibration=res.diagnostics.get('calibration'))
    report[vid] = out
    for k in ('hitnet', 'hitnet_no_foot', 'hitnet_audio', 'rules_or_pipeline'):
        acc = pooled.setdefault(k, [0, 0, 0])
        acc[0] += out[k]['tp']; acc[1] += out[k]['det']; acc[2] += out[k]['gt']
    print(vid, json.dumps({k: (v['F1'] if isinstance(v, dict) and 'F1' in v else v) for k, v in out.items()
                           if k != 'calibration'}, default=str), flush=True)
report['pooled'] = {k: prf(*v) for k, v in pooled.items()}
print('pooled', json.dumps(report['pooled']))
json.dump(report, open(os.environ.get('FINEB_OUT', 'results_hitnet_v2_fineb.json'), 'w'), indent=1, default=str)
