"""Compare a candidate to its initializer and the frozen ten-member ensemble on validation only."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import torch


def metrics(truth, logits):
    confusion = np.zeros((25, 25), dtype=np.int64)
    np.add.at(confusion, (truth, logits.argmax(1)), 1)
    denominator = confusion.sum(0) + confusion.sum(1)
    f1 = np.divide(2 * confusion.diagonal(), denominator,
                   out=np.zeros(25), where=denominator > 0)
    return dict(correct=int(confusion.trace()), examples=len(truth),
                accuracy=float(confusion.trace() / len(truth)),
                macro_f1_24=float(f1[1:].mean()), confusion=confusion.tolist())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    a = p.parse_args()
    root = a.root.resolve()
    if a.out.exists():
        raise FileExistsError('Comparison already exists')
    if a.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; refusing CPU fallback')
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    spec = importlib.util.spec_from_file_location('run_bst', root / 'research/cloud_upgrade/cloud/run_bst.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from app.services.tracking.bst import BST
    from app.services.tracking.bst_vendor.bst import BST_CG_AP
    data_path = root / 'research/cloud_upgrade/data/bst_fixed30/manifest.json'
    data = module.dataset(data_path, 'val')
    if data['matches'] != {'041'}:
        raise ValueError('Expected frozen validation only')
    manifest = root / 'research/cloud_upgrade/artifacts/bst_seq30/manifest.json'
    baseline = BST(manifest, a.device)

    @torch.inference_mode()
    def forward(net):
        logits = []
        for start in range(0, len(data['label']), 32):
            logits.append(net(*module.batch(data, slice(start, start + 32), a.device)).cpu().numpy())
        result = np.concatenate(logits)
        if result.shape != (len(data['label']), 25) or not np.isfinite(result).all():
            raise ValueError('Invalid model output')
        return result

    members = [forward(net) for net in baseline.nets]
    ensemble = np.zeros_like(members[0])
    for logits in members:
        ensemble += logits / len(members)
    checkpoint = torch.load(a.candidate, map_location='cpu', weights_only=True)
    net = BST_CG_AP(72, 30, n_class=25, depth_tem=2, depth_inter=1).to(a.device).eval()
    net.load_state_dict(checkpoint['state'], strict=True)
    candidate = forward(net)
    truth = data['label'].numpy()
    rows = {name: metrics(truth, logits) for name, logits in
            [('released_member_1', members[0]), ('released_ensemble_10', ensemble), ('candidate', candidate)]}
    for field in ('accuracy', 'macro_f1_24'):
        if not np.isclose(rows['candidate'][field], checkpoint['validation'][field], atol=1e-12, rtol=0):
            raise ValueError('Candidate validation does not reproduce training checkpoint')
    report = dict(device=a.device, torch=torch.__version__,
                  data_manifest_sha256=module.sha(data_path),
                  baseline_manifest_sha256=module.sha(manifest),
                  candidate_sha256=module.sha(a.candidate), candidate_step=checkpoint['step'],
                  metrics=rows,
                  changed_vs_ensemble=int((candidate.argmax(1) != ensemble.argmax(1)).sum()),
                  scope='1126 available labeled-hit validation clips from match041; excludes 28 known clips without pose. Not blind test, full-video or doubles accuracy; no deployment selection made here.')
    a.out.mkdir(parents=True)
    np.savez_compressed(a.out / 'predictions.npz', truth=truth, name=data['name'],
                        initializer=members[0], ensemble=ensemble, candidate=candidate)
    (a.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: {m: v for m, v in row.items() if m != 'confusion'} for k, row in rows.items()}, indent=2))


if __name__ == '__main__':
    main()
