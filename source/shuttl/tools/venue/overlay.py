#!/usr/bin/env python3
"""overlay.py — render a diagnostic overlay video (analysis drawn on the footage).

Usage:
  ./overlay.py <video> <analysis.json> [-o out.mp4] [--max-seconds N] [--no-intro] [-h]

Draws: reprojected court lines (green conf ≥ 0.7, else orange), the shuttle 2-D
trail (0.5 s fade), hit rings for 8 frames with near/far + shot type, player boxes
when the analysis has them, a HUD (frame/time/rally/状态/last shot speed/score) and
a 1 s rally-end banner. Streams frames, never holds the video in memory.
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
from venue_common import (OVERLAY_SUFFIX, VenueError, blend_layer, camera_info,  # noqa: E402
                          hits_from_analysis, iter_video_frames, load_json, open_writer,
                          rally_rows, require_file, static_court_layer, TextRenderer,
                          track_arrays, verify_video, video_props)

from app.services.tracking.camera import CameraModel  # noqa: E402

REASON_ZH = {"in": "落点界内", "out": "出界", "net": "下网", "unknown": "判定不明"}
WINNER_ZH = {"near": "近端得分", "far": "远端得分", "unknown": "得分未知"}
HITTER_ZH = {"near": "近端", "far": "远端", "unknown": "未知"}
COLOR_NEAR = (0, 235, 255)      # BGR yellow
COLOR_FAR = (255, 0, 235)       # BGR magenta
COLOR_UNK = (235, 235, 235)


def player_boxes(ans: dict) -> dict[int, list[dict]]:
    """Optional per-frame player boxes: {'players': [{frame, bbox, side, foot_world}]}."""
    for key in ("players", "observations", "player_observations", "player_tracks"):
        seq = ans.get(key)
        if not isinstance(seq, list) or not seq:
            continue
        boxes: dict[int, list[dict]] = {}
        for item in seq:
            if not isinstance(item, dict):
                continue
            f = item.get("frame")
            bb = item.get("bbox")
            if f is None or bb is None or len(bb) != 4:
                continue
            bb = [float(v) for v in bb]
            if max(bb) <= 1.5:                      # normalised boxes
                w = float((ans.get("video") or {}).get("width") or 1)
                h = float((ans.get("video") or {}).get("height") or 1)
                bb = [bb[0] * w, bb[1] * h, bb[2] * w, bb[3] * h]
            boxes.setdefault(int(f), []).append(
                {"bbox": bb, "side": item.get("side") or "unknown",
                 "foot_world": item.get("foot_world"), "score": item.get("score")})
        if boxes:
            return boxes
    return {}


class Overlay:
    def __init__(self, analysis: dict, size: tuple[int, int], fps: float, title: str = "",
                 n_frames_hint: int | None = None):
        self.analysis = analysis
        self.w, self.h = int(size[0]), int(size[1])
        self.fps = float(fps or 30.0)
        self.scale = self.h / 1080.0
        self.px = int(round(34 * self.scale))
        self.px_small = int(round(26 * self.scale))
        self.px_big = int(round(46 * self.scale))
        self.text = TextRenderer(base_px=self.px)
        cam_d = analysis.get("camera")
        self.cam = CameraModel.from_dict(cam_d) if cam_d else None
        info = camera_info(analysis)
        self.conf = float(info.get("confidence") or 0.0)
        self.good = self.conf >= 0.7
        if self.cam is not None:
            self.layer, self.mask = static_court_layer(
                (self.h, self.w, 3), self.cam, self.good, self.h / 1080.0)
        else:
            self.layer = self.mask = None
        self.xy, self.known, self.det = track_arrays(analysis)
        n_track = len(self.known)
        self.n_frames = max(int((analysis.get("video") or {}).get("frames") or 0), n_track,
                            int(n_frames_hint or 0))
        self.hits = hits_from_analysis(analysis)
        self.rallies = rally_rows(analysis)
        self.score = analysis.get("score") or []
        self.starts = np.array([r["start"] for r in self.rallies], dtype=np.int64)
        self.players = player_boxes(analysis)
        self.title = title
        self.intro_frames = int(round(2.0 * self.fps))
        self.geom_debug = False
        self.hit_by_frame: dict[int, dict] = {}
        for i, h in enumerate(self.hits):
            self.hit_by_frame.setdefault(int(h["frame"]), []).append(h)
        # frames → rally-end banner / rally-start marker (small windows, dict lookup per frame)
        self.banner: dict[int, dict] = {}
        self.start_mark: dict[int, int] = {}
        span = int(round(1.0 * self.fps))
        for k, r in enumerate(self.rallies):
            if r.get("end") is not None:
                for f in range(int(r["end"]), int(r["end"]) + span):
                    self.banner[f] = r
            if r.get("start") is not None:
                for f in (int(r["start"]), int(r["start"]) + 1):
                    self.start_mark[f] = k
        self.ends = np.array([int(r["end"]) if r.get("end") is not None else -1
                              for r in self.rallies], dtype=np.int64)

    # ---------------------------------------------------------------- pieces
    def _trail(self, frame: np.ndarray, i: int) -> None:
        win = max(2, int(round(0.5 * self.fps)))
        lo = max(0, i - win + 1)
        pts = [(k, self.xy[k]) for k in range(lo, min(i + 1, len(self.known))) if self.known[k]]
        if len(pts) >= 2:
            for a in range(len(pts) - 1):
                frac = (a + 1) / len(pts)
                p1 = tuple(np.round(pts[a][1]).astype(int))
                p2 = tuple(np.round(pts[a + 1][1]).astype(int))
                col = (0, int(200 * frac + 55), int(255 * frac))
                th = max(1, int(round((1 + 3.5 * frac) * self.scale)))
                cv2.line(frame, p1, p2, col, th, cv2.LINE_AA)
        if i < len(self.known) and self.known[i]:
            c = tuple(np.round(self.xy[i]).astype(int))
            r = max(2, int(round(5 * self.scale)))
            cv2.circle(frame, c, r, (255, 255, 255), max(1, int(2 * self.scale)), cv2.LINE_AA)
            cv2.circle(frame, c, r + max(2, int(3 * self.scale)), (0, 0, 255),
                       max(1, int(1 * self.scale)), cv2.LINE_AA)
            if self.geom_debug and not self.det[i]:
                cv2.drawMarker(frame, c, (160, 160, 160), cv2.MARKER_TILTED_CROSS,
                               max(4, int(9 * self.scale)), max(1, int(2 * self.scale)))

    def _hits(self, frame: np.ndarray, i: int) -> None:
        for h in self.hits:
            df = i - int(h["frame"])
            if not (0 <= df < 8):
                continue
            xyn = h.get("xy_norm")
            xy = (int(round(float(xyn[0]) * self.w)), int(round(float(xyn[1]) * self.h))) \
                if xyn else None
            if xy is None:
                continue
            col = COLOR_NEAR if h["hitter"] == "near" else \
                (COLOR_FAR if h["hitter"] == "far" else COLOR_UNK)
            rad = int(round((26 - 2.6 * df) * self.scale))
            cv2.circle(frame, xy, max(4, rad), col, max(2, int(3 * self.scale)), cv2.LINE_AA)
            cv2.circle(frame, xy, max(2, rad // 3), col, -1, cv2.LINE_AA)
            label = f"{h['hitter']} {h['shot_type']}"
            if h.get("speed_kmh") is not None:
                label += f" {float(h['speed_kmh']):.0f}km/h"
            tw, th = self.text.size(label, self.px_small)
            tx = min(max(0, xy[0] + rad + 6), self.w - tw - 2)
            ty = min(max(0, xy[1] - th // 2), self.h - th - 2)
            self.text.draw_panel(frame, [label], (tx - 6, ty - 4), self.px_small,
                                 pad=6, color=col, alpha=0.6)

    def _players(self, frame: np.ndarray, i: int) -> None:
        for p in self.players.get(i, []):
            x1, y1, x2, y2 = [int(round(v)) for v in p["bbox"]]
            col = (255, 200, 0) if p["side"] == "near" else (0, 200, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, max(1, int(2 * self.scale)),
                          cv2.LINE_AA)
            fx, fy = (x1 + x2) // 2, y2
            if p.get("foot_world") is not None and self.cam is not None:
                uv = self.cam.project(np.array([[float(p["foot_world"][0]),
                                                 float(p["foot_world"][1]), 0.0]]))
                if np.all(np.isfinite(uv)):
                    fx, fy = int(round(uv[0, 0])), int(round(uv[0, 1]))
            cv2.drawMarker(frame, (fx, fy), col, cv2.MARKER_CROSS,
                           max(6, int(16 * self.scale)), max(1, int(2 * self.scale)))

    def _rally_index(self, i: int) -> int:
        if len(self.starts) == 0:
            return -1
        j = int(np.searchsorted(self.starts, i, side="right")) - 1
        if j < 0:
            return -1
        if i <= int(self.rallies[j]["end"] or self.rallies[j]["start"]):
            return j
        return -1

    def _score_at(self, i: int) -> str:
        if not self.score or len(self.starts) == 0:
            return "近 0 : 0 远" if self.score else ""
        j = int(np.searchsorted(self.starts, i, side="right")) - 1
        if j < 0:
            idx = -1
        elif self.ends[j] >= 0 and i <= int(self.ends[j]):
            idx = j - 1
        else:
            idx = j
        if idx < 0:
            return "近 0 : 0 远"
        s = self.score[idx] or {}
        sc = s.get("score") or {}
        if "near" not in sc:
            return ""
        return f"近 {sc.get('near')} : {sc.get('far')} 远"

    def _last_speed(self, i: int) -> float | None:
        best = None
        for h in self.hits:
            if int(h["frame"]) <= i and h.get("speed_kmh") is not None:
                best = float(h["speed_kmh"])
            if int(h["frame"]) > i:
                break
        return best

    def _hud(self, frame: np.ndarray, i: int) -> None:
        t = i / self.fps if self.fps else 0.0
        ri = self._rally_index(i)
        in_rally = ri >= 0
        lines = [f"帧 {i}/{self.n_frames}   时间 {t:.1f}s"]
        status = "比赛中" if in_rally else "死球"
        lines.append(f"回合 {ri + 1 if in_rally else '-'} · {status}")
        spd = self._last_speed(i)
        sc = self._score_at(i)
        bits = []
        if spd is not None:
            bits.append(f"最近球速 {spd:.0f} km/h")
        if sc:
            bits.append(sc)
        if bits:
            lines.append(" · ".join(bits))
        if self.cam is None:
            lines.append("相机未标定：无法给出球速/落点")
        self.text.draw_panel(frame, lines, (int(12 * self.scale), int(12 * self.scale)),
                             self.px, alpha=0.55)
        if self.cam is None:
            tw, _th = self.text.size("NO CAMERA", self.px_big)
            self.text.draw(frame, "NO CAMERA",
                           (self.w - tw - int(16 * self.scale), int(16 * self.scale)),
                           self.px_big, (0, 0, 255))
        elif not self.good:
            msg = f"calib conf {self.conf:.2f} (<0.7)"
            tw, _th = self.text.size(msg, self.px_small)
            self.text.draw(frame, msg,
                           (self.w - tw - int(16 * self.scale), int(20 * self.scale)),
                           self.px_small, (0, 165, 255))

    def _banner(self, frame: np.ndarray, i: int) -> None:
        r = self.banner.get(i)
        if r is not None:
            reason = REASON_ZH.get(r["end_reason"], r["end_reason"])
            winner = WINNER_ZH.get(r["winner"], r["winner"])
            conf = r.get("outcome_confidence")
            txt = f"回合结束 · {reason} · {winner}"
            if conf is not None:
                txt += f" · 置信 {float(conf):.2f}"
            tw, th = self.text.size(txt, self.px_big)
            self.text.draw_panel(frame, [txt], ((self.w - tw) // 2, self.h - th - int(40 * self.scale)),
                                 self.px_big, pad=int(14 * self.scale), alpha=0.7)
        k = self.start_mark.get(i)
        if k is not None:
            txt = f"回合 {k + 1} 开始"
            tw, th = self.text.size(txt, self.px_small)
            self.text.draw_panel(frame, [txt], ((self.w - tw) // 2, int(20 * self.scale)),
                                 self.px_small, pad=8, color=(120, 255, 120), alpha=0.6)

    def _intro(self, frame: np.ndarray, i: int) -> None:
        if i >= self.intro_frames:
            return
        n_hits = len(self.hits)
        cam_txt = f"相机：已标定 · 置信度 {self.conf:.2f}" if self.cam else "相机：未标定（无球速/落点）"
        lines = [self.title, cam_txt,
                 f"回合 {len(self.rallies)} 个 · 击球 {n_hits} 次",
                 "绿线=标定成功(置信≥0.7)  橙线=置信偏低",
                 "黄圈=近端击球  洋红圈=远端击球  白点=羽毛球轨迹"]
        px = int(round(40 * self.scale))
        sizes = [self.text.size(ln, px) for ln in lines]
        w = max(s[0] for s in sizes) + int(40 * self.scale)
        h = int(px * 1.5) * len(lines) + int(30 * self.scale)
        x = (self.w - w) // 2
        y = (self.h - h) // 2
        from venue_common import dark_box
        dark_box(frame, x, y, w, h, 0.65)
        for k, ln in enumerate(lines):
            self.text.draw(frame, ln, (x + int(20 * self.scale), y + int(15 * self.scale) + k * int(px * 1.5)),
                           px)

    # ---------------------------------------------------------------- main compose

    def compose(self, frame: np.ndarray, i: int) -> None:
        if self.mask is not None:
            blend_layer(frame, self.layer, self.mask, 0.85)
        self._trail(frame, i)
        self._hits(frame, i)
        self._players(frame, i)
        self._hud(frame, i)
        self._banner(frame, i)
        self._intro(frame, i)


def build_overlay(video: Path, analysis_path: Path, out: Path, max_seconds: float | None,
                  intro: bool = True, quiet: bool = False, writer: str = "auto") -> dict:
    analysis = load_json(analysis_path)
    props = video_props(video)
    fps = float(props["fps"] or 30.0)
    stop = int(round(max_seconds * fps)) if max_seconds else None
    declared = int(props.get("frames") or 0)
    cap = declared if declared > 0 else None
    if cap is not None and stop is not None:
        stop = min(stop, cap)
    gen = iter_video_frames(video, stop=stop, max_frames=cap)
    try:
        first_i, first = next(gen)
    except StopIteration as exc:
        raise VenueError(f"video has no readable frames: {video}") from exc
    h, w = first.shape[:2]
    ov = Overlay(analysis, (w, h), fps, title=video.name, n_frames_hint=props.get("frames"))
    if not intro:
        ov.intro_frames = 0

    def _render(prefer_avf: bool) -> tuple[int, str, float]:
        writer_obj, cc = open_writer(out, fps, (w, h), prefer_avf=prefer_avf)
        n = 0
        t0 = time.time()
        frames = iter_video_frames(video, stop=stop, max_frames=cap)
        try:
            for i, frame in frames:
                if frame.shape[0] != h or frame.shape[1] != w:
                    frame = cv2.resize(frame, (w, h))
                ov.compose(frame, i)
                writer_obj.write(frame)
                n += 1
                if not quiet and n % 60 == 0:
                    el = time.time() - t0
                    sys.stdout.write(f"\r  渲染 {n} 帧 ({n / el:.1f} fps) ")
                    sys.stdout.flush()
        finally:
            writer_obj.release()
        return n, cc, time.time() - t0

    n, cc, dt = _render(prefer_avf=(writer in ("auto", "avf")))
    if writer == "auto" and cc.startswith("avf") and not verify_video(out):
        print("  提示：AVFoundation 写出的文件无法读取，改用 FFmpeg 重渲染…")
        n, cc, dt = _render(prefer_avf=False)
    if not quiet:
        sys.stdout.write("\n")
    return {"out": str(out), "frames": n, "seconds": round(dt, 1),
            "render_fps": round(n / dt, 1) if dt > 0 else None, "codec": cc,
            "size_bytes": out.stat().st_size if out.exists() else 0,
            "camera": camera_info(analysis), "hits": len(ov.hits), "rallies": len(ov.rallies)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="overlay.py",
        description="Render a diagnostic overlay video from a Shuttl analysis JSON.",
        epilog="Default output: <video>_overlay.mp4 next to the video.")
    ap.add_argument("video", help="source video (.mov/.mp4)")
    ap.add_argument("analysis", help="analysis JSON (phone or mac_analysis)")
    ap.add_argument("-o", "--out", help="output mp4 (default <video>_overlay.mp4)")
    ap.add_argument("--max-seconds", type=float, default=None,
                    help="render only the first N seconds")
    ap.add_argument("--no-intro", action="store_true", help="skip the 2 s Chinese title card")
    ap.add_argument("--quiet", action="store_true", help="no progress output")
    ap.add_argument("--writer", choices=("auto", "avf", "ffmpeg"), default="auto",
                    help="video encoder: auto (AVFoundation when available), avf, ffmpeg")
    args = ap.parse_args(argv)

    video = require_file(args.video, "video")
    analysis = require_file(args.analysis, "analysis JSON")
    out = Path(args.out) if args.out else video.with_name(video.stem + OVERLAY_SUFFIX)
    try:
        res = build_overlay(video, analysis, out, args.max_seconds,
                            intro=not args.no_intro, quiet=args.quiet, writer=args.writer)
    except VenueError:
        raise
    except Exception as exc:                                            # noqa: BLE001
        raise VenueError(f"overlay failed: {type(exc).__name__}: {exc}") from exc
    cam = res["camera"]
    print(f"叠加视频: {res['out']}")
    print(f"  帧 {res['frames']}  渲染 {res['seconds']}s ({res['render_fps']} fps)  "
          f"编码 {res['codec']}  {res['size_bytes'] / 1e6:.1f}MB")
    print(f"  相机 {'有' if cam['found'] else '无'} (conf {cam['confidence']})  "
          f"击球 {res['hits']}  回合 {res['rallies']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VenueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
