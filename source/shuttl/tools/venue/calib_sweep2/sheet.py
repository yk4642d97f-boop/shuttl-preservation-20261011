#!/usr/bin/env python3
"""Contact sheet: the median frame of chosen sweep cases with the ESTIMATED camera's court
drawn on it (tools/venue/calib_sheet.draw_court: green = conf >= 0.7, orange below) and
the TRUE camera's court in thin magenta, to confirm by eye that the lines sit on the paint.

Usage: sheet.py -o sheet.jpg ITEM [ITEM ...]
  ITEM = sweep2:<id> | old:<case> | heldout:<case> | fb:<name>   (fb = still-player scenes)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_VENV = Path(__file__).resolve().parents[3] / "backend" / ".venv" / "bin" / "python"
if _VENV.exists() and Path(sys.executable).resolve() != _VENV.resolve():
    os.execv(str(_VENV), [str(_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

import argparse

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import cases  # noqa: E402
import calib_sheet  # noqa: E402  (draw_court, TextRenderer)
from venue_common import court_polylines  # noqa: E402

TW, TH, CAP = 640, 360, 40


def scene(item: str):
    """→ (label, true camera, frames)."""
    import calib_sweep as cs
    import scenes
    from tests import test_court_calibration as t
    kind, key = item.split(":", 1)
    if kind == "sweep2":
        c = {x["id"]: x for x in cases.build(cases.ALL_GRIDS)}[int(key)]
        cam = cases.make_camera(c["height_m"], c["dist_m"], c["lat_m"], c["roll_deg"], c["pitch_deg"], c["focal"])
        return (f"#{c['id']} {c['grid']}/{c['kind']} h{c['height_m']} d{c['dist_m']} lat{c['lat_m']} "
                f"r{c['roll_deg']} p{c['pitch_deg']}", cam, scenes.render(c, cam))
    if kind in ("old", "heldout"):
        c = {x["case"]: x for x in cs.build_cases(3, 5, False)}[int(key)]
        seed = c["seed"] + (5000 if kind == "heldout" else 0)
        cam = cs.make_camera(c["height_m"], c["dist_m"], c["lat_m"], c["roll_deg"])
        return (f"{kind} case {key} h{c['height_m']} d{c['dist_m']} lat{c['lat_m']} r{c['roll_deg']}", cam,
                t.render_frames(cam, np.random.default_rng(seed), n=c["frames"], style=c["style"]))
    if kind == "fb":
        cam = t._behind(1.6, 3.0)
        rng, rows = {"still_4_20": (4, range(4, 21)), "still_all": (7, range(24))}[key]
        return f"still player {key}", cam, t.still_player_frames(cam, np.random.default_rng(rng),
                                                                 "blue" if rng == 4 else "green", rows)
    raise SystemExit(f"unknown item {item}")


def tile(item: str, tr) -> np.ndarray:
    from app.services.tracking import court_calibration as cc
    label, true, frames = scene(item)
    d: dict = {}
    est = cc.calibrate_from_frames(frames, (cases.W, cases.H), diagnostics=d)
    img = cc._to_image(frames, (cases.W, cases.H)).copy()
    for poly in court_polylines(true):
        cv2.polylines(img, [poly], False, (255, 0, 255), 1, cv2.LINE_AA)
    cap = f"{label} | {d.get('reason')} ({d.get('source')})"
    if est is not None:
        calib_sheet.draw_court(img, est, est.confidence >= 0.7, 1.0)
        import calib_sweep as cs
        e = cs.errors(true, est)
        cap += f" | floor max {e['floor_max_m']:.3f} m, px max {e['px_max']:.2f}, conf {est.confidence:.2f}"
    out = np.zeros((TH + CAP, TW, 3), np.uint8)
    out[CAP:] = cv2.resize(img, (TW, TH), interpolation=cv2.INTER_AREA)
    tr.draw(out, cap, (6, 6), 13, (255, 255, 255))
    print(cap, flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("items", nargs="+")
    a = ap.parse_args()
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:        # already niced (e.g. /tmp/heavy.sh) → keep
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    tr = calib_sheet.TextRenderer()
    tiles = [tile(i, tr) for i in a.items]
    while len(tiles) % a.cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[k:k + a.cols]) for k in range(0, len(tiles), a.cols)]
    cv2.imwrite(a.out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
