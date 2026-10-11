#!/usr/bin/env python3
"""calib_sweep2 runner: every case of cases.py through calibrate_from_frames → CSV.

Usage (from anywhere; runs under backend/.venv, nice 10, <= 4 workers):
  run.py --out results_after.csv [--grids old,low,rec,hard] [--workers 4]
         [--code <court_calibration.py to test instead of the live one>]
  report.py results_after.csv [--before results_before.csv]     (tables)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_VENV = Path(__file__).resolve().parents[3] / "backend" / ".venv" / "bin" / "python"
if _VENV.exists() and Path(sys.executable).resolve() != _VENV.resolve():
    os.execv(str(_VENV), [str(_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

import argparse
import csv
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cases  # noqa: E402

FIELDS = ["id", "grid", "kind", "height_m", "dist_m", "lat_m", "roll_deg", "pitch_deg", "scene", "seed",
          "style", "focal", "old_case", "whole_court", "accepted", "reason", "source", "frames_agree",
          "px_med", "px_max", "floor_med_m", "floor_max_m", "focal_rel", "confidence", "margin",
          "n_t", "n_l", "n_absent", "t_straddle", "coverage", "explained_frac", "far_m_per_px", "calib_s",
          "line_colour"]


def run_one(case: dict) -> dict:
    import cv2
    cv2.setNumThreads(1)
    sys.path.insert(0, str(HERE.parent))
    import calib_regress
    import calib_sweep as cs
    import scenes
    cc = calib_regress.load_cc()
    cam = cases.make_camera(case["height_m"], case["dist_m"], case["lat_m"], case["roll_deg"],
                            case["pitch_deg"], case["focal"])
    frames = scenes.render(case, cam)
    diag: dict = {}
    t0 = time.perf_counter()
    try:
        est = cc.calibrate_from_frames(frames, (cases.W, cases.H), diagnostics=diag)
    except Exception as e:                             # a crash is a result (old code: KeyError)
        est = None
        diag = {"reason": f"exception:{type(e).__name__}"}
    row = {k: case.get(k) for k in FIELDS}
    row.update(whole_court=cases.whole_court_in_frame(cam), accepted=est is not None,
               reason=diag.get("reason", ""), source=diag.get("source", ""),
               frames_agree=" ".join(map(str, diag.get("frames_agree") or [])),
               calib_s=round(time.perf_counter() - t0, 2))
    for k in ("px_med", "px_max", "floor_med_m", "floor_max_m", "focal_rel", "confidence", "far_m_per_px"):
        row[k] = None
    if est is not None:
        row.update(cs.errors(cam, est), confidence=est.confidence)
        from app.services.tracking import court_calibration as live      # works for --code too
        row["far_m_per_px"] = live.far_m_per_px(est)
    for k in ("margin", "n_t", "n_l", "n_absent", "t_straddle", "coverage", "explained_frac", "line_colour"):
        row[k] = diag.get(k)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--grids", default="old,low,rec,hard")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--code", default=None)
    a = ap.parse_args()
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:        # already niced (e.g. /tmp/heavy.sh) → keep
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    if a.code:
        os.environ["CALIB_REGRESS_CODE"] = str(Path(a.code).resolve())
    todo = cases.build(tuple(a.grids.split(",")))
    out = Path(a.out)
    done: dict[int, dict] = {}
    if out.exists():                                   # resume
        done = {int(r["id"]): r for r in csv.DictReader(open(out))}
    todo = [c for c in todo if c["id"] not in done]
    t0 = time.time()
    with open(out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not done:
            w.writeheader()
        with ProcessPoolExecutor(max_workers=max(1, min(4, a.workers))) as ex:
            futs = [ex.submit(run_one, c) for c in todo]
            for i, fu in enumerate(as_completed(futs), 1):
                w.writerow(fu.result())
                f.flush()
                if i % 20 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
