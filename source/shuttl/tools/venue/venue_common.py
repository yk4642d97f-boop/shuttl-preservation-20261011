"""Shared helpers for the Shuttl venue-day toolkit (tools/venue/).

Only reads backend/ code; every output of the toolkit goes under tools/venue/.

Public helper groups
  io       load_json / save_json / video_props / sha of a small file
  analysis hits_from_analysis / track_arrays / rally_rows / visible_fraction
           compare_analyses (phone vs mac)
  drawing  court_polylines / net_polylines / static_court_layer / dark_box
           TextRenderer (Chinese-capable, cached, PIL based)
  misc     ensure_venv (re-exec the backend venv) / fmt_dur / calibration_reason
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                     # tools/venue -> tools -> repo root
BACKEND = REPO / "backend"
VENV_PY = BACKEND / ".venv" / "bin" / "python"
DATA_DIR = HERE / "data"

PHONE_DEVICE = "0F92DDA9-7A87-4F05-8368-0E834177D8F3"
BUNDLE_ID = "com.ycyangcong.shuttl"

MAC_SUFFIX = ".mac_analysis.json"
COMPARE_SUFFIX = ".compare.json"
CALIB_SUFFIX = "_calib.jpg"
OVERLAY_SUFFIX = "_overlay.mp4"

FONT_CANDIDATES = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)


# --------------------------------------------------------------------------- bootstrap

def ensure_venv(script: str | Path) -> None:
    """Re-exec under backend/.venv/bin/python when started with another interpreter."""
    script = Path(script).resolve()
    try:
        same = Path(sys.executable).resolve() == VENV_PY.resolve()
    except OSError:
        same = False
    if not same and VENV_PY.exists():
        os.execv(str(VENV_PY), [str(VENV_PY), str(script), *sys.argv[1:]])


def add_backend() -> None:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))


add_backend()

import cv2  # noqa: E402
from app.services.tracking import court_model as cm  # noqa: E402
from app.services.tracking.camera import CameraModel  # noqa: E402


# --------------------------------------------------------------------------- io

def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _plain(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return _plain(x.tolist())
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if not math.isfinite(v) else round(v, 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def save_json(path: str | Path, obj: Any, indent: int = 1) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_plain(obj), fh, ensure_ascii=False, indent=indent)
    tmp.replace(p)


def open_capture(path: str | Path, start: int = 0, prefer_avfoundation: bool = True):
    """cv2.VideoCapture preferring macOS AVFoundation (fast HEVC), with fallback.

    iPhone recordings are HEVC: AVFoundation (VideoToolbox) decodes ~2-3x faster
    than the bundled FFmpeg here. AVFoundation cannot open every container, so a
    probe frame decides, and the FFmpeg/default backend is the fallback.
    """
    path = str(path)
    caps = []
    if prefer_avfoundation and sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
        caps.append(cv2.VideoCapture(path, cv2.CAP_AVFOUNDATION))
    caps.append(cv2.VideoCapture(path))
    chosen = None
    for cap in caps:
        if not cap.isOpened():
            cap.release()
            continue
        if chosen is None:
            chosen = cap                     # first backend that opens at all
        if start:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        ok, frame = cap.read()
        if ok and frame is not None and frame.size:
            if start:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            return cap
        cap.release()
    if chosen is not None:
        if start:
            chosen.set(cv2.CAP_PROP_POS_FRAMES, start)
        return chosen
    cap = cv2.VideoCapture(path)
    return cap


def video_props(path: str | Path) -> dict:
    """Fast container properties (no full decode): fps / frames / size / duration."""
    cap = open_capture(path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()
    return {"fps": round(fps, 4), "frames": n, "width": w, "height": h,
            "duration": round(n / fps, 3) if fps > 0 else 0.0}


def fmt_dur(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return "0s"
    m, s = divmod(float(seconds), 60.0)
    if m >= 1:
        return f"{int(m)}分{s:04.1f}秒"
    return f"{s:.1f}秒"


def run(cmd: Sequence[str], timeout: float | None = None) -> tuple[int, str]:
    """Run a command, return (returncode, combined output)."""
    try:
        p = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "")
        return 124, f"TIMEOUT after {timeout}s\n{out}"
    except FileNotFoundError as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# --------------------------------------------------------------------------- analysis helpers

def analysis_meta(ans: dict) -> dict:
    v = (ans or {}).get("video") or {}
    return {"fps": v.get("fps"), "width": v.get("width"), "height": v.get("height"),
            "frames": v.get("frames")}


def hits_from_analysis(ans: dict) -> list[dict]:
    """Every hit (shot contact) with its frame, hitter, type and 3-D speed if any."""
    out: list[dict] = []
    for ri, r in enumerate(ans.get("rallies") or []):
        for s in r.get("shots") or []:
            f = s.get("frame")
            if f is None:
                continue
            seg = s.get("flight") or {}
            out.append({"rally": ri, "frame": int(f), "t": s.get("t"),
                        "hitter": s.get("hitter") or "unknown",
                        "shot_type": s.get("shot_type") or "unknown",
                        "speed_kmh": seg.get("speed0_kmh"),
                        "xy_norm": s.get("xy_norm"),
                        "confidence": s.get("hit_confidence")})
    out.sort(key=lambda h: h["frame"])
    return out


def rally_rows(ans: dict) -> list[dict]:
    rows = []
    for i, r in enumerate(ans.get("rallies") or []):
        shots = r.get("shots") or []
        speeds = [s["flight"]["speed0_kmh"] for s in shots
                  if (s.get("flight") or {}).get("speed0_kmh") is not None]
        rows.append({
            "index": i + 1, "start": r.get("start_frame"), "end": r.get("end_frame"),
            "shots": len(shots), "end_reason": r.get("end_reason") or "unknown",
            "winner": r.get("winner") or "unknown", "server": r.get("server") or "unknown",
            "confidence": r.get("confidence"), "outcome_confidence": r.get("outcome_confidence"),
            "outcome_source": r.get("outcome_source"),
            "max_speed_kmh": max(speeds) if speeds else None,
            "landing_xy": r.get("landing_xy"), "in_out_margin_m": r.get("in_out_margin_m"),
        })
    return rows


def track_arrays(ans: dict, n_frames: int | None = None
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(xy (N,2) in PIXELS with NaN where unknown, known bool, detected bool).

    serialize.to_dict stores the track normalised to 0–1 of the frame; tracks read
    from a native analysis dict are already in pixels. Both are accepted.
    """
    n = int((ans.get("video") or {}).get("frames") or 0) if n_frames is None else int(n_frames)
    runs = ans.get("track") or []
    for run in runs:
        n = max(n, int(run.get("start_frame", 0)) + len(run.get("xy") or []))
    n = max(n, 1)
    xy = np.full((n, 2), np.nan, dtype=np.float64)
    known = np.zeros(n, dtype=bool)
    det = np.zeros(n, dtype=bool)
    for run in runs:
        s = int(run.get("start_frame", 0))
        arr = np.asarray(run.get("xy") or [], dtype=np.float64)
        if arr.ndim != 2 or len(arr) == 0:
            continue
        e = min(n, s + len(arr))
        if e <= s:
            continue
        xy[s:e] = arr[:e - s]
        known[s:e] = True
        interp = {int(k) for k in (run.get("interp") or [])}
        for k in range(s, e):
            if (k - s) not in interp:
                det[k] = True
    v = ans.get("video") or {}
    w, h = float(v.get("width") or 0), float(v.get("height") or 0)
    fin = np.isfinite(xy).all(axis=1)
    if fin.any() and w > 0 and h > 0 and np.nanmax(np.abs(xy[fin])) <= 1.5:
        xy[fin] *= (w, h)                    # normalised 0–1 → pixels
    return xy, known, det


