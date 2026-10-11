"""Render promo2: dump sound cues → synth soundtrack → frames (parallel Chromium) → H.264 → mux.

usage: ../promo/.venv/bin/python render.py [--workers 8] [--fps 60] [--from 0 --to 60] [--audio-only]
       [--out out/Shuttl-宣传片-2.mp4]
"""
import argparse
import json
import subprocess
import sys
import time
from multiprocessing import Process
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
URL = (ROOT / "web" / "index.html").as_uri()
FF = str(next((ROOT.parent / "promo/.venv/lib").glob("python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*")))
BUILD = ROOT / "build"


def page(p):
    b = p.chromium.launch(args=["--allow-file-access-from-files", "--disable-web-security", "--force-color-profile=srgb"])
    pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_function("window.READY === true", timeout=60000)
    return b, pg, errs


def worker(i, f0, f1, fps):
    out = BUILD / f"seg{i:02d}.mp4"
    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                            "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-tune", "animation", "-pix_fmt", "yuv420p",
                            "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
                            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                            "-g", str(fps * 2), "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    with sync_playwright() as p:
        b, pg, errs = page(p)
        t0 = time.time()
        for f in range(f0, f1):
            pg.evaluate(f"seek({f / fps})")
            enc.stdin.write(pg.screenshot(type="png"))
            if (f - f0) % 300 == 0:
                print(f"  w{i}: frame {f} ({f - f0}/{f1 - f0}) {time.time() - t0:.0f}s", flush=True)
        b.close()
        if errs:
            print(f"  w{i} page errors:", errs[:5], flush=True)
    enc.stdin.close(); enc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "out" / "Shuttl-宣传片-2.mp4"))
    a = ap.parse_args()
    BUILD.mkdir(exist_ok=True); Path(a.out).parent.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b, pg, errs = page(p)
        cues, dur = pg.evaluate("getCues()"), pg.evaluate("DURATION")
        b.close()
    if errs:
        print("page errors:", errs[:5])
    (BUILD / "cues.json").write_text(json.dumps(cues))
    print(f"{len(cues)} cues, duration {dur}s")
    subprocess.run([sys.executable, str(ROOT / "audio_music2.py"), str(BUILD / "cues.json"), str(BUILD / "music.wav")], check=True, cwd=ROOT)
    if a.audio_only:
        return
    t1 = a.t1 if a.t1 is not None else dur
    F0, F1 = round(a.t0 * a.fps), round(t1 * a.fps)
    n = a.workers
    edges = [F0 + (F1 - F0) * k // n for k in range(n + 1)]
    for old in BUILD.glob("seg*.mp4"):
        old.unlink()
    t = time.time()
    ps = [Process(target=worker, args=(k, edges[k], edges[k + 1], a.fps)) for k in range(n)]
    [q.start() for q in ps]; [q.join() for q in ps]
    print(f"frames rendered in {time.time() - t:.0f}s")
    lst = BUILD / "segs.txt"
    lst.write_text("".join(f"file '{BUILD / f'seg{k:02d}.mp4'}'\n" for k in range(n)))
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-ss", str(a.t0), "-t", str(t1 - a.t0),
                    "-i", str(BUILD / "music.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1", "-c:a", "aac", "-b:a", "256k",
                    "-movflags", "+faststart", "-shortest", a.out], check=True)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
