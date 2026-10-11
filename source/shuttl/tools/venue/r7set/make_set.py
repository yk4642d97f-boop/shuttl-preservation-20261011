#!/usr/bin/env python3
"""R7 phonesim calibration set: render N_FRAMES evenly spaced frames per clip (the app's
calibration sampling: video_io.sample_frames(path, 24)) + ground truth, for eval.py.

Cases (deterministic): the 5 configs of deliverables/DELIVERY_R7/configs × SEEDS_PER_CONFIG
seeds (config seed + k), plus N_BATCH clips of `phonesim batch` variations (batch_variation,
rng seed 7 — same draws as `phonesim batch --seed 7`).

Frames are written as JPEG q92 (the app sees H.264 video anyway) to --frames (default
/tmp/r7set: ~0.4 MB/frame); the manifest (case → config, seed, overrides, GT camera) goes to
tools/venue/r7set/manifest.json. Resumable: finished cases (gt.json present) are skipped.

usage: make_set.py [--frames /tmp/r7set] [--workers 4] [--only name,...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R7 = HERE.parents[2] / "deliverables" / "DELIVERY_R7"
sys.path.insert(0, str(R7 / "src"))

CONFIGS = ("default", "doubles", "hard_lights", "multicourt", "closeup")
SEEDS_PER_CONFIG = 6
N_BATCH = 20
N_FRAMES = 24
DURATION_S = 20.0


def build_cases() -> list[dict]:
    import numpy as np
    import yaml
    from phonesim.cli import batch_variation
    cases = []
    for c in CONFIGS:
        base = int(yaml.safe_load(open(R7 / "configs" / f"{c}.yaml"))["seed"])
        for k in range(SEEDS_PER_CONFIG):
            cases.append({"name": f"{c}_s{base + k}", "config": c, "seed": base + k,
                          "overrides": {"duration_s": DURATION_S}})
    rng = np.random.default_rng(7)
    for i in range(N_BATCH):
        var = batch_variation(rng, i)
        var["duration_s"] = DURATION_S
        cases.append({"name": f"batch_{i:03d}", "config": "default", "seed": 7000 + i, "overrides": var})
    return cases


def render_case(case: dict, frames_dir: str) -> dict:
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    from phonesim.config import load
    from phonesim.gt import court_keypoints_px
    from phonesim.pipeline import build
    out = Path(frames_dir) / case["name"]
    if (out / "gt.json").exists():
        return json.load(open(out / "gt.json"))
    out.mkdir(parents=True, exist_ok=True)
    cfg = load(str(R7 / "configs" / f"{case['config']}.yaml"), case["overrides"])
    R, r = build(cfg, case["seed"])
    fps = float(r["fps"])
    total = int(round(float(r["duration_s"]) * fps))
    for k, i in enumerate(np.linspace(0, total - 1, N_FRAMES).astype(int)):
        bgr, _, _ = R.render(int(i), float(i) / fps)
        cv2.imwrite(str(out / f"frame_{k:02d}.jpg"), bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    gt = {"case": case, "camera": R.cam.to_dict(), "keypoints": court_keypoints_px(R.cam),
          "doubles": bool(r["doubles"]), "scene": r["scene"], "fps": fps}
    json.dump(gt, open(out / "gt.json", "w"), default=float)
    return gt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="/tmp/r7set")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    cases = build_cases()
    if a.only:
        cases = [c for c in cases if c["name"] in a.only.split(",")]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max(1, min(4, a.workers))) as ex:
        gts = list(ex.map(render_case, cases, [a.frames] * len(cases)))
    man = {"frames_dir": a.frames, "n_frames": N_FRAMES, "cases": [
        {**c, "camera": g["camera"], "doubles": g["doubles"]} for c, g in zip(cases, gts)]}
    if not a.only:
        json.dump(man, open(HERE / "manifest.json", "w"), indent=1, default=float)
    print(f"{len(cases)} cases → {a.frames}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
