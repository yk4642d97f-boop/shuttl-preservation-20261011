"""calib_sweep2 scene rendering: the test renderer (tests.test_court_calibration) plus the
Task 9 hard cases. Plain cases call render_frames unchanged (same frames as calib_sweep).

Hard cases (all on top of render_background, then the render_frames degradations):
  occlusion     2–3 extra players standing STILL on court lines in every frame, thicker
                net posts (0.10 m)
  second_court  a neighbouring court: the full line set again, shifted sideways by the
                doubles width + 1.0–3.0 m (multi-court hall)
  wood_tape     wood floor + 3–6 tape strips (white and coloured) on the floor
  motion_blur   linear blur 5–15 px, random direction, on every frame
  exposure      per-frame gain 0.6–1.4 and gamma 0.8–1.25 (auto-exposure hunting)
  zoom          focal 1100–1700 px (set in cases.py; rendered plain)
Grid "colour" (cases.py): kind colour_lines — the plain scene with the court lines painted
  case["line_bgr"] (yellow, light blue, red, orange) instead of white.
"""

from __future__ import annotations

import cv2
import numpy as np

import cases  # noqa: F401  (sys.path)
from tests import test_court_calibration as t  # noqa: E402
from app.services.tracking import court_model as cm  # noqa: E402


def _second_court_lines(rng: np.random.Generator) -> dict:
    dy = 2 * cm.DOUBLES_HALF_WIDTH + rng.uniform(1.0, 3.0)
    s = float(rng.choice([-1.0, 1.0])) * dy
    out = dict(cm.COURT_LINES)
    for k, ((ax, ay), (bx, by)) in cm.COURT_LINES.items():
        out[f"{k}_2"] = ((ax, ay + s), (bx, by + s))
    return out


def _tape(img: np.ndarray, cam, rng: np.random.Generator) -> None:
    for _ in range(int(rng.integers(3, 7))):
        x0, y0 = rng.uniform(-9, 9), rng.uniform(-5, 5)
        ang, L, wdt = rng.uniform(0, np.pi), rng.uniform(1.0, 5.0), rng.uniform(0.03, 0.06)
        u = np.array([np.cos(ang), np.sin(ang), 0.0])
        n = np.array([-u[1], u[0], 0.0]) * wdt / 2
        p = np.array([x0, y0, 0.0])
        quad = np.array([p - n, p + L * u - n, p + L * u + n, p + n])
        col = [(235, 235, 235), (40, 200, 230), (60, 60, 220), (220, 120, 40)][int(rng.integers(0, 4))]
        t._poly(img, cam, quad, col)


def _post(img: np.ndarray, cam) -> None:
    for s in (-1, 1):
        y = s * cm.DOUBLES_HALF_WIDTH
        t._poly(img, cam, np.array([[0.05, y - 0.05, 0], [0.05, y + 0.05, 0], [0.05, y + 0.05, 1.55],
                                    [0.05, y - 0.05, 1.55]]), (30, 40, 30))


def _motion(f: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    L = int(rng.integers(5, 16))
    k = np.zeros((L, L), np.float32)
    k[L // 2, :] = 1.0 / L
    M = cv2.getRotationMatrix2D((L / 2 - 0.5, L / 2 - 0.5), float(rng.uniform(0, 180)), 1.0)
    k = cv2.warpAffine(k, M, (L, L))
    return cv2.filter2D(f, -1, k / max(k.sum(), 1e-6))


def _exposure(f: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    g, gam = rng.uniform(0.6, 1.4), rng.uniform(0.8, 1.25)
    x = np.clip(f.astype(np.float32) * g, 0, 255) / 255.0
    return np.clip(255.0 * x ** gam, 0, 255).astype(np.float32)


def render(case: dict, cam, n: int = 5) -> list[np.ndarray]:
    rng = np.random.default_rng(case["seed"])
    kind = case["kind"]
    if kind in ("plain", "zoom"):
        return t.render_frames(cam, rng, n=n, style=case["style"])
    lines = _second_court_lines(rng) if kind == "second_court" else None
    colour = tuple(case["line_bgr"]) if kind == "colour_lines" else None
    bg = t.render_background(cam, rng, case["style"], True, lines, line_colour=colour)
    still = []
    if kind == "occlusion":
        _post(bg, cam)
        pts = [(-cm.SHORT_SERVICE_X, 0.0), (-cm.DOUBLES_LONG_SERVICE_X, rng.uniform(-2, 2)),
               (rng.uniform(-6, -2), cm.SINGLES_HALF_WIDTH), (cm.SHORT_SERVICE_X, rng.uniform(-1, 1))]
        still = [pts[i] for i in rng.choice(len(pts), int(rng.integers(2, 4)), replace=False)]
    if kind == "wood_tape":
        _tape(bg, cam, rng)
    blur, sigma, q = rng.uniform(0.5, 1.2), rng.uniform(2, 5), int(rng.integers(60, 91))
    grad = (0.85 + 0.25 * np.linspace(0, 1, bg.shape[1], dtype=np.float32))[None, :, None]
    frames = []
    for _ in range(n):
        f = bg.copy()
        for half in (-1, 1):
            t._player(f, cam, half * rng.uniform(1.0, 5.5), rng.uniform(-2.5, 2.5),
                      (245, 245, 245) if half < 0 else (50, 50, 200))
        for (x, y) in still:
            t._player(f, cam, x, y, (60, 160, 60))
        f = cv2.GaussianBlur(f, (0, 0), blur).astype(np.float32) * grad
        if kind == "motion_blur":
            f = _motion(f, rng)
        if kind == "exposure":
            f = _exposure(f, rng)
        f += rng.normal(0, sigma, f.shape).astype(np.float32)
        ok, enc = cv2.imencode(".jpg", np.clip(f, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, q])
        frames.append(cv2.imdecode(enc, cv2.IMREAD_COLOR))
    return frames
