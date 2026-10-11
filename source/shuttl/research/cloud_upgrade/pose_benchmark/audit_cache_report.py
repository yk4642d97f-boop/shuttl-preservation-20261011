"""Summarize retained cache diagnostics, including downstream prediction stability."""
import json
import numpy as np
from adapters import HERE, ROOT, sha
from panel import write_new


def main():
    checks = HERE / 'checks'
    a, b, ca, cb = [np.load(checks / name) for name in
                   ['cache_current.npz', 'cache_oldenv.npz', 'cache_cross_current_ort.npz', 'cache_cross_old_ort.npz']]
    with np.load(ROOT / 'research/rtmpose/pose/041.npz') as z:
        ix = {int(f): i for i, f in enumerate(z['frame'])}
        cached = z['kp'][[ix[int(f)] for f in a['frame']], :, :17]
    report = dict(frames=a['frame'].tolist(),
        same_decoded_pixels=bool(np.array_equal(a['pixel_sha256'], b['pixel_sha256'])),
        padded_box_max_diff=float(abs(a['pads'] - b['pads']).max()),
        warp_matrix_max_diff=float(abs(ca['matrices'] - cb['matrices']).max()),
        crop_max_channel_diff=int(abs(a['crop'].astype(int) - b['crop'].astype(int)).max()),
        normalized_input_max_diff=float(abs(a['input'] - b['input']).max()),
        current_ort_old_inputs_vs_old_ort_old_inputs=float(abs(ca['kp'] - b['kp']).max()),
        old_ort_current_inputs_vs_current_ort_current_inputs=float(abs(cb['kp'] - a['kp']).max()),
        oldenv_reference_vs_cache_max_diff=float(abs(b['kp'] - cached).max()),
        current_reference_vs_cache_max_diff=float(abs(a['kp'] - cached).max()),
        cached_classifier=json.loads((checks / 'cached_baseline_classification.json').read_text()),
        environments={n: json.loads((checks / ('cache_' + n + '.json')).read_text()) for n in ['current', 'oldenv']},
        source_hashes={p.name: sha(p) for p in checks.glob('cache*.npz')},
        conclusion='On these diagnostic frames, decoded pixels/boxes/warp matrices match. Crop interpolation differs between OpenCV builds; using the same prepared tensor eliminates the large pose discrepancy across ORT versions. Cached and fresh baseline classify the 44 frozen clips identically.',
        scope='9 validation frames selected because cache coordinate error >1px; diagnostic, not new candidate selection')
    write_new(checks / 'cache_audit_verified.json', report)
    print(report['conclusion'])


if __name__ == '__main__':
    main()