def visible_fraction(ans: dict) -> dict:
    xy, known, det = track_arrays(ans)
    n = len(known)
    n_frames = int((ans.get("video") or {}).get("frames") or n)
    tot = max(n_frames, n)
    return {"frames": tot,
            "known_frames": int(known.sum()),
            "detected_frames": int(det.sum()),
            "known_frac": round(float(known.sum()) / tot, 4),
            "detected_frac": round(float(det.sum()) / tot, 4)}


def top_speed_kmh(ans: dict) -> float | None:
    vals = []
    s = (ans.get("summary") or {}).get("max_speed_kmh")
    if s is not None:
        vals.append(float(s))
    for r in ans.get("rallies") or []:
        for sh in r.get("shots") or []:
            v = (sh.get("flight") or {}).get("speed0_kmh")
            if v is not None:
                vals.append(float(v))
    return round(max(vals), 1) if vals else None


def stage_seconds(diag: dict | None) -> dict:
    out = {}
    for name, st in ((diag or {}).get("stages") or {}).items():
        if isinstance(st, dict):
            out[name] = {"ok": bool(st.get("ok", True)),
                         "seconds": round(float(st.get("seconds") or 0.0), 2)}
            if st.get("error"):
                out[name]["error"] = str(st["error"])[:200]
    return out


