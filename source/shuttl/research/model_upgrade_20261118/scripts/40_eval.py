"""Evaluate ensembles on professional validation and VideoBadminton (corrected labels, hit-centred windows).

Usage: 40_eval.py [--final] [--out FILE] ARM=SPEC ...
  SPEC: 'released' | 'control17' | 'aux17' | run directory name under /dev/shm/claude/runs (optionally ':last')
Without --final only development data is read. --final additionally reads the two holdout dates and
must only be used for frozen candidates.
"""
import argparse, glob, json, sys
from pathlib import Path
import numpy as np, torch
import bstlib as bo
sys.argv[0] = '40_eval'
from importlib import import_module
tr = import_module('30_train')

DATA = Path('/root/shuttl-claude-20261118/data'); RUNS = Path('/dev/shm/claude/runs')
T = bo.TYPES


def paths(spec):
    if spec == 'released': return bo.released_paths()
    if spec == 'control17': return [bo.PREV / 'selected' / f'control-member-{i}.pt' for i in range(10)]
    if spec == 'aux17': return [bo.PREV / 'selected' / f'aux-member-{i}.pt' for i in range(10)]
    name, _, tag = spec.partition(':')
    files = sorted(glob.glob(str(RUNS / name / ('member-*-last.pt' if tag == 'last' else 'member-?.pt'))))
    if not files: files = sorted(glob.glob(str(Path('/root/shuttl-claude-20261118/models') / name / '*.pt')))
    assert files, spec
    return [Path(f) for f in files]


def vb_report(nets, style, split, labels='new'):
    z = np.load(DATA / f'vb_{style}_{split}.npz', allow_pickle=False)
    arrays = [torch.from_numpy(z[k]) for k in ('jnb', 'shuttle', 'pos', 'length')]
    truth = z['type'] if labels == 'new' else z['old_type']
    keep = truth >= 0
    lg = bo.logits_of(nets, arrays).numpy(); cls = lg.argmax(1); pred = bo.type_prediction(lg)
    m = bo.clip_metrics(pred[keep], truth[keep])
    gate = z['gate_prod'][keep]; ok = (pred == truth)[keep]
    side_ok = ((cls > 12).astype(int) == z['side'])[keep & (cls > 0) & (z['side'] >= 0)]
    r = dict(n=int(keep.sum()), accuracy=m['accuracy'], macro_recall=m['macro_recall'], macro_f1=m['macro_f1'], answered=m['answered'],
             per_class={k: v['recall'] for k, v in m['per_class'].items()},
             acc25=float((cls == z['label'])[keep & (z['side'] >= 0)].mean()) if labels == 'new' else None, side_accuracy=float(side_ok.mean()),
             gate_prod_rate=float(gate.mean()), accuracy_inside_gate=float(ok[gate].mean()), end_to_end_with_gate=float((ok & gate).mean()))
    if style == 'hit':
        for k in (-2, 2):
            j, s, p, l = tr.shift(*arrays, k)
            r[f'accuracy_shift{k:+d}'] = float((bo.type_prediction(bo.logits_of(nets, [j, s, p, l]).numpy()) == truth)[keep].mean())
    return r, ok, z['session'][keep]


def set_report(nets, name):
    """Extra labelled sets (BFMD, FineBadminton): a prediction is right when its type is in the row's allowed set."""
    z = np.load(DATA / f'{name}.npz', allow_pickle=False); keep = z['allowed'].any(1)
    arrays = [torch.from_numpy(z[k][keep]) for k in ('jnb', 'shuttle', 'pos', 'length')]
    al = z['allowed'][keep]; al12 = al[:, 1:13] | al[:, 13:25]
    out = {}
    for tag, arr in (('with_pos', arrays), ('no_pos', [arrays[0], arrays[1], torch.zeros_like(arrays[2]), arrays[3]])):
        lg = bo.logits_of(nets, arr).numpy(); cls = lg.argmax(1); pred = bo.type_prediction(lg)
        ok = (pred >= 0) & al12[np.arange(len(pred)), np.maximum(pred, 0)]
        out[tag] = float(ok.mean())
        if tag == 'with_pos':
            single = al12.sum(1) == 1; truth = al12.argmax(1)
            rec = [float(ok[single & (truth == c)].mean()) for c in range(12) if (single & (truth == c)).sum() >= 5]
            out['macro_recall'] = float(np.mean(rec)); sk = z['side'][keep] >= 0
            out['side_accuracy'] = float(((cls > 12).astype(int) == z['side'][keep])[sk & (cls > 0)].mean()); out['n'] = int(len(pred))
            oks = ok; groups = z['match'][keep]
    return out, oks, groups


