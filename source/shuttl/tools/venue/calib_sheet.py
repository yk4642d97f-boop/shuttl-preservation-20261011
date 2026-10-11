#!/usr/bin/env python3
"""calib_sheet.py — 3×2 contact sheet of the reprojected court, to eyeball the calibration.

Usage:
  ./calib_sheet.py <video> [analysis.json] [-o out.jpg] [--tiles 6] [--no-lines] [-h]

Picks 6 frames spread over the video, draws the reprojected court lines on each
(green when confidence ≥ 0.7, orange below) with the reprojection RMSE and
confidence. Without a camera it writes "标定失败" plus the diagnostic reason.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# run under backend/.venv/bin/python even when started with the system python
_VENV = Path(__file__).resolve().parents[2] / "backend" / ".venv" / "bin" / "python"
if _VENV.exists() and Path(sys.executable).resolve() != _VENV.resolve():
    os.execv(str(_VENV), [str(_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

import argparse
import time

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venue_common import (CALIB_SUFFIX, MAC_SUFFIX, VenueError, add_backend,  # noqa: E402
                          calibration_reason, camera_info, court_polylines, load_json,
                          net_polylines, require_file, TextRenderer, video_props)

add_backend()
from app.services.tracking import video_io  # noqa: E402
from app.services.tracking.camera import CameraModel  # noqa: E402

TILE_W, TILE_H, CAP_H = 640, 360, 46


def find_analysis(video: Path, explicit: str | None) -> Path | None:
    if explicit:
        return require_file(explicit, "analysis JSON")
    for cand in (video.with_suffix(MAC_SUFFIX), video.parent / "mac_analysis.json",
                 video.with_suffix(".json")):
        if cand.is_file():
            return cand
    return None


def draw_court(frame: np.ndarray, cam: CameraModel, good: bool, scale: float) -> None:
    color = (0, 255, 0) if good else (0, 165, 255)
    thick = max(1, int(round(2 * scale)))
    for poly in court_polylines(cam):
        cv2.polylines(frame, [poly], False, color, thick + 1, cv2.LINE_AA)
    for poly in net_polylines(cam):
        cv2.polylines(frame, [poly], False, (255, 190, 90), thick, cv2.LINE_AA)


def build_sheet(video: Path, analysis_path: Path | None, out: Path, tiles: int = 6,
                draw_lines: bool = True) -> dict:
    props = video_props(video)
    n_total = int(props["frames"] or 0)
    if n_total <= 0:
        raise VenueError(f"video reports no frames: {video}")
    n_tiles = 6 if tiles == 6 else max(1, tiles)
    picked = video_io.sample_frames(str(video), n_tiles, n_total)
    if not picked:
        raise VenueError(f"could not read any frame from {video}")

    analysis = load_json(analysis_path) if analysis_path else {}
    cam_d = (analysis or {}).get("camera")
    cam = CameraModel.from_dict(cam_d) if cam_d else None
    info = camera_info(analysis) if analysis else {"found": False, "confidence": None, "rmse_px": None}
    reason = calibration_reason(analysis) if analysis else "没有分析 JSON（请先运行 analyze.py）"
    good = bool(info.get("found") and (info.get("confidence") or 0) >= 0.7)

    cols = 3
    rows = int(np.ceil(n_tiles / cols))
    sheet = np.full((rows * (TILE_H + CAP_H), cols * TILE_W, 3), 22, np.uint8)
    text = TextRenderer(base_px=22)

    for k, (idx, frame) in enumerate(picked[:n_tiles]):
        h, w = frame.shape[:2]
        if draw_lines and cam is not None:
            draw_court(frame, cam, good, h / 1080.0)
        tile = cv2.resize(frame, (TILE_W, TILE_H), interpolation=cv2.INTER_AREA)
        r, c = divmod(k, cols)
        y0, x0 = r * (TILE_H + CAP_H), c * TILE_W
        sheet[y0:y0 + TILE_H, x0:x0 + TILE_W] = tile
        if cam is not None:
            txt = (f"帧 {idx} · 重投影误差 {float(info['rmse_px'] or 0):.2f}px · "
                   f"置信 {float(info['confidence'] or 0):.2f}")
            col = (0, 255, 0) if good else (0, 165, 255)
        else:
            txt = f"帧 {idx} · {reason}"
            col = (0, 0, 255)
        cv2.rectangle(sheet, (x0, y0 + TILE_H), (x0 + TILE_W, y0 + TILE_H + CAP_H), (12, 12, 12), -1)
        text.draw(sheet, txt, (x0 + 8, y0 + TILE_H + 8), 22, col)
        cv2.rectangle(sheet, (x0, y0), (x0 + TILE_W - 1, y0 + TILE_H - 1), (60, 60, 60), 1)

    # header strip with the verdict
    head_h = 64
    header = np.full((head_h, sheet.shape[1], 3), 30, np.uint8)
    if cam is not None:
        head = (f"{video.name}   相机已标定   confidence={float(info['confidence'] or 0):.2f}   "
                f"reproj_rmse={float(info['rmse_px'] or 0):.2f}px   "
                f"{'绿色=置信≥0.7' if good else '橙色=置信<0.7'}")
        col = (0, 255, 0) if good else (0, 165, 255)
    else:
        head = f"{video.name}   标定失败   {reason}"
        col = (0, 0, 255)
    TextRenderer(base_px=30).draw(header, head, (14, 12), 30, col)
    sheet = np.vstack([header, sheet])

    out.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise VenueError(f"could not write {out}")
    return {"out": str(out), "tiles": len(picked[:n_tiles]), "camera": info,
            "reason": reason, "size": [sheet.shape[1], sheet.shape[0]],
            "analysis": str(analysis_path) if analysis_path else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="calib_sheet.py",
        description="3×2 contact sheet of the reprojected court (calibration eyeball check).",
        epilog="Default output: <video>_calib.jpg next to the video.")
    ap.add_argument("video", help="source video (.mov/.mp4)")
    ap.add_argument("analysis", nargs="?", default=None,
                    help="analysis JSON (default: <video>.mac_analysis.json, else mac_analysis.json)")
    ap.add_argument("-o", "--out", default=None, help="output JPEG")
    ap.add_argument("--tiles", type=int, default=6, help="number of frames (default 6)")
    ap.add_argument("--no-lines", action="store_true", help="frames only, no court lines")
    args = ap.parse_args(argv)

    video = require_file(args.video, "video")
    analysis_path = find_analysis(video, args.analysis)
    out = Path(args.out) if args.out else video.with_name(video.stem + CALIB_SUFFIX)
    t0 = time.time()
    try:
        res = build_sheet(video, analysis_path, out, args.tiles, draw_lines=not args.no_lines)
    except VenueError:
        raise
    except Exception as exc:                                            # noqa: BLE001
        raise VenueError(f"calib sheet failed: {type(exc).__name__}: {exc}") from exc
    cam = res["camera"]
    print(f"标定图: {res['out']}  ({res['size'][0]}x{res['size'][1]}, {res['tiles']} 帧, "
          f"{time.time() - t0:.1f}s)")
    print(f"  相机 {'有' if cam.get('found') else '无'}  confidence={cam.get('confidence')}  "
          f"rmse={cam.get('rmse_px')}")
    if not cam.get("found"):
        print(f"  原因: {res['reason']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VenueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