def camera_info(ans: dict) -> dict:
    cam = (ans or {}).get("camera")
    return {"found": cam is not None, "calibrated": bool((ans or {}).get("calibrated")),
            "confidence": (cam or {}).get("confidence"),
            "rmse_px": (cam or {}).get("reproj_rmse_px")}


_IOU_EPS = 1e-9


def _iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    inter = max(0.0, hi - lo)
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > _IOU_EPS else 0.0


def _greedy_pairs(scored: list[tuple[float, int, int]], min_score: float
                  ) -> list[tuple[int, int, float]]:
    """scored = (score, i, j) — take the best pairs without reusing an index."""
    used_i: set[int] = set()
    used_j: set[int] = set()
    out = []
    for score, i, j in sorted(scored, key=lambda x: -x[0]):
        if score < min_score or i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        out.append((i, j, score))
    return out


def match_hits(phone_hits: list[dict], mac_hits: list[dict], tol: int = 3) -> dict:
    scored = []
    for i, ph in enumerate(phone_hits):
        for j, mh in enumerate(mac_hits):
            df = abs(int(ph["frame"]) - int(mh["frame"]))
            if df <= tol:
                scored.append((float(df), i, j))
    pairs = _greedy_pairs(scored, 0.0)
    pairs.sort(key=lambda p: phone_hits[p[0]]["frame"])
    return {
        "phone": len(phone_hits), "mac": len(mac_hits), "matched": len(pairs),
        "only_phone": len(phone_hits) - len(pairs), "only_mac": len(mac_hits) - len(pairs),
        "tol_frames": tol,
        "pairs": [{"phone_frame": int(phone_hits[i]["frame"]),
                   "mac_frame": int(mac_hits[j]["frame"]),
                   "df": int(mac_hits[j]["frame"]) - int(phone_hits[i]["frame"]),
                   "phone_type": phone_hits[i]["shot_type"], "mac_type": mac_hits[j]["shot_type"],
                   "phone_speed": phone_hits[i]["speed_kmh"], "mac_speed": mac_hits[j]["speed_kmh"]}
                  for i, j, _ in pairs],
        "only_phone_frames": [int(h["frame"]) for k, h in enumerate(phone_hits)
                              if k not in {i for i, _, _ in pairs}],
        "only_mac_frames": [int(h["frame"]) for k, h in enumerate(mac_hits)
                            if k not in {j for _, j, _ in pairs}],
    }


