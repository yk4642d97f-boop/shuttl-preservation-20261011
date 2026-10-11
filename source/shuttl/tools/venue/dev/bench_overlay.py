#!/usr/bin/env python3
"""dev/bench_overlay.py — where does the overlay render time go (1080p)?

Usage: ./bench_overlay.py <video> <analysis.json> [--frames 300]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_VENV = Path(__file__).resolve().parents[3] / "backend" / ".venv" / "bin" / "python"
if _VENV.exists() and Path(sys.executable).resolve() != _VENV.resolve():
    os.execv(str(_VENV), [str(_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

import argparse

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from venue_common import (iter_video_frames, load_json, video_props)  # noqa: E402
from overlay import Overlay  # noqa: E402


def bench(video: str, analysis: str, frames: int) -> None:
    props = video_props(video)
    fps = float(props["fps"])
    t0 = time.time()
    n = 0
    for _i, f in iter_video_frames(video, stop=frames):
        n += 1
    dt = time.time() - t0
    print(f"decode only      : {n / dt:6.1f} fps ({dt / max(n, 1) * 1000:.1f} ms/frame)")

    fr = list(iter_video_frames(video, stop=1))
    h, w = fr[0][1].shape[:2]
    ans = load_json(analysis)
    ov = Overlay(ans, (w, h), fps, title=os.path.basename(video), n_frames_hint=props["frames"])

    # write only (constant frame)
    frame = np.ascontiguousarray(fr[0][1])
    out = Path(video).with_name("_bench_write.mp4")
    wr = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
    cc = "avc1"
    t0 = time.time()
    for _ in range(frames):
        wr.write(frame)
    wr.release()
    dt = time.time() - t0
    print(f"encode only      : {frames / dt:6.1f} fps ({dt / frames * 1000:.1f} ms/frame, {cc})")
    out.unlink(missing_ok=True)

    # compose pieces separately
    for name, fn in (("court blend", lambda f, i: __import__('venue_common').blend_layer(f, ov.layer, ov.mask, 0.85)),
                     ("hud", lambda f, i: ov._hud(f, i)),
                     ("trail", lambda f, i: ov._trail(f, i)),
                     ("banner", lambda f, i: ov._banner(f, i))):
        t0 = time.time()
        for i, (idx, f) in enumerate(iter_video_frames(video, stop=frames)):
            fn(f, idx)
        dt = time.time() - t0
        print(f"{name:16s} : {frames / dt:6.1f} fps ({dt / frames * 1000:.1f} ms/frame)")

    t0 = time.time()
    for idx, f in iter_video_frames(video, stop=frames):
        ov.compose(f, idx)
    dt = time.time() - t0
    print(f"full compose     : {frames / dt:6.1f} fps ({dt / frames * 1000:.1f} ms/frame)")

    t0 = time.time()
    wr = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
    for idx, f in iter_video_frames(video, stop=frames):
        ov.compose(f, idx)
        wr.write(f)
    wr.release()
    dt = time.time() - t0
    print(f"compose+encode   : {frames / dt:6.1f} fps ({dt / frames * 1000:.1f} ms/frame)")
    out.unlink(missing_ok=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("analysis")
    ap.add_argument("--frames", type=int, default=300)
    a = ap.parse_args()
    bench(a.video, a.analysis, a.frames)
