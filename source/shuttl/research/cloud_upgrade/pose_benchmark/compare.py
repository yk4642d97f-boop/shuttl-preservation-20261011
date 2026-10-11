"""Verify identical evidence inputs before comparing frozen candidate reports."""
import argparse
import json
import numpy as np
from adapters import HERE, ROOT, sha
from panel import R, write_new


def compare(panel_name, device):
    panel_path = HERE / 'panels' / f'{panel_name}.json'
    panel = json.loads(panel_path.read_text())
    base = HERE / 'results' / panel_name
    names = ['rtmpose_m', 'rtmpose_x', 'vitpose_plus_base']
    reports, arrays, starts = {}, {}, {}
    for name in names:
        path = base / f'{name}_{device}'
        reports[name] = r = json.loads((path / 'report.json').read_text())
        starts[name] = json.loads((path / 'started.json').read_text())
        if r['panel_sha256'] != sha(panel_path) or r['outputs_sha256'] != sha(path / 'outputs.npz'):
            raise ValueError('Stale or changed report input/output')
        if [(e['id'], e['class']) for e in panel['events']] != [(e['id'], e['label']) for e in r['predictions']]:
            raise ValueError('Selection or label denominator changed')
        with np.load(path / 'outputs.npz') as z:
            arrays[name] = {k: z[k] for k in z.files}
    baseline = arrays[names[0]]
    for name in names[1:]:
        if reports[name]['pixel_sha256'] != reports[names[0]]['pixel_sha256']:
            raise ValueError('Decoded pixels differ')
        if starts[name]['code_sha256'] != starts[names[0]]['code_sha256']:
            raise ValueError('Benchmark code changed between arms')
        for field in ('frame', 'box', 'pos', 'shuttle'):
            np.testing.assert_array_equal(arrays[name][field], baseline[field])
    with np.load(ROOT / 'research/rtmpose/pose/041.npz') as z:
        lookup = {int(f): i for i, f in enumerate(z['frame'])}
        original = z['kp'][[lookup[int(f)] for f in baseline['frame']], :, :17]
    finite = np.isfinite(original) & np.isfinite(baseline['kp'])
    parity = dict(shared_finite_values=int(finite.sum()),
                  max_abs_coordinate_or_score_error=float(np.abs(original[finite] - baseline['kp'][finite]).max()),
                  missing_mask_differences=int(np.count_nonzero(np.isfinite(original) != np.isfinite(baseline['kp']))))
    paired = {}
    br = reports['rtmpose_m']['predictions']
    for name in names[1:]:
        changes = []
        gains = losses = 0
        for b, c in zip(br, reports[name]['predictions']):
            if b['prediction'] != c['prediction']:
                gains += b['prediction'] != b['label'] and c['prediction'] == c['label']
                losses += b['prediction'] == b['label'] and c['prediction'] != c['label']
                changes.append(dict(id=b['id'], label=b['label'], baseline=b['prediction'], candidate=c['prediction']))
        paired[name] = dict(gains=gains, losses=losses, changed=changes)
    result = dict(panel_sha256=sha(panel_path), same_decoded_pixels=True, same_boxes_positions_shuttle=True,
                  scope=panel['protocol']['scope'], cached_baseline_pose_parity=parity,
                  metrics={name: reports[name]['metrics'] for name in names}, paired=paired,
                  timing={name: {k: reports[name][k] for k in ('inference_seconds', 'poses_per_second', 'frame_count', 'pose_count')} for name in names},
                  report_hashes={name: sha(base / f'{name}_{device}' / 'report.json') for name in names},
                  decision='Research comparison only; do not replace production from a small, class-balanced validation panel.')
    write_new(base / f'comparison_{device}.json', result)
    for name in names:
        m = result['metrics'][name]
        print(name, f"{m['exact_correct']}/{m['n']}", 'exact', round(m['exact_accuracy'], 4), 'type', round(m['type_accuracy'], 4), flush=True)
    print('cached_baseline_pose_parity', parity)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--panel', choices=['small', 'full'], default='small')
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    a = p.parse_args()
    compare(a.panel, a.device)