def boot(ok_a, ok_b, groups, seed=20261118, draws=2000):
    u = np.unique(groups); rng = np.random.default_rng(seed)
    st = np.array([[(groups == g).sum(), ok_a[groups == g].sum(), ok_b[groups == g].sum()] for g in u])
    d = st[rng.integers(0, len(st), size=(draws, len(st)))].sum(1)
    return np.quantile((d[:, 1] - d[:, 2]) / d[:, 0], [.025, .975]).tolist()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--final', action='store_true'); ap.add_argument('--out'); ap.add_argument('--ref', default='')
    ap.add_argument('--clip', action='store_true', help='also evaluate the 2026-11-17 whole-clip protocol'); ap.add_argument('arms', nargs='+')
    a = ap.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    vj, vs, vp, vl, vy = bo.load_split('val'); report = {}; oks = {}
    splits = ['development'] + (['holdout', 'holdout2'] if a.final else [])
    for arm in a.arms:
        name, _, spec = arm.partition('='); spec = spec or name
        nets = [bo.load_net(p) for p in paths(spec)]
        r = dict(members=len(nets), pro_clean=bo.pro_metrics(bo.logits_of(nets, (vj, vs, vp, vl)), vy)['acc12'],
                 pro_nopos=bo.pro_metrics(bo.logits_of(nets, (vj, vs, torch.zeros_like(vp), vl)), vy)['acc12'])
        for k in (-2, 2):
            j, s, p, l = tr.shift(vj, vs, vp, vl, k)
            r[f'pro_clean_shift{k:+d}'] = bo.pro_metrics(bo.logits_of(nets, (j, s, p, l)), vy)['acc12']
        for split in splits:
            r[f'vb_{split}'], ok, groups = vb_report(nets, 'hit', split); oks[(name, split)] = (ok, groups)
            if a.clip:
                r[f'clip17_{split}_oldlabels'] = vb_report(nets, 'clip', split, 'old')[0]
                r[f'clip17_{split}_newlabels'] = vb_report(nets, 'clip', split, 'new')[0]
        for extra in ['bfmd_dev', 'fineb_dev'] + (['bfmd_test', 'fineb_test'] if a.final else []):
            if (DATA / f'{extra}.npz').exists():
                r[extra], ok, groups = set_report(nets, extra); oks[(name, extra)] = (ok, groups)
        report[name] = r
        line = f"{name:<18} m={len(nets):<2} pro {r['pro_clean']:.4f}/{r['pro_nopos']:.4f} shift±2 {r['pro_clean_shift-2']:.3f}/{r['pro_clean_shift+2']:.3f}"
        for split in splits:
            v = r[f'vb_{split}']
            line += f" | {split[:4]}{split[-1] if split[-1]=='2' else ''} acc {v['accuracy']:.4f} mR {v['macro_recall']:.4f} side {v['side_accuracy']:.3f} gate {v['gate_prod_rate']:.2f} e2e {v['end_to_end_with_gate']:.3f} sh {v['accuracy_shift-2']:.3f}/{v['accuracy_shift+2']:.3f}"
        for extra in ('bfmd_dev', 'bfmd_test', 'fineb_dev', 'fineb_test'):
            if extra in r: line += f" | {extra} {r[extra]['with_pos']:.4f}/{r[extra]['no_pos']:.4f} mR {r[extra]['macro_recall']:.3f}"
        print(line, flush=True)
        del nets
    if a.ref:
        for arm in report:
            if arm == a.ref: continue
            for extra in [k[1] for k in oks if k[0] == arm and k[1] not in splits]:
                ok, groups = oks[(arm, extra)]; ok_ref, _ = oks[(a.ref, extra)]
                report[arm][extra]['delta_vs_' + a.ref] = dict(delta=float(ok.mean() - ok_ref.mean()), ci95=boot(ok, ok_ref, groups), groups=int(len(np.unique(groups))))
                print(f"{arm} - {a.ref} on {extra}: {ok.mean() - ok_ref.mean():+.4f} CI95 {report[arm][extra]['delta_vs_' + a.ref]['ci95']}")
            for split in splits:
                ok, groups = oks[(arm, split)]; ok_ref, _ = oks[(a.ref, split)]
                report[arm][f'vb_{split}']['delta_vs_' + a.ref] = dict(delta=float(ok.mean() - ok_ref.mean()), ci95=boot(ok, ok_ref, groups), groups=int(len(np.unique(groups))))
                print(f"{arm} - {a.ref} on {split}: {ok.mean() - ok_ref.mean():+.4f} CI95 {report[arm][f'vb_{split}']['delta_vs_' + a.ref]['ci95']}")
    if a.out: Path(a.out).write_text(json.dumps(report, indent=1))


if __name__ == '__main__': main()
