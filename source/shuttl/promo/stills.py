"""Render chosen timestamps to a labelled contact sheet for review.

usage: .venv/bin/python stills.py out.png 0.3 0.6 1.2 ...   (or  a:b:step)
"""
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
URL = (ROOT / "web" / "index.html").as_uri()


def times(args):
    out = []
    for a in args:
        if ":" in a:
            s, e, st = map(float, a.split(":"))
            x = s
            while x <= e + 1e-9:
                out.append(round(x, 3)); x += st
        else:
            out.append(float(a))
    return out


def open_page(p):
    b = p.chromium.launch(args=["--allow-file-access-from-files", "--disable-web-security"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_function("window.READY === true", timeout=30000)
    return b, pg, errs


def main():
    out, ts = sys.argv[1], times(sys.argv[2:])
    cols = min(len(ts), 6)
    tw, th = 360, 640
    rows = (len(ts) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 34)), "white")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 22)
    with sync_playwright() as p:
        b, pg, errs = open_page(p)
        for i, t in enumerate(ts):
            pg.evaluate(f"seek({t})")
            im = Image.open(BytesIO(pg.screenshot(type="png"))).convert("RGB")
            if len(ts) == 1:
                im.save(out); print("saved", out); break
            x, y = (i % cols) * tw, (i // cols) * (th + 34)
            sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y + 34))
            d.text((x + 8, y + 5), f"{t:.2f}s", fill="black", font=font)
        b.close()
    if len(ts) > 1:
        sheet.save(out); print("saved", out)
    for e in errs[:20]:
        print("PAGE:", e)


if __name__ == "__main__":
    main()
