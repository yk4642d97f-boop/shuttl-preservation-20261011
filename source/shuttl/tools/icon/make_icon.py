"""Shuttl app icon, drawn as a two-drum risograph print.

Two spot inks (cobalt, tomato) are laid on warm paper and multiply where they
overlap, making a third colour out of two (Albers). The shuttlecock is
knocked out of both drums, so it is bare paper. The drums sit a few px out of
register, the way a riso drum always does. The butter trail is the tracker's
signature: dots whose spacing shrinks toward the head as the shuttle
decelerates under drag.

Usage (from the repo root):
  backend/.venv/bin/python tools/icon/make_icon.py <out_dir> [--variant NAME]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 4096                      # supersampled canvas; downsampled to 1024
PAPER = (0xF4, 0xEE, 0xE3)
INK = (0x22, 0x1B, 0x2E)
COBALT = (0x2F, 0x4B, 0xDE)
TOMATO = (0xF2, 0x54, 0x2D)
BUTTER = (0xF7, 0xD9, 0x5C)
LILAC = (0xC7, 0xB6, 0xF2)
PISTACHIO = (0xB9, 0xD6, 0x6A)
NIGHT = (0x15, 0x12, 0x1C)


def u(v: float) -> int:
    """Icon units (0..100) → canvas px."""
    return int(round(v * S / 100))


def mask() -> Image.Image:
    return Image.new("L", (S, S), 0)


def disc(m: Image.Image, cx: float, cy: float, r: float) -> None:
    ImageDraw.Draw(m).ellipse([u(cx - r), u(cy - r), u(cx + r), u(cy + r)], fill=255)


def shuttle_polys(cx: float, cy: float, length: float, angle_deg: float):
    """Shuttlecock pointing along angle (cork at the head): cork disc + skirt."""
    a = math.radians(angle_deg)
    d = np.array([math.cos(a), math.sin(a)])       # head direction
    n = np.array([-d[1], d[0]])
    head = np.array([cx, cy]) + d * length * 0.5
    cork_r = length * 0.17
    cork_c = head - d * cork_r
    neck = cork_c - d * cork_r * 0.55
    tail = head - d * length
    w_neck, w_tail = length * 0.13, length * 0.42
    # skirt rim: 5 feather tips, shallow so it reads as a shuttle and not a fan
    rim = []
    lobes = 5
    for i in range(lobes * 8 + 1):
        t = i / (lobes * 8)
        s = (t - 0.5) * 2 * w_tail
        bulge = abs(math.sin(math.pi * t * lobes)) * length * 0.045
        rim.append(tail + n * s - d * bulge)
    skirt = [neck + n * w_neck] + rim[::-1] + [neck - n * w_neck]
    ribs = []
    for k in range(1, lobes):
        t = k / lobes
        s = (t - 0.5) * 2 * w_tail
        ribs.append((neck + n * (t - 0.5) * 2 * w_neck, tail + n * s))
    return cork_c, cork_r, skirt, ribs, d


def draw_shuttle(m: Image.Image, cx, cy, length, angle, rib_w=0.0, ribs_cut: Image.Image | None = None):
    cork_c, cork_r, skirt, ribs, _ = shuttle_polys(cx, cy, length, angle)
    dr = ImageDraw.Draw(m)
    dr.polygon([(u(p[0]), u(p[1])) for p in skirt], fill=255)
    dr.ellipse([u(cork_c[0] - cork_r), u(cork_c[1] - cork_r), u(cork_c[0] + cork_r), u(cork_c[1] + cork_r)], fill=255)
    if ribs_cut is not None and rib_w > 0:
        dc = ImageDraw.Draw(ribs_cut)
        for a_, b_ in ribs:
            dc.line([(u(a_[0]), u(a_[1])), (u(b_[0]), u(b_[1]))], fill=255, width=u(rib_w))
    return cork_c, cork_r


def trail(m: Image.Image, pts: np.ndarray, r0: float, r1: float) -> None:
    """Dots along a flight path, spacing already baked into pts; radius r0→r1."""
    for i, p in enumerate(pts):
        t = i / max(len(pts) - 1, 1)
        disc(m, p[0], p[1], r0 + (r1 - r0) * t)


def flight(p0, p1, apex_lift: float, n: int, drag: float = 2.2) -> np.ndarray:
    """Quadratic arc p0→p1; parameter warped so dots bunch up near the head."""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    mid = (p0 + p1) / 2 + np.array([0, -apex_lift])
    out = []
    for i in range(n):
        s = i / (n - 1)
        t = 1 - (1 - s) ** drag           # drag: equal time steps cover less ground late
        out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * mid + t ** 2 * p1)
    return np.array(out)


def compose(layers, bg=PAPER, grain=0.035, seed=7) -> Image.Image:
    """layers: (mask, rgb, (dx, dy) misregistration in icon units[, mode]).
    mode "mul" = transparent ink multiplying what is under it (riso overprint);
    mode "over" = the layer knocks out what is under it (light ink on a dark field)."""
    img = np.ones((S, S, 3), np.float32) * (np.array(bg, np.float32) / 255)
    rng = np.random.default_rng(seed)
    for layer in layers:
        m, rgb, (dx, dy) = layer[:3]
        mode = layer[3] if len(layer) > 3 else "mul"
        a = np.asarray(m.transform(m.size, Image.AFFINE, (1, 0, -u(dx), 0, 1, -u(dy))), np.float32) / 255
        ink = np.array(rgb, np.float32) / 255
        # riso ink coverage is never perfectly flat: slight density variation per drum
        a = a * (0.94 + 0.06 * rng.random((1, 1), np.float32))
        top = img * ink if mode == "mul" else np.broadcast_to(ink, img.shape)
        img = img * (1 - a[..., None]) + top * a[..., None]
    out = Image.fromarray(np.clip(img * 255, 0, 255).astype(np.uint8)).resize((1024, 1024), Image.LANCZOS)
    if grain > 0:
        g = np.random.default_rng(seed + 1).normal(0, 1, (1024, 1024, 1)).astype(np.float32)
        g = np.asarray(Image.fromarray(((g[..., 0] * 40) + 128).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)), np.float32)
        g = (g - 128) / 40
        arr = np.asarray(out, np.float32) * (1 + grain * g[..., None])
        out = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    return out


def _cut(a: Image.Image, b: Image.Image) -> Image.Image:
    return Image.fromarray(np.minimum(np.asarray(a), 255 - np.asarray(b)))


def _keep(a: Image.Image, b: Image.Image) -> Image.Image:
    return Image.fromarray(np.minimum(np.asarray(a), np.asarray(b)))


def variant_overprint() -> Image.Image:
    """Paper stock, cobalt + tomato drums overlapping, shuttle knocked out of both.
    The overlap multiplies into a deep aubergine, so the knocked-out paper shuttle
    sits on the darkest, highest-contrast field in the middle of the tile."""
    cob, tom, knock, ribs, dots = _overprint_masks()
    return compose([(cob, COBALT, (0, 0)), (tom, TOMATO, (0.5, -0.35)),
                    (dots, BUTTER, (0, 0), "over"), (ribs, INK, (0, 0), "over")])


def _overprint_masks():
    cob, tom, knock, ribs, dots = mask(), mask(), mask(), mask(), mask()
    # one drum per half of the court; the overlap is the net band the shuttle crosses
    disc(cob, 36, 64, 37)
    disc(tom, 64, 36, 33)
    draw_shuttle(knock, 52, 49, 43, -45, rib_w=1.0, ribs_cut=ribs)
    # drag: later dots sit closer together, but they must never merge into a blob
    trail(dots, flight((15, 86), (28.5, 72.5), 6, 4, drag=1.25), 1.2, 1.9)
    dots = _keep(dots, cob)
    return _cut(cob, knock), _cut(tom, knock), knock, _keep(ribs, knock), dots


def variant_overprint_dark() -> Image.Image:
    """iOS 18 dark appearance: same print on night stock. Multiply would vanish on a
    dark field, so the overlap is laid as its own mixed ink (cobalt × tomato)."""
    cob, tom, knock, ribs, dots = _overprint_masks()
    both = _keep(cob, tom)
    mixed = tuple(int(a * b / 255) for a, b in zip(COBALT, TOMATO))
    return compose([(cob, COBALT, (0, 0), "over"), (tom, TOMATO, (0.5, -0.35), "over"),
                    (both, mixed, (0, 0), "over"), (knock, PAPER, (0, 0), "over"),
                    (dots, BUTTER, (0, 0), "over"), (ribs, INK, (0, 0), "over")], bg=NIGHT, grain=0.02)


def variant_overprint_tinted() -> Image.Image:
    """iOS 18 tinted appearance: grayscale on black; the system applies the tint."""
    return variant_overprint_dark().convert("L").convert("RGB")


def variant_split() -> Image.Image:
    """Tomato / cobalt split diagonally along the flight line; the shuttle straddles it,
    printed in paper, with a butter drag-dot trail on the cobalt side."""
    tom, knock, cork, dots, ribs = mask(), mask(), mask(), mask(), mask()
    ImageDraw.Draw(tom).polygon([(0, 0), (S, 0), (S, u(38)), (0, u(78))], fill=255)
    cc, cr = draw_shuttle(knock, 55, 46, 50, -40, rib_w=1.0, ribs_cut=ribs)
    disc(cork, cc[0], cc[1], cr)
    trail(dots, flight((7, 97), (30, 74), 10, 5, drag=1.8), 1.6, 2.9)
    return compose([(mask_full(), COBALT, (0, 0), "over"), (_cut(tom, knock), TOMATO, (0, 0), "over"),
                    (_cut(dots, knock), BUTTER, (0, 0), "over"), (knock, PAPER, (0, 0), "over"),
                    (cork, INK, (0, 0), "over"), (_keep(ribs, knock), LILAC, (0, 0), "over")])


def mask_full() -> Image.Image:
    return Image.new("L", (S, S), 255)


def variant_night() -> Image.Image:
    """Night surround, pistachio court in perspective, trail rising off it."""
    court, lines, dots, sh, cork = mask(), mask(), mask(), mask(), mask()
    dc = ImageDraw.Draw(court)
    quad = [(18, 90), (82, 90), (66, 58), (34, 58)]
    dc.polygon([(u(x), u(y)) for x, y in quad], fill=255)
    dl = ImageDraw.Draw(lines)
    w = u(0.9)
    for (x0, y0), (x1, y1) in [((50, 90), (50, 58)), ((23.3, 80), (76.7, 80)), ((30.3, 67), (69.7, 67))]:
        dl.line([(u(x0), u(y0)), (u(x1), u(y1))], fill=255, width=w)
    dl.polygon([(u(x), u(y)) for x, y in quad], outline=255, width=w)
    trail(dots, flight((24, 84), (66, 30), 26, 9), 1.0, 2.6)
    cc, cr = draw_shuttle(sh, 70, 25, 22, -60)
    disc(cork, cc[0], cc[1], cr)
    lines = Image.fromarray(np.minimum(np.asarray(lines), np.asarray(court)))
    return compose([(court, PISTACHIO, (0, 0), "over"), (lines, PAPER, (0, 0), "over"),
                    (dots, BUTTER, (0, 0), "over"), (sh, PAPER, (0, 0), "over"),
                    (cork, TOMATO, (0, 0), "over")], bg=NIGHT, grain=0.02)


def variant_cobalt() -> Image.Image:
    """Cobalt stock, big paper shuttle, butter drag-dotted trail, tomato cork."""
    field, knock, cork, dots, ribs = mask(), mask(), mask(), mask(), mask()
    ImageDraw.Draw(field).rectangle([0, 0, S, S], fill=255)
    cc, cr = draw_shuttle(knock, 56, 45, 50, -40, rib_w=1.0, ribs_cut=ribs)
    disc(cork, cc[0], cc[1], cr)
    trail(dots, flight((6, 96), (30, 74), 10, 5, drag=1.8), 1.6, 3.0)
    field = _cut(field, knock)
    ribs = _keep(ribs, knock)
    return compose([(field, COBALT, (0, 0)), (dots, BUTTER, (0, 0), "over"),
                    (cork, TOMATO, (0.35, -0.25), "over"), (ribs, LILAC, (0, 0), "over")])


VARIANTS = {"overprint": variant_overprint, "overprint_dark": variant_overprint_dark,
            "overprint_tinted": variant_overprint_tinted, "split": variant_split,
            "night": variant_night, "cobalt": variant_cobalt}

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shuttl_icons")
    out.mkdir(parents=True, exist_ok=True)
    names = [sys.argv[sys.argv.index("--variant") + 1]] if "--variant" in sys.argv else list(VARIANTS)
    for name in names:
        im = VARIANTS[name]()
        im.save(out / f"icon_{name}.png")
        print(out / f"icon_{name}.png")