def match_rallies(phone_r: list[dict], mac_r: list[dict], iou_thr: float = 0.5) -> dict:
    scored = []
    for i, a in enumerate(phone_r):
        for j, b in enumerate(mac_r):
            v = _iou((float(a.get("start") or 0), float(a.get("end") or 0)),
                     (float(b.get("start") or 0), float(b.get("end") or 0)))
            if v >= iou_thr:
                scored.append((v, i, j))
    pairs = _greedy_pairs(scored, iou_thr)
    pairs.sort(key=lambda p: phone_r[p[0]].get("start") or 0)
    return {
        "phone": len(phone_r), "mac": len(mac_r), "matched": len(pairs),
        "only_phone": len(phone_r) - len(pairs), "only_mac": len(mac_r) - len(pairs),
        "iou_threshold": iou_thr,
        "pairs": [{"phone": phone_r[i]["index"], "mac": mac_r[j]["index"], "iou": round(v, 3),
                   "phone_span": [phone_r[i]["start"], phone_r[i]["end"]],
                   "mac_span": [mac_r[j]["start"], mac_r[j]["end"]],
                   "phone_end_reason": phone_r[i]["end_reason"],
                   "mac_end_reason": mac_r[j]["end_reason"]}
                  for i, j, v in pairs],
    }


def compare_analyses(phone: dict, mac: dict, tol: int = 3, iou_thr: float = 0.5) -> dict:
    ph, mh = hits_from_analysis(phone), hits_from_analysis(mac)
    return {
        "hits": match_hits(ph, mh, tol),
        "rallies": match_rallies(rally_rows(phone), rally_rows(mac), iou_thr),
        "camera": {"phone": camera_info(phone), "mac": camera_info(mac)},
        "top_speed_kmh": {"phone": top_speed_kmh(phone), "mac": top_speed_kmh(mac)},
        "visible": {"phone": visible_fraction(phone), "mac": visible_fraction(mac)},
        "stages_seconds": {"phone": stage_seconds(phone.get("diagnostics")),
                           "mac": stage_seconds(mac.get("diagnostics"))},
        "processing_time_seconds": {"phone": phone.get("processing_time_seconds"),
                                    "mac": mac.get("processing_time_seconds")},
    }


def calibration_reason(ans: dict) -> str:
    """Human-readable why the automatic calibration failed (best effort)."""
    diag = ans.get("diagnostics") or {}
    cal = diag.get("calibration")
    if isinstance(cal, dict):
        if cal.get("reason"):
            return str(cal["reason"])
        if cal.get("error"):
            return str(cal["error"])
    st = (diag.get("stages") or {}).get("calibrate") or {}
    if st and st.get("ok") is False:
        return str(st.get("error") or "calibrate stage failed")
    stats = {k: v for k, v in diag.items() if k not in ("candidates", "calibration_attempt")}
    if isinstance(cal, dict):                      # stats nested one level down
        stats.update(cal)
    attempt = diag.get("calibration_attempt")
    if isinstance(attempt, dict):                  # stats from analyze.py's explain step
        stats.update({k: v for k, v in attempt.items() if v is not None})
    bits = []
    if "n_lines" in stats:
        bits.append(f"检测到直线 {stats.get('n_lines')} 条")
    if "n_hyp" in stats:
        bits.append(f"候选 {stats.get('n_hyp')} 个")
    if "n_valid" in stats:
        bits.append(f"通过证据检验 {stats.get('n_valid')} 个")
    if stats.get("coverage") is not None:
        bits.append(f"coverage={float(stats['coverage']):.2f}")
    if stats.get("rmse") is not None:
        bits.append(f"rmse={float(stats['rmse']):.2f}px")
    if stats.get("n_absent") is not None:
        bits.append(f"缺失线={stats.get('n_absent')}")
    if stats.get("explained_frac") is not None:
        bits.append(f"explained={float(stats['explained_frac']):.2f}")
    if stats.get("confidence") is not None:
        bits.append(f"confidence={float(stats['confidence']):.2f}")
    return "自动标定未通过（" + ", ".join(bits) + "）" if bits else "自动标定未通过（无诊断信息）"


# --------------------------------------------------------------------------- drawing

