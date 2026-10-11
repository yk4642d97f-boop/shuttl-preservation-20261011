"""Compare unmodified service output to source human annotations."""
import importlib.util
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
spec = importlib.util.spec_from_file_location('hit_score', ROOT / 'research/hits/score.py')
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)
manifest = json.loads((OUT / 'manifest.json').read_text())
source = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / 'computer-archive.json'
analysis = json.loads(source.read_text())
truth = manifest['truth']
predictions = sorted(analysis['hits'], key=lambda h: h['frame'])
shots = {s['hit']['frame']: s for r in analysis['rallies'] for s in r['shots']}
types = dict(zip(
    ['放小球', '擋小球', '殺球', '挑球', '長球', '平球', '切球', '推球', '撲球', '勾球', '發短球', '發長球'],
    ['net', 'block', 'smash', 'lift', 'clear', 'drive', 'drop', 'push', 'kill', 'cross_net', 'short_serve', 'long_serve']))
report = {'source': source.name, 'video_sha256': manifest['sha256'],
          'scope': 'One preselected annotated singles validation rally, automatic court calibration. Not overall accuracy, doubles accuracy, or held-out test performance.',
          'processing_seconds': analysis['processing_time_seconds'],
          'video_seconds': manifest['duration_seconds'], 'truth_hits': len(truth),
          'predicted_hits': len(predictions), 'frame_shift_applied': 0,
          'has_camera': analysis['camera'] is not None, 'rallies': len(analysis['rallies']),
          'detection_by_tolerance': {}}
for tolerance in [1, 2, 3]:
    pairs, misses, extras = scorer.pair([r['frame'] for r in truth], predictions, tolerance)
    precision, recall, f1 = scorer.prf(len(pairs), len(extras), len(misses))
    report['detection_by_tolerance'][str(tolerance)] = {
        'true_positive': len(pairs), 'false_positive': len(extras), 'false_negative': len(misses),
        'precision': precision, 'recall': recall, 'f1': f1,
        'mean_absolute_error_frames': sum(abs(p[2]) for p in pairs) / len(pairs) if pairs else None}
pairs, misses, extras = scorer.pair([r['frame'] for r in truth], predictions, 2)
details = []
for gi, pi, offset in sorted(pairs):
    label = truth[gi]
    gt_type = types[label['official_class'].split('_', 1)[1]]
    frame = predictions[pi]['frame']
    predicted_type = shots.get(frame, {}).get('shot_type', 'unknown')
    details.append({'truth_frame': label['frame'], 'predicted_frame': frame, 'offset_frames': offset,
                    'truth_type': gt_type, 'predicted_type': predicted_type,
                    'correct': predicted_type == gt_type})
correct = sum(d['correct'] for d in details)
report['stroke_type'] = {'correct': correct, 'matched_hits': len(details),
                          'accuracy_among_matched': correct / len(details) if details else None,
                          'correct_over_all_truth': correct / len(truth), 'details': details}
report['not_evaluated'] = ['Per-frame shuttle position: no independent dense labels for this clip',
                            '3D speed, landing positions and match winner accuracy',
                            'Long recordings, doubles and mobile cellular network reliability']
destination = source.with_name(source.stem.replace('-archive', '') + '-accuracy.json')
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ['stroke_type', 'not_evaluated']}, ensure_ascii=False, indent=2))
print(f'Stroke type: {correct}/{len(truth)} = {correct / len(truth):.2%}')
