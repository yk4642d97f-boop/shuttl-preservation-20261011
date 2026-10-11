#!/usr/bin/env python3
"""Run the app's court calibration on the R7 set (make_set.py) and score it against phonesim's
GT camera → CSV + summary.

Per case: accepted, reason, source, keypoint px error (median / max over the GT keypoints
inside the image, distorted pixels), floor error (m, app camera back-projecting the GT pixels),
focal rel error, FA by definition (c): accepted with floor_max > 0.10 m AND px_max > 3 px.

usage: eval.py [--out results.csv] [--frames /tmp/r7set] [--workers 4]
               [--code <court_calibration.py to test instead of the live one>]
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
import json
import time
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
FIELDS = ["name", "config", "seed", "doubles", "accepted", "reason", "source", "confidence", "px_med", "px_max",
          "floor_med_m", "floor_max_m", "focal_rel", "n_kp", "n_t", "n_l", "n_absent", "coverage",
          "explained_frac", "rmse", "margin", "calib_s"]
FLOOR_M, PX = 0.10, 3.0


def run_one(args: tuple[dict, str]) -> dict:
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    import calib_regress  # noqa: F401  (backend on sys.path)
    from app.services.tracking import court_model as cm
    from app.services.tracking.camera import CameraModel
    cc = calib_regress.load_cc()
    case, frames_dir = args
    d = Path(frames_dir) / case["name"]
    frames = [cv2.imread(str(p)) for p in sorted(d.glob("frame_*.jpg"))]
    gt = json.load(open(d / "gt.json"))
    h, w = frames[0].shape[:2]
    diag: dict = {}
    t0 = time.perf_counter()
    cam = cc.calibrate_from_frames(frames, (w, h), diagnostics=diag)
    row = {"name": case["name"], "config": case["config"], "seed": case["seed"], "doubles": gt["doubles"],
           "accepted": cam is not None, "reason": diag.get("reason"), "source": diag.get("source"),
           "calib_s": round(time.perf_counter() - t0, 2)}
    for k in ("n_t", "n_l", "n_absent", "coverage", "explained_frac", "rmse", "margin"):
        row[k] = diag.get(k)
    if cam is not None:
        names, P = cm.keypoints_array()
        inside = np.array([gt["keypoints"][n]["in_image"] for n in names])
        uv_gt = np.array([gt["keypoints"][n]["px"] for n in names], float)[inside]
        Pw = P[inside]
        px = np.linalg.norm(cam.project(Pw) - uv_gt, axis=1)
        floor_pts = Pw[:, 2] == 0
        g = cam.pixel_to_floor(uv_gt[floor_pts])
        fl = np.linalg.norm(g[:, :2] - Pw[floor_pts, :2], axis=1)
        fl = fl[np.isfinite(fl)]
        gcam = CameraModel.from_dict(gt["camera"])
        row.update(confidence=cam.confidence, px_med=float(np.median(px)), px_max=float(px.max()),
                   floor_med_m=float(np.median(fl)) if len(fl) else float("inf"),
                   floor_max_m=float(fl.max()) if len(fl) else float("inf"),
                   focal_rel=abs(cam.K[0, 0] / gcam.K[0, 0] - 1), n_kp=int(inside.sum()))
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "results.csv"))
    ap.add_argument("--frames", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--code", default=None)
    a = ap.parse_args()
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    if a.code:
        os.environ["CALIB_REGRESS_CODE"] = str(Path(a.code).resolve())
    man = json.load(open(HERE / "manifest.json"))
    frames_dir = a.frames or man["frames_dir"]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max(1, min(4, a.workers))) as ex:
        rows = list(ex.map(run_one, [(c, frames_dir) for c in man["cases"]]))
    with open(a.out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        wr.writeheader()
        wr.writerows(rows)
    fa = lambda r: r["accepted"] and r["floor_max_m"] > FLOOR_M and r["px_max"] > PX
    for grp in sorted({r["config"] if not r["name"].startswith("batch") else "batch" for r in rows}):
        rs = [r for r in rows if (r["config"] if not r["name"].startswith("batch") else "batch") == grp]
        acc = [r for r in rs if r["accepted"]]
        worst = lambda k: max((r[k] for r in acc), default=float("nan"))
        print(f"{grp:12s} accepted {len(acc):2d}/{len(rs):2d}  FA {sum(fa(r) for r in rs)}  worst px_max "
              f"{worst('px_max'):.2f}  floor_max {worst('floor_max_m'):.3f} m  focal_rel {worst('focal_rel'):.4f}"
              f"  rejects {dict(Counter(r['reason'] for r in rs if not r['accepted']))}")
    acc = [r for r in rows if r["accepted"]]
    print(f"ALL accepted {len(acc)}/{len(rows)}  FA {sum(fa(r) for r in rows)}  doubles "
          f"{sum(r['accepted'] for r in rows if r['doubles'])}/{sum(bool(r['doubles']) for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