def _finite_runs(uv: np.ndarray, size: tuple[int, int], margin: float = 0.15) -> list[np.ndarray]:
    w, h = size
    ok = np.all(np.isfinite(uv), axis=1)
    runs = []
    i, n = 0, len(uv)
    while i < n:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j < n and ok[j]:
            j += 1
        if j - i >= 2:
            seg = uv[i:j]
            m = margin * max(w, h)
            inside = ((seg[:, 0] > -m) & (seg[:, 0] < w + m)
                      & (seg[:, 1] > -m) & (seg[:, 1] < h + m))
            if inside.any():
                runs.append(np.round(seg).astype(np.int32))
        i = j
    return runs


def _resample(a: np.ndarray, b: np.ndarray, n: int = 40) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)[:, None]
    return a[None, :] + (b - a)[None, :] * t


def court_polylines(cam: CameraModel, samples: int = 40) -> list[np.ndarray]:
    """Floor court lines projected into the image, split at the horizon."""
    out = []
    for a, b in cm.COURT_LINES.values():
        P = np.column_stack([_resample(np.asarray(a, float), np.asarray(b, float), samples),
                             np.zeros((samples, 1))])
        out.extend(_finite_runs(cam.project(P), tuple(cam.image_size)))
    return out


def net_polylines(cam: CameraModel, samples: int = 28) -> list[np.ndarray]:
    """Net tape curve, mesh bottom curve and the two posts."""
    ys = np.linspace(-cm.DOUBLES_HALF_WIDTH, cm.DOUBLES_HALF_WIDTH, samples)
    top = cm.NET_HEIGHT_CENTRE + (cm.NET_HEIGHT_POST - cm.NET_HEIGHT_CENTRE) * (ys / cm.DOUBLES_HALF_WIDTH) ** 2
    zero = np.zeros_like(ys)
    out = []
    tape = np.column_stack([zero, ys, top])
    out.extend(_finite_runs(cam.project(tape), tuple(cam.image_size)))
    for s in (-1.0, 1.0):
        y = s * cm.DOUBLES_HALF_WIDTH
        post = np.array([[0.0, y, 0.0], [0.0, y, cm.NET_HEIGHT_POST]])
        out.extend(_finite_runs(cam.project(post), tuple(cam.image_size)))
    # a few vertical mesh strings for depth
    for y in (-1.5, -0.75, 0.0, 0.75, 1.5):
        z = cm.NET_HEIGHT_CENTRE + (cm.NET_HEIGHT_POST - cm.NET_HEIGHT_CENTRE) * (y / cm.DOUBLES_HALF_WIDTH) ** 2
        seg = np.array([[0.0, y, 0.79], [0.0, y, z]])
        out.extend(_finite_runs(cam.project(seg), tuple(cam.image_size)))
    return out


