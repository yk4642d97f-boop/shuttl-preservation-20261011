"""Render stills at chosen times into a contact sheet, for checking frames without a full render.

usage: ../promo/.venv/bin/python stills.py 0.5 2 3.5 5 [--cols 4] [--out build/stills.jpg] [--scale 0.4]
"""
import argparse
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
URL = (ROOT / "web" / "index.html").as_uri()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("times", nargs="+", type=float)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--scale", type=float, default=0.4)
    ap.add_argument("--out", default=str(ROOT / "build" / "stills.jpg"))
    a = ap.parse_args()
    shots = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--allow-file-access-from-files", "--disable-web-security", "--force-color-profile=srgb"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.goto(URL)
        pg.wait_for_function("window.READY === true", timeout=60000)
        for t in a.times:
            pg.evaluate(f"seek({t})")
            shots.append(Image.open(io.BytesIO(pg.screenshot(type="png"))).convert("RGB"))
        b.close()
    if errs:
        print("PAGE ERRORS:", errs[:8])
    w, h = int(1920 * a.scale), int(1080 * a.scale)
    rows = (len(shots) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (w * a.cols + 6 * (a.cols - 1), h * rows + 6 * (rows - 1)), (0, 0, 0))
    for i, im in enumerate(shots):
        sheet.paste(im.resize((w, h), Image.LANCZOS), ((i % a.cols) * (w + 6), (i // a.cols) * (h + 6)))
    sheet.save(a.out, quality=85)
    print("wrote", a.out, sheet.size)


if __name__ == "__main__":
    main()
