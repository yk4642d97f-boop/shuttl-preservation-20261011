"""calib_sweep2 case grids (Task 9 §2). Deterministic: the same case list every run.

Grids (camera behind the near baseline, aimed at the court centre, iPhone 70° HFOV
f = 1371 px at 1920x1080 unless the case sets `focal`):
  old   the calib_sweep.py grid (360 cases, same seeds as tools/venue/calib_sweep.py)
  low   height 0.6–1.4 m step 0.1 × distance 0–1.5 m step 0.25 (63 cells); per cell
        LOW_PER_CELL cases sampled from lateral {0,1,2,3} × roll {0,2,5} × pitch {-3,0,3}
        × 5 scenes (full factorial would be 11 340 cases)
  rec   the recommended setup region: height 1.2–3.0 m step 0.2 × distance 3.5–7 m step
        0.5 (80 cells); per cell REC_PER_CELL cases from lateral {0,0.5,1,2} × roll
        {0,2,5} × pitch {-3,0,3} × 5 scenes
  hard  hard cases (scenes.py): occlusion, second court, wood + tape, motion blur,
        exposure changes, zoom (focal 1100–1700 px), HARD_PER_KIND each, drawn from the
        recommended region
  colour court lines painted yellow / light blue / red / orange (LINE_BGR) instead of white,
        COLOUR_PER_KIND each, same draw as hard (recommended region, all 3 floor styles);
        not in the default grid list (ids after hard: existing ids unchanged)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import calib_sweep as cs  # noqa: E402  (adds backend/ to sys.path)

W, H = cs.W, cs.H
FOCAL = cs.FOCAL
STYLES = ("green", "wood", "blue")
LOW_PER_CELL, REC_PER_CELL, HARD_PER_KIND = 12, 10, 40
HARD_KINDS = ("occlusion", "second_court", "wood_tape", "motion_blur", "exposure", "zoom")
# BGR, from deliverables/DELIVERY_R7 phonesim LINE_RGB (yellow, red, orange) + a light blue
LINE_BGR = {"yellow": (34, 196, 238), "light_blue": (235, 200, 120), "red": (40, 40, 196),
            "orange": (30, 120, 232)}
COLOUR_PER_KIND = 30


def make_camera(h: float, dist: float, lat: float = 0.0, roll: float = 0.0, pitch: float = 0.0,
                focal: float = FOCAL):
    """Eye `dist` behind the near baseline at height `h`, aimed at the court centre with an
    aim (pitch) error of `pitch` degrees (+ = aimed higher)."""
    from app.services.tracking import court_model as cm
    from app.services.tracking.camera import CameraModel
    eye = np.array([-cm.HALF_LENGTH - dist, lat, h])
    d = np.array([0.0, 0.0, 0.0]) - eye
    horiz = math.hypot(d[0], d[1])
    ang = math.atan2(d[2], horiz) + math.radians(pitch)
    tgt = eye + np.array([d[0], d[1], math.tan(ang) * horiz])
    return CameraModel.look_at(eye, tgt, focal, (W, H), roll_deg=roll)


def whole_court_in_frame(cam, margin: float = 0.03) -> bool:
    """4 outer corners, a point 0.5 m behind each baseline (centre) and the far player's
    head (1.9 m, far baseline centre) all inside the image with a `margin` border."""
    from app.services.tracking import court_model as cm
    L, Wd = cm.HALF_LENGTH, cm.DOUBLES_HALF_WIDTH
    far = 1.0 if cam.center[0] < 0 else -1.0
    P = np.array([[-L, -Wd, 0], [-L, Wd, 0], [L, -Wd, 0], [L, Wd, 0],
                  [-L - 0.5, 0, 0], [L + 0.5, 0, 0], [far * L, 0, 1.9]], float)
    uv = cam.project(P)
    mx, my = margin * W, margin * H
    return bool(np.all(np.isfinite(uv)) and np.all((uv[:, 0] >= mx) & (uv[:, 0] <= W - mx)
                                                   & (uv[:, 1] >= my) & (uv[:, 1] <= H - my)))


def _sampled(grid: str, cell: int, heights_dists, laterals, per_cell: int, rng_seed: int) -> list[dict]:
    out = []
    combos = [(la, ro, pi, sc) for la in laterals for ro in (0.0, 2.0, 5.0) for pi in (-3.0, 0.0, 3.0)
              for sc in range(5)]
    h, d = heights_dists
    pick = np.random.default_rng(rng_seed + cell).choice(len(combos), per_cell, replace=False)
    for k in sorted(pick):
        la, ro, pi, sc = combos[k]
        out.append({"grid": grid, "height_m": h, "dist_m": d, "lat_m": la, "roll_deg": ro, "pitch_deg": pi,
                    "scene": sc, "seed": rng_seed * 1000 + cell * 100 + int(k), "style": STYLES[(cell + sc) % 3],
                    "focal": FOCAL, "kind": "plain"})
    return out


ALL_GRIDS = ("old", "low", "rec", "hard", "colour")


def build(grids: tuple[str, ...] = ("old", "low", "rec", "hard")) -> list[dict]:
    """Cases of `grids`; ids are positions in the list of ALL grids (stable whatever subset)."""
    want = set(grids)
    grids = ALL_GRIDS
    cases: list[dict] = []
    if "old" in grids:
        for c in cs.build_cases(3, 5, False):
            cases.append({"grid": "old", "height_m": c["height_m"], "dist_m": c["dist_m"], "lat_m": c["lat_m"],
                          "roll_deg": c["roll_deg"], "pitch_deg": 0.0, "scene": c["scene"], "seed": c["seed"],
                          "style": c["style"], "focal": FOCAL, "kind": "plain", "old_case": c["case"]})
    if "low" in grids:
        hd = [(round(0.6 + 0.1 * i, 1), 0.25 * j) for i in range(9) for j in range(7)]
        for cell, x in enumerate(hd):
            cases += _sampled("low", cell, x, (0.0, 1.0, 2.0, 3.0), LOW_PER_CELL, 71)
    if "rec" in grids:
        hd = [(round(1.2 + 0.2 * i, 1), 3.5 + 0.5 * j) for i in range(10) for j in range(8)]
        for cell, x in enumerate(hd):
            cases += _sampled("rec", cell, x, (0.0, 0.5, 1.0, 2.0), REC_PER_CELL, 83)
    if "hard" in grids:
        rng = np.random.default_rng(97)
        for kind in HARD_KINDS:
            for k in range(HARD_PER_KIND):
                cases.append({"grid": "hard", "kind": kind,
                              "height_m": float(rng.choice([1.2, 1.6, 2.0, 2.5, 3.0])),
                              "dist_m": float(rng.choice([3.5, 4.5, 5.0, 6.0, 7.0])),
                              "lat_m": float(rng.choice([0.0, 0.5, 1.0, 2.0])),
                              "roll_deg": float(rng.choice([0.0, 2.0, 5.0])),
                              "pitch_deg": float(rng.choice([-3.0, 0.0, 3.0])), "scene": k,
                              "seed": 97_000_000 + HARD_KINDS.index(kind) * 1000 + k,
                              "style": "wood" if kind == "wood_tape" else STYLES[k % 3],
                              "focal": float(rng.uniform(1100, 1700)) if kind == "zoom" else FOCAL})
    if "colour" in grids:
        rng = np.random.default_rng(101)
        for kind in LINE_BGR:
            for k in range(COLOUR_PER_KIND):
                cases.append({"grid": "colour", "kind": "colour_lines", "line": kind,
                              "line_bgr": LINE_BGR[kind],
                              "height_m": float(rng.choice([1.2, 1.6, 2.0, 2.5, 3.0])),
                              "dist_m": float(rng.choice([3.5, 4.5, 5.0, 6.0, 7.0])),
                              "lat_m": float(rng.choice([0.0, 0.5, 1.0, 2.0])),
                              "roll_deg": float(rng.choice([0.0, 2.0, 5.0])),
                              "pitch_deg": float(rng.choice([-3.0, 0.0, 3.0])), "scene": k,
                              "seed": 101_000_000 + list(LINE_BGR).index(kind) * 1000 + k,
                              "style": STYLES[k % 3], "focal": FOCAL})
    for i, c in enumerate(cases):
        c["id"] = i
    return [c for c in cases if c["grid"] in want]


if __name__ == "__main__":
    from collections import Counter
    cs_ = build()
    print(len(cs_), Counter(c["grid"] for c in cs_), Counter(c["kind"] for c in cs_ if c["grid"] == "hard"))
    cams = [make_camera(c["height_m"], c["dist_m"], c["lat_m"], c["roll_deg"], c["pitch_deg"], c["focal"])
            for c in cs_]
    for g in ("old", "low", "rec", "hard"):
        sel = [whole_court_in_frame(k) for k, c in zip(cams, cs_) if c["grid"] == g]
        print(g, f"whole court in frame {sum(sel)}/{len(sel)}")