def static_court_layer(shape: tuple[int, int, int], cam: CameraModel, caliber_good: bool,
                       scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Pre-render the (static) court for compositing every frame.

    Returns (BGR layer, uint8 mask). The mask is drawn with LINE_AA so the
    fast cv2-based blend in blend_layer keeps the anti-aliased edge coverage.
    """
    layer = np.zeros(shape, np.uint8)
    mask = np.zeros(shape[:2], np.uint8)
    thick = max(1, int(round(2 * scale)))
    color = (0, 255, 0) if caliber_good else (0, 165, 255)      # green / orange (BGR)
    for poly in court_polylines(cam):
        cv2.polylines(layer, [poly], False, color, thick + 1, cv2.LINE_AA)
        cv2.polylines(mask, [poly], False, 255, thick + 1, cv2.LINE_AA)
    for poly in net_polylines(cam):
        cv2.polylines(layer, [poly], False, (255, 190, 90), max(1, thick), cv2.LINE_AA)
        cv2.polylines(mask, [poly], False, 255, max(1, thick), cv2.LINE_AA)
    return layer, mask


def blend_layer(frame: np.ndarray, layer: np.ndarray, mask: np.ndarray, alpha: float = 0.85) -> None:
    """Alpha-composite a pre-rendered layer (BGR) through a uint8 mask.

    cv2.addWeighted + copyTo is ~20x faster than numpy boolean indexing on 1080p.
    """
    if mask is None or not mask.any():
        return
    if mask.dtype != np.uint8:
        mask = (mask > 0).astype(np.uint8) * 255
    blend = cv2.addWeighted(layer, alpha, frame, 1.0 - alpha, 0.0)
    cv2.copyTo(blend, mask, frame)


def dark_box(frame: np.ndarray, x: int, y: int, w: int, h: int, alpha: float = 0.55) -> None:
    h = min(h, frame.shape[0] - y)
    w = min(w, frame.shape[1] - x)
    if h <= 1 or w <= 1 or x < 0 or y < 0:
        return
    sub = frame[y:y + h, x:x + w]
    cv2.addWeighted(sub, 1.0 - alpha, np.zeros_like(sub), alpha, 0.0, dst=sub)


class TextRenderer:
    """Chinese-capable, cached text blitter (PIL). Falls back to cv2.putText."""

    def __init__(self, base_px: int = 34, max_cache: int = 3000):
        self.base_px = int(base_px)
        self.max_cache = max_cache
        self._cache: dict[tuple, Any] = {}
        self._font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
        self._pil_ok = False
        if self._font_path:
            try:
                from PIL import ImageFont  # noqa: F401
                self._pil_ok = True
            except Exception:
                self._pil_ok = False

    def _font(self, px: int):
        from PIL import ImageFont
        key = ("font", px)
        f = self._cache.get(key)
        if f is None:
            f = ImageFont.truetype(self._font_path, px)
            if len(self._cache) > self.max_cache:
                self._cache.clear()
            self._cache[key] = f
        return f

    def sprite(self, text: str, px: int | None = None, color=(255, 255, 255)):
        """(rgb uint8 HxWx3, alpha uint8 HxW) for `text`, cached."""
        px = int(px or self.base_px)
        key = (text, px, tuple(color))
        spr = self._cache.get(key)
        if spr is not None:
            return spr
        if self._pil_ok:
            from PIL import Image, ImageDraw
            f = self._font(px)
            box = f.getbbox(text or " ")
            w = max(1, box[2] - box[0] + 4)
            h = max(1, box[3] - box[1] + 4)
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.text((2 - box[0], 2 - box[1]), text, font=f, fill=(*color, 255))
            a = np.array(img)
            spr = (np.ascontiguousarray(a[:, :, 2::-1]), np.ascontiguousarray(a[:, :, 3]))
        else:
            scale = max(0.4, px / 30.0)
            (tw, th), _ = cv2.getTextSize(text or " ", cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            rgb = np.zeros((th + 6, tw + 6, 3), np.uint8)
            cv2.putText(rgb, text or " ", (3, th + 3), cv2.FONT_HERSHEY_SIMPLEX, scale,
                        tuple(int(c) for c in color), max(1, int(scale * 1.5)), cv2.LINE_AA)
            spr = (rgb, (cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY) > 0).astype(np.uint8) * 255)
        if len(self._cache) > self.max_cache:
            self._cache.clear()
        self._cache[key] = spr
        return spr

    def size(self, text: str, px: int | None = None) -> tuple[int, int]:
        rgb, _ = self.sprite(text, px)
        return rgb.shape[1], rgb.shape[0]

    def draw(self, frame: np.ndarray, text: str, xy: tuple[int, int], px: int | None = None,
             color=(255, 255, 255)) -> tuple[int, int]:
        """Blit `text` with its top-left at xy; returns the sprite size."""
        rgb, alpha = self.sprite(text, px, color)
        h, w = rgb.shape[:2]
        x, y = int(xy[0]), int(xy[1])
        if x >= frame.shape[1] or y >= frame.shape[0]:
            return (w, h)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
        if x1 <= x0 or y1 <= y0:
            return (w, h)
        sx0, sy0 = x0 - x, y0 - y
        roi = frame[y0:y1, x0:x1]
        sp = rgb[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)].astype(np.float32)
        al = alpha[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)].astype(np.float32)[..., None] / 255.0
        roi[:] = (roi.astype(np.float32) * (1.0 - al) + sp * al).astype(np.uint8)
        return (w, h)

    def draw_panel(self, frame: np.ndarray, lines: Iterable[str], xy: tuple[int, int],
                   px: int | None = None, pad: int = 10, color=(255, 255, 255),
                   alpha: float = 0.6) -> None:
        """Dark translucent box with several lines of text."""
        px = int(px or self.base_px)
        lines = [ln for ln in lines if ln]
        if not lines:
            return
        sizes = [self.size(ln, px) for ln in lines]
        lh = int(px * 1.35)
        w = max(s[0] for s in sizes) + 2 * pad
        h = lh * len(lines) + 2 * pad - int(px * 0.3)
        x, y = int(xy[0]), int(xy[1])
        x = max(0, min(x, frame.shape[1] - w - 1))
        y = max(0, min(y, frame.shape[0] - h - 1))
        if w < frame.shape[1] and h < frame.shape[0]:
            dark_box(frame, x, y, w, h, alpha)
        for k, ln in enumerate(lines):
            self.draw(frame, ln, (x + pad, y + pad + k * lh), px, color)


# --------------------------------------------------------------------------- writer

def open_writer(path: str | Path, fps: float, size: tuple[int, int], prefer_avf: bool = False):
    """VideoWriter: AVFoundation (hardware H.264, macOS) → 'avc1' → 'mp4v'.

    iPhone footage is HEVC: decoding it with AVFoundation and encoding with the
    FFmpeg H.264 encoder competes for the media engine (1080p60 dropped to ~18 fps).
    The AVFoundation writer keeps everything in VideoToolbox (~7 ms/frame).
    """
    if prefer_avf and sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
        p = Path(path)
        if p.exists():
            try:
                p.unlink()          # AVAssetWriter refuses to overwrite an existing file
            except OSError:
                pass
        w = cv2.VideoWriter(str(p), cv2.CAP_AVFOUNDATION, cv2.VideoWriter_fourcc(*"avc1"),
                            float(fps), size)
        if w.isOpened():
            return w, "avf-h264"
        w.release()
    for cc in ("avc1", "mp4v"):
        w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*cc), float(fps), size)
        if w.isOpened():
            return w, cc
        w.release()
    raise RuntimeError(f"cv2.VideoWriter could not open any codec for {path}")


def verify_video(path: str | Path, min_frames: int = 5) -> bool:
    """True when the written file can be re-opened and has readable frames."""
    p = Path(path)
    if not p.is_file() or p.stat().st_size < 1024:
        return False
    cap = open_capture(p, prefer_avfoundation=False)
    n = 0
    try:
        while n < min_frames:
            ok, f = cap.read()
            if not ok or f is None or not f.size:
                break
            n += 1
    finally:
        cap.release()
    return n >= min_frames


def iter_video_frames(path: str | Path, start: int = 0, stop: int | None = None,
                      max_frames: int | None = None):
    """Stream upright BGR frames with their index (never holds the video in RAM).

    A declared-frame cap (max_frames) is a safety net: some containers make the
    FFmpeg backend stall at EOF, so the caller's expected length is authoritative.
    """
    cap = open_capture(path, start=start)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    n = 0
    i = start
    try:
        while stop is None or i < stop:
            ok, f = cap.read()
            if not ok or f is None or not f.size:
                break
            yield i, f
            i += 1
            n += 1
            if max_frames is not None and n >= max_frames:
                break
    finally:
        cap.release()


def resize_keep(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= width:
        return img
    return cv2.resize(img, (width, int(round(h * width / w))), interpolation=cv2.INTER_AREA)


# --------------------------------------------------------------------------- errors

class VenueError(RuntimeError):
    """Expected, user-facing failure (exit code 1 with a clear message)."""


def require_file(path: str | Path, what: str = "file") -> Path:
    p = Path(path)
    if not p.exists():
        raise VenueError(f"{what} not found: {p}")
    return p
