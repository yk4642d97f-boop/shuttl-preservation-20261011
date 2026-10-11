#!/usr/bin/env python3
"""calib_regress.py — regression check of the automatic court calibration.

Usage:
  ./calib_regress.py [--workers 4] [--baseline calib_sweep_baseline.csv]
                     [--out calib_sweep_after.csv] [--real] [--zoom] [--skip-sweep]

  sweep   the calib_sweep.py grid (360 synthetic tripod cases, same seeds); prints a
          before/after table per height and distance against the baseline CSV.
          FAILS if any accepted camera has a worst floor error > 0.15 m.
  --real  the 29 TrackNetV2 Test clips vs calib_real_baseline.json: FAILS unless
          accept/reject is identical and accepted cameras agree within 0.5 px.
  --zoom  the 1080p broadcast clip (data/_offline_hd): FAILS unless it is rejected or
          every far-court line is within 5 px (median residual) on every 60th frame.
  held-out scenes: --seed-offset N (same grid, other random scenes); make the matching
          baseline from the pre-change code first:
            ./calib_regress.py --seed-offset 5000 --code <backup court_calibration.py> \\
                --baseline heldout_before.csv
            ./calib_regress.py --seed-offset 5000 --baseline heldout_before.csv
Runs at nice 10 with at most 4 worker processes. Exit code 0 = all requested checks pass.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_VENV = Path(__file__).resolve().parents[2] / "backend" / ".venv" / "bin" / "python"
if _VENV.exists() and Path(sys.executable).resolve() != _VENV.resolve():
    os.execv(str(_VENV), [str(_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import calib_sweep as cs  # noqa: E402

REPO = HERE.parents[1]
ZOOM_CLIP = HERE / "data/_offline_hd/Documents/Matches/phone_sample_1080p60.mov"
# Metrics (coordinator D2, 2026-09-28): a FALSE ACCEPT (wrong camera) = accepted, worst
# floor error > FLOOR_M and worst keypoint error > PX (CourtLock's 3 px) — must be 0; an
# IMPRECISE accept = floor > FLOOR_M but keypoints <= PX (right camera at its resolution
# limit, reported with far_m_per_px). The strict floor-only count is always shown too.
FLOOR_M, PX = 0.10, 3.0
FIELDS = ["case", "height_m", "dist_m", "lat_m", "roll_deg", "scene", "seed", "style", "accepted",
          "reason", "px_med", "px_max", "floor_med_m", "floor_max_m", "focal_rel", "confidence",
          "n_t", "n_l", "n_absent", "explained_frac", "coverage", "margin", "far_m_per_px", "source"]


def load_cc():
    """court_calibration, or the file named by $CALIB_REGRESS_CODE (e.g. the pre-change backup)."""
    path = os.environ.get("CALIB_REGRESS_CODE")
    if not path:
        from app.services.tracking import court_calibration as cc
        return cc
    import importlib.util
    spec = importlib.util.spec_from_file_location("court_calibration_alt", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_one(case: dict) -> dict:
    import cv2
    cv2.setNumThreads(1)
    from tests import test_court_calibration as t
    cc = load_cc()
    cam = cs.make_camera(case["height_m"], case["dist_m"], case["lat_m"], case["roll_deg"])
    frames = t.render_frames(cam, np.random.default_rng(case["seed"]), n=case["frames"], style=case["style"])
    diag: dict = {}
    est = cc.calibrate_from_frames(frames, (cs.W, cs.H), diagnostics=diag)
    row = {k: case.get(k) for k in FIELDS}
    row.update(accepted=est is not None, reason=diag.get("reason", ""),
               px_med=None, px_max=None, floor_med_m=None, floor_max_m=None, focal_rel=None, confidence=None,
               far_m_per_px=None)
    if est is not None:
        row.update(cs.errors(cam, est), confidence=est.confidence)
        from app.services.tracking import court_calibration as live      # works for --code too
        row["far_m_per_px"] = live.far_m_per_px(est)
    row["source"] = diag.get("source", "")
    row.update({k: diag.get(k) for k in ("n_t", "n_l", "n_absent", "explained_frac", "coverage", "margin")})
    return row


def sweep(workers: int, out: Path, seed_offset: int = 0) -> list[dict]:
    cases = cs.build_cases(3, 5, False)
    for c in cases:                      # held-out scenes: same grid, different random scenes
        c["seed"] += seed_offset
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, min(4, workers))) as ex:
        for i, fu in enumerate(as_completed([ex.submit(run_one, c) for c in cases]), 1):
            rows.append(fu.result())
            print(f"\r  sweep {i}/{len(cases)}", end="", flush=True)
    print()
    rows.sort(key=lambda r: r["case"])
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return rows


def _num(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except ValueError:
        return None
def classify(r: dict) -> str:
    """'rej' | 'FA' (wrong camera) | 'imprecise' | 'ok' — coordinator D2 definitions."""
    if str(r["accepted"]) != "True":
        return "rej"
    fl, px = _num(r["floor_max_m"]) or 0.0, _num(r["px_max"]) or 0.0
    if fl > FLOOR_M:
        return "FA" if px > PX else "imprecise"
    return "ok"


def table(before: list[dict], after: list[dict]) -> tuple[str, list]:
    """Per height / distance: accepted before → after, worst floor error, FA / imprecise /
    strict (floor > FLOOR_M) counts; the FA list decides pass/fail."""
    lines = [f"{'cell':10s} {'accepted before':>16s} {'after':>8s}  {'worst floor m':>14s}"
             f"  FA b→a  imprecise b→a  strict>{FLOOR_M}m b→a"]
    cnt = lambda rs, k: sum(classify(r) == k for r in rs)
    strict = lambda rs: sum(classify(r) in ("FA", "imprecise") for r in rs)
    for key, vals in (("height_m", cs.HEIGHTS), ("dist_m", cs.DISTANCES)):
        for v in vals:
            b = [r for r in before if _num(r[key]) == v]
            a = [r for r in after if _num(r[key]) == v]
            acc = lambda rs: [r for r in rs if str(r["accepted"]) == "True"]
            worst = lambda rs: max([_num(r["floor_max_m"]) or 0 for r in acc(rs)] or [0])
            lines.append(f"{key[0]}={v:<8} {len(acc(b)):>9d}/{len(b):<3d} {100 * len(acc(b)) / len(b):3.0f}%"
                         f" {len(acc(a)):>4d} {100 * len(acc(a)) / len(a):3.0f}%  {worst(b):6.3f}→{worst(a):6.3f}"
                         f"  {cnt(b, 'FA'):2d}→{cnt(a, 'FA'):<2d}  {cnt(b, 'imprecise'):5d}→{cnt(a, 'imprecise'):<5d}"
                         f"  {strict(b):8d}→{strict(a)}")
    tot = lambda rs: sum(str(r["accepted"]) == "True" for r in rs)
    lines.append(f"{'all':10s} {tot(before):>9d}/{len(before):<3d}      {tot(after):>4d}")
    wrong = [r for r in after if classify(r) == "FA"]
    imp = [r for r in after if classify(r) == "imprecise"]
    lost = [r["case"] for r, b in zip(after, before) if str(b["accepted"]) == "True" and str(r["accepted"]) != "True"]
    gained = [r["case"] for r, b in zip(after, before) if str(b["accepted"]) != "True" and str(r["accepted"]) == "True"]
    lines.append(f"FALSE ACCEPTS (floor > {FLOOR_M} m AND px > {PX}): before "
                 f"{[r['case'] for r in before if classify(r) == 'FA']}  after {[r['case'] for r in wrong]}")
    lines.append(f"imprecise accepts after (floor > {FLOOR_M} m, px <= {PX}): "
                 + ", ".join(f"{r['case']} ({_num(r['floor_max_m']):.3f} m, {_num(r['px_max']):.2f} px, "
                             f"far_m_per_px {_num(r.get('far_m_per_px')) or float('nan'):.3f})" for r in imp))
    lines.append(f"accepted before but rejected now: {lost};  newly accepted: {gained}")
    return "\n".join(lines), wrong


def check_real(baseline: Path) -> bool:
    from app.services.tracking import court_calibration as cc, court_model as cm, video_io
    from app.services.tracking.camera import CameraModel
    ok = True
    worst = 0.0
    for c in json.loads(baseline.read_text())["clips"]:
        path = str(REPO / c["clip"])
        meta = video_io.probe(path)
        frames = [f for _, f in video_io.sample_frames(path, 24, meta.n_frames)]
        cam = cc.calibrate_from_frames(frames, (meta.width, meta.height))
        same = (cam is not None) == bool(c["accepted"])
        d = float("nan")
        if cam is not None and c["camera"]:
            ref = CameraModel.from_dict(c["camera"])
            _, P = cm.keypoints_array()
            d = float(np.nanmax(np.linalg.norm(cam.project(P) - ref.project(P), axis=1)))
            worst = max(worst, d)
        ok &= same and not d > 0.5
        print(f"  {c['clip'][-24:]}: {'same' if same else 'FLIP'} accept={cam is not None} kp diff {d:.3g} px")
    print(f"real: {'PASS' if ok else 'FAIL'} (max keypoint diff vs baseline {worst:.3g} px)")
    return ok


def check_zoom() -> bool:
    from app.services.tracking import court_calibration as cc, court_model as cm, video_io
    meta = video_io.probe(str(ZOOM_CLIP))
    frames = [f for _, f in video_io.sample_frames(str(ZOOM_CLIP), 24, meta.n_frames)]
    diag: dict = {}
    cam = cc.calibrate_from_frames(frames, (meta.width, meta.height), diagnostics=diag)
    if cam is None:
        print(f"zoom: rejected ({diag.get('reason')}) → PASS")
        return True
    names = list(cm.COURT_LINES)
    far = [k for k, n in enumerate(names) if n.startswith("far_")]
    per: dict[int, list[float]] = {k: [] for k in far}      # per frame: median |residual| px
    missed: dict[int, int] = {k: 0 for k in far}           # frames with < 50 % of the line found
    p = cc._cam_params(cam, bool(cam.dist[0]))
    n_frames = 0
    for i, f in video_io.iter_frames(str(ZOOM_CLIP), step=60):
        n_frames += 1
        feat = cc._Features(f)
        idx, found, tg, nn, _ = cc._match_lines(feat, p, cam.K[0, 2], cam.K[1, 2], cc._FINE, 80.0)
        r = np.abs(np.sum((cc._project_params(p, cc._FINE[0][idx], cam.K[0, 2], cam.K[1, 2]) - tg) * nn, 1))
        lid = cc._FINE[2][idx]
        for k in far:
            on = lid == k
            if on.sum() < 5:
                continue
            if found[on].mean() < 0.5:
                missed[k] += 1
            else:
                per[k].append(float(np.median(r[on & found])))
    # p90 over frames per line: robust to the odd frame where a player covers the line
    p90 = {names[k]: float(np.percentile(v, 90)) for k, v in per.items() if v}
    worst = max(p90.values() or [np.inf])
    miss = max(missed.values()) / max(n_frames, 1)
    ok = worst < 5.0 and miss <= 0.1
    print(f"zoom: accepted conf {cam.confidence:.2f}; far lines over {n_frames} frames: p90 median residual "
          + ", ".join(f"{n} {v:.2f}" for n, v in p90.items())
          + f" px; max single frame {max(max(v) for v in per.values() if v):.1f} px; "
            f"worst missed-frame fraction {miss:.2f} → {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--baseline", default=str(HERE / "calib_sweep_baseline.csv"))
    ap.add_argument("--out", default=str(HERE / "calib_sweep_after.csv"))
    ap.add_argument("--real-baseline", default=str(HERE / "calib_real_baseline.json"))
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--zoom", action="store_true")
    ap.add_argument("--skip-sweep", action="store_true")
    ap.add_argument("--seed-offset", type=int, default=0,
                    help="held-out scenes (baseline must be a sweep with the same offset)")
    ap.add_argument("--code", default=None,
                    help="court_calibration.py file to test instead of the live one (e.g. a backup)")
    a = ap.parse_args()
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:        # already niced (e.g. /tmp/heavy.sh) → keep
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    if a.code:
        os.environ["CALIB_REGRESS_CODE"] = str(Path(a.code).resolve())
    ok = True
    if not a.skip_sweep and a.code and not Path(a.baseline).exists():
        sweep(a.workers, Path(a.baseline), a.seed_offset)        # just produce a baseline
        print(f"baseline written: {a.baseline}")
        return 0
    if not a.skip_sweep:
        after = sweep(a.workers, Path(a.out), a.seed_offset)
        before = list(csv.DictReader(open(a.baseline)))
        txt, wrong = table(before, [{k: str(v) for k, v in r.items()} for r in after])
        print(txt)
        ok &= not wrong
    if a.real:
        ok &= check_real(Path(a.real_baseline))
    if a.zoom:
        ok &= check_zoom()
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
