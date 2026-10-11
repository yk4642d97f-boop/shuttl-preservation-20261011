#!/usr/bin/env python3
"""calib_sweep.py — which tripod positions does the automatic court calibration handle?

Usage:
  ./calib_sweep.py [-h] [--quick] [--workers 4] [--scenes 3] [--frames 5]
                   [--csv tools/venue/calib_sweep.csv] [--heatmap calib_sweep.png]

Sweeps camera height 0.8–2.5 m × distance behind the near baseline 0.5–5 m ×
lateral offset 0–3 m × roll 0/3° × 3 random synthetic scenes (the test renderer
`tests.test_court_calibration.render_frames`), runs the real
`court_calibration.calibrate_from_frames` on every case and records acceptance,
the reject reason, keypoint error vs the true camera (px and floor metres) and
the focal error. Writes CSV + heat-map PNG and prints a Chinese summary.

Cameras: iPhone main camera ≈ 70° horizontal FOV at 1920×1080 → focal 1370 px,
aimed at the court centre.
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
import csv
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venue_common import VenueError, add_backend  # noqa: E402

add_backend()

W, H = 1920, 1080
FOCAL = 2 * (W / 2) / (2 * math.tan(math.radians(70.0) / 2))     # 70° horizontal FOV
HEIGHTS = (0.8, 1.2, 1.6, 2.0, 2.5)
DISTANCES = (0.5, 1.5, 3.0, 5.0)
LATERALS = (0.0, 1.5, 3.0)
ROLLS = (0.0, 3.0)
STYLES = ("green", "wood", "green")

CSV_FIELDS = ["case", "height_m", "dist_m", "lat_m", "roll_deg", "scene", "seed", "style",
              "accepted", "reason", "px_med", "px_max", "floor_med_m", "floor_max_m",
              "focal_rel", "confidence", "coverage", "rmse_px", "explained_frac", "n_t", "n_l",
              "n_absent", "n_lines", "n_hyp", "n_valid", "margin", "render_s", "calib_s"]


# --------------------------------------------------------------------------- one case

def make_camera(height: float, dist: float, lat: float, roll: float):
    from app.services.tracking import court_model as cm
    from app.services.tracking.camera import CameraModel
    eye = np.array([-cm.HALF_LENGTH - dist, lat, height])          # x = behind near baseline
    return CameraModel.look_at(eye, np.array([0.0, 0.0, 0.0]), FOCAL, (W, H), roll_deg=roll)


def errors(true_cam, est_cam) -> dict:
    from app.services.tracking import court_model as cm
    _, P = cm.keypoints_array()
    w, h = true_cam.image_size
    uv = true_cam.project(P)
    vis = np.all(np.isfinite(uv), 1) & (uv[:, 0] >= 0) & (uv[:, 1] >= 0) \
        & (uv[:, 0] < w) & (uv[:, 1] < h)
    if vis.sum() < 4:
        return {}
    uv, Pv = uv[vis], P[vis]
    rep = np.linalg.norm(est_cam.project(Pv) - uv, axis=1)
    g = est_cam.pixel_to_floor(uv)
    werr = np.linalg.norm(g[:, :2] - Pv[:, :2], axis=1)
    werr = werr[np.isfinite(werr)]
    return {"px_med": float(np.median(rep)), "px_max": float(np.max(rep)),
            "floor_med_m": float(np.median(werr)) if len(werr) else float("inf"),
            "floor_max_m": float(np.max(werr)) if len(werr) else float("inf"),
            "focal_rel": abs(est_cam.K[0, 0] / true_cam.K[0, 0] - 1.0)}


def reject_reason(diag: dict, cam) -> str:
    if cam is not None:
        return ""
    from app.services.tracking.court_calibration import MIN_CONFIDENCE, MIN_MARGIN
    if not diag:
        return "no diagnostics"
    if diag.get("n_lines", 0) < 2:
        return f"直线太少(n_lines={diag.get('n_lines', 0)})"
    if not diag.get("n_hyp"):
        return "没有候选(RANSAC 无解)"
    if not diag.get("n_valid"):
        return (f"候选未通过证据检验(n_t={diag.get('n_t')}, n_l={diag.get('n_l')}, "
                f"n_absent={diag.get('n_absent')}, explained={_f(diag.get('explained_frac'))})")
    conf, margin = diag.get("confidence"), diag.get("margin")
    cov, rmse = diag.get("coverage"), diag.get("rmse")
    reasons = []
    if conf is not None and conf < MIN_CONFIDENCE:
        reasons.append(f"置信度低(conf={conf:.2f}<{MIN_CONFIDENCE})")
    if margin is not None and margin < MIN_MARGIN:
        reasons.append(f"有歧义(margin={margin:.3f})")
    if cov is not None and cov < 0.4:
        reasons.append(f"覆盖低(coverage={cov:.2f})")
    if rmse is not None and rmse > 1.5:
        reasons.append(f"拟合差(rmse={rmse:.2f}px)")
    return ", ".join(reasons) if reasons else "未通过阈值(_valid)"


def _f(v) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "?"


def run_case(case: dict) -> dict:
    """Render one synthetic scene and calibrate it. Runs in a worker process."""
    cv2.setNumThreads(1)
    from tests import test_court_calibration as t
    from app.services.tracking import court_calibration as cc

    t0 = time.time()
    cam = make_camera(case["height_m"], case["dist_m"], case["lat_m"], case["roll_deg"])
    rng = np.random.default_rng(case["seed"])
    frames = t.render_frames(cam, rng, n=case["frames"], style=case["style"])
    t_render = time.time() - t0
    diag: dict = {}
    t0 = time.time()
    est = cc.calibrate_from_frames(frames, (W, H), diagnostics=diag)
    t_calib = time.time() - t0
    row = dict(case)
    row["accepted"] = bool(est is not None)
    row["reason"] = reject_reason(diag, est)
    row.update({k: None for k in ("px_med", "px_max", "floor_med_m", "floor_max_m", "focal_rel")})
    if est is not None:
        row.update(errors(cam, est))
        row["confidence"] = est.confidence
        row["accepted"] = True
    row["confidence"] = row.get("confidence") if est is not None else None
    for k in ("coverage", "rmse", "explained_frac", "n_t", "n_l", "n_absent", "n_lines",
              "n_hyp", "n_valid", "margin"):
        row[k] = diag.get(k)
    row["render_s"] = round(t_render, 2)
    row["calib_s"] = round(t_calib, 2)
    return row


# --------------------------------------------------------------------------- sweep

def build_cases(scenes: int, frames: int, quick: bool) -> list[dict]:
    heights = HEIGHTS if not quick else (1.2, 1.6, 2.0)
    dists = DISTANCES if not quick else (1.5, 3.0)
    lats = LATERALS if not quick else (0.0,)
    rolls = ROLLS if not quick else (0.0,)
    scenes = scenes if not quick else 1
    cases = []
    case_id = 0
    for hi, h in enumerate(heights):
        for di, d in enumerate(dists):
            for li, lat in enumerate(lats):
                for ri, roll in enumerate(rolls):
                    for s in range(scenes):
                        case_id += 1
                        cases.append({
                            "case": case_id, "height_m": h, "dist_m": d, "lat_m": lat,
                            "roll_deg": roll, "scene": s,
                            "seed": 10_000_000 + hi * 100_000 + di * 10_000 + li * 1_000
                                    + ri * 100 + s,
                            "style": STYLES[(hi + di + li + ri + s) % len(STYLES)],
                            "frames": frames,
                        })
    return cases


def run_sweep(cases: list[dict], workers: int, csv_path: Path, heat_png: Path | None) -> list[dict]:
    rows: list[dict] = []
    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=max(1, min(4, workers))) as ex:
        futs = {ex.submit(run_case, c): c for c in cases}
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            done += 1
            ok = "OK " if row["accepted"] else "REJ"
            sys.stdout.write(f"\r  {done}/{len(cases)}  [{ok}] h={row['height_m']}m "
                             f"d={row['dist_m']}m lat={row['lat_m']} roll={row['roll_deg']}° "
                             f"scene={row['scene']}  ({time.time() - t0:.0f}s)      ")
            sys.stdout.flush()
    sys.stdout.write("\n")
    rows.sort(key=lambda r: r["case"])
    write_csv(rows, csv_path)
    if heat_png is not None:
        write_heatmap(rows, heat_png)
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


# --------------------------------------------------------------------------- summaries

def group_stats(rows: list[dict], key: str) -> dict:
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    out = {}
    for k, rs in groups.items():
        accepted = [r for r in rs if r["accepted"]]
        floor_max = [r["floor_max_m"] for r in accepted if r.get("floor_max_m") is not None]
        px_max = [r["px_max"] for r in accepted if r.get("px_max") is not None]
        out[k] = {
            "n": len(rs), "accepted": len(accepted),
            "rate": len(accepted) / len(rs) if rs else 0.0,
            "max_floor_p95": float(np.percentile(floor_max, 95)) if floor_max else None,
            "worst_floor": max(floor_max) if floor_max else None,
            "worst_px": max(px_max) if px_max else None,
            "mean_conf": float(np.mean([r["confidence"] for r in accepted])) if accepted else None,
        }
    return out


def reliable_cells(rows: list[dict], min_rate: float = 0.95, max_floor: float = 0.10) -> list[dict]:
    cells = {}
    for r in rows:
        cells.setdefault((r["height_m"], r["dist_m"]), []).append(r)
    out = []
    for (h, d), rs in sorted(cells.items()):
        acc = [r for r in rs if r["accepted"]]
        rate = len(acc) / len(rs)
        worst = max((r["floor_max_m"] for r in acc if r.get("floor_max_m") is not None),
                    default=float("inf"))
        out.append({"height_m": h, "dist_m": d, "n": len(rs), "rate": rate,
                    "worst_floor_m": worst if acc else float("inf"),
                    "ok": rate >= min_rate and worst <= max_floor})
    return out


def summary_text(rows: list[dict]) -> str:
    lines = []
    lines.append("【标定范围扫描结果】iPhone 主摄 1920x1080 70°FOV (f=1370px)，镜头对准球场中心")
    lines.append(f"总case数 {len(rows)}，接受 {sum(1 for r in rows if r['accepted'])} "
                 f"({100 * sum(1 for r in rows if r['accepted']) / len(rows):.1f}%)")
    by_h = group_stats(rows, "height_m")
    by_d = group_stats(rows, "dist_m")
    by_l = group_stats(rows, "lat_m")
    by_r = group_stats(rows, "roll_deg")
    lines.append("\n按高度：")
    for h in sorted(by_h):
        s = by_h[h]
        lines.append(f"  {h}m: 接受 {s['accepted']}/{s['n']} = {100 * s['rate']:.0f}%，"
                     f"最差地面误差 {_f(s['worst_floor'])}m，最差像素误差 {_f(s['worst_px'])}px，"
                     f"平均置信 {_f(s['mean_conf'])}")
    lines.append("按距离（近端底线之后）：")
    for d in sorted(by_d):
        s = by_d[d]
        lines.append(f"  {d}m: 接受 {s['accepted']}/{s['n']} = {100 * s['rate']:.0f}%，"
                     f"最差地面误差 {_f(s['worst_floor'])}m，最差像素误差 {_f(s['worst_px'])}px，"
                     f"平均置信 {_f(s['mean_conf'])}")
    lines.append("按横向偏移：")
    for lat in sorted(by_l):
        s = by_l[lat]
        lines.append(f"  {lat}m: 接受 {s['accepted']}/{s['n']} = {100 * s['rate']:.0f}%，"
                     f"最差地面误差 {_f(s['worst_floor'])}m")
    lines.append("按相机滚转：")
    for r0 in sorted(by_r):
        s = by_r[r0]
        lines.append(f"  {r0}°: 接受 {s['accepted']}/{s['n']} = {100 * s['rate']:.0f}%，"
                     f"最差地面误差 {_f(s['worst_floor'])}m，最差像素误差 {_f(s['worst_px'])}px")

    cells = reliable_cells(rows)
    good = [c for c in cells if c["ok"]]
    worst_ok = max((c["worst_floor_m"] for c in good), default=None)
    lines.append("\n问题1：哪些高度×距离可靠（接受率≥95% 且最差地面误差≤10cm）？")
    if good:
        lines.append("  可靠的位置（高度 × 距近端底线距离）：")
        for c in good:
            lines.append(f"    {c['height_m']}m × {c['dist_m']}m: 接受率 "
                         f"{100 * c['rate']:.0f}%，最差地面误差 {c['worst_floor_m'] * 100:.1f}cm")
        lines.append(f"  → 全部可靠格的最差地面误差 {worst_ok * 100:.1f}cm")
    else:
        lines.append("  没有任何组合同时满足 ≥95% 接受率与 ≤10cm 最差地面误差。")

    lines.append("\n问题2：哪些失败，为什么？")
    fails = [r for r in rows if not r["accepted"]]
    reasons: dict[str, int] = {}
    for r in fails:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    if fails:
        lines.append(f"  失败 {len(fails)} 个，原因分布：")
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:12]:
            lines.append(f"    {n:4d} 个: {reason}")
        lines.append("  失败最多的位置：")
        by_pos: dict[tuple, int] = {}
        for r in fails:
            by_pos[(r["height_m"], r["dist_m"])] = by_pos.get((r["height_m"], r["dist_m"]), 0) + 1
        for (h, d), n in sorted(by_pos.items(), key=lambda kv: -kv[1])[:8]:
            lines.append(f"    h={h}m d={d}m: {n} 个失败")
    else:
        lines.append("  没有失败。")
    if any(r["accepted"] for r in rows):
        acc = [r for r in rows if r["accepted"]]
        worst = max(acc, key=lambda r: r["floor_max_m"] or 0)
        lines.append(f"  接受但误差最大的格子：h={worst['height_m']}m d={worst['dist_m']}m "
                     f"lat={worst['lat_m']}m roll={worst['roll_deg']}° → "
                     f"{_f(worst['floor_max_m'])}m / {_f(worst['px_max'])}px")

    lines.append("\n问题3：明天三脚架怎么摆？")
    best = None
    for c in cells:
        if not c["ok"]:
            continue
        # prefer a mid height, mid distance, and comfortable framing
        score = abs(c["height_m"] - 1.6) + 0.35 * abs(c["dist_m"] - 1.5)
        if best is None or score < best[0]:
            best = (score, c)
    if best:
        c = best[1]
        lines.append(f"  → 高度 {c['height_m']}m，放在近端底线后方 {c['dist_m']}m，"
                     f"横向对准场地中线（偏移 0m），水平仪调平（roll 0°），镜头对准球场中心。")
        lines.append(f"    该组合接受率 {100 * c['rate']:.0f}%，最差地面误差 {c['worst_floor_m'] * 100:.1f}cm。")
    else:
        lines.append("  → 没有可靠组合，请改到更高的位置/更近的距离再试。")
    return "\n".join(lines)


# --------------------------------------------------------------------------- heatmap (PIL only)

def write_heatmap(rows: list[dict], path: Path, min_rate: float = 0.95,
                  max_floor: float = 0.10) -> None:
    from PIL import Image, ImageDraw, ImageFont
    cells = reliable_cells(rows, min_rate, max_floor)
    heights = sorted({c["height_m"] for c in cells})
    dists = sorted({c["dist_m"] for c in cells})
    cw, ch, pad, top, left = 150, 84, 6, 78, 96
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 17)
        small = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 14)
        big = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 20)
    except Exception:                                                   # noqa: BLE001
        font = small = big = None
    title = "球场标定接受率（颜色=接受率，数字=最差地面误差 cm，黑框=可靠）"
    try:
        title_w = int(d.textlength(title, font=big)) + 24
    except Exception:                                                   # noqa: BLE001
        title_w = len(title) * 20
    width = max(left + len(dists) * (cw + pad) + pad, title_w)
    img = Image.new("RGB", (width, top + len(heights) * (ch + pad) + pad + 40), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((left, 10), title, fill=(20, 20, 20), font=big)
    for j, dist in enumerate(dists):
        d.text((left + j * (cw + pad) + 30, top - 30), f"距底线 {dist:g}m", fill=(30, 30, 30), font=font)
    for i, h in enumerate(heights):
        d.text((10, top + i * (ch + pad) + ch / 2 - 10), f"高 {h:g}m", fill=(30, 30, 30), font=font)
    by = {(c["height_m"], c["dist_m"]): c for c in cells}
    for i, h in enumerate(heights):
        for j, dist in enumerate(dists):
            c = by.get((h, dist))
            if c is None:
                continue
            r = c["rate"]
            col = (int(220 - 170 * r), int(90 + 150 * r), 90)
            x0 = left + j * (cw + pad)
            y0 = top + i * (ch + pad)
            d.rectangle([x0, y0, x0 + cw, y0 + ch], fill=col)
            wf = c["worst_floor_m"]
            txt = f"{100 * r:.0f}%  {wf * 100:.1f}cm" if wf != float("inf") else f"{100 * r:.0f}%  —"
            d.text((x0 + 14, y0 + 16), txt, fill=(255, 255, 255), font=font)
            d.text((x0 + 14, y0 + 44), f"n={c['n']}", fill=(240, 240, 240), font=small)
            if c["ok"]:
                d.rectangle([x0 - 2, y0 - 2, x0 + cw + 2, y0 + ch + 2], outline=(20, 20, 20), width=3)
    d.text((left, img.height - 30), "实线框 = 接受率≥95% 且最差地面误差≤10cm（可靠）",
           fill=(60, 60, 60), font=small)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="calib_sweep.py",
        description="Sweep tripod positions through the automatic court calibration.",
        epilog="Writes tools/venue/calib_sweep.csv (+ heat-map PNG) and prints a Chinese summary.")
    ap.add_argument("--quick", action="store_true", help="small smoke sweep (6 cases)")
    ap.add_argument("--workers", type=int, default=4, help="parallel processes (max 4)")
    ap.add_argument("--scenes", type=int, default=3, help="random scenes per cell")
    ap.add_argument("--frames", type=int, default=5, help="frames rendered per scene")
    ap.add_argument("--csv", default=str(Path(__file__).resolve().parent / "calib_sweep.csv"))
    ap.add_argument("--heatmap", default=str(Path(__file__).resolve().parent / "calib_sweep.png"))
    ap.add_argument("--no-heatmap", action="store_true")
    ap.add_argument("--from-csv", default=None,
                    help="skip the sweep: rebuild the summary/heat-map from an existing CSV")
    args = ap.parse_args(argv)

    if args.from_csv:
        with open(args.from_csv, newline="", encoding="utf-8") as fh:
            rows = []
            for r in csv.DictReader(fh):
                r = dict(r)
                for k in ("case", "height_m", "dist_m", "lat_m", "roll_deg", "scene", "frames"):
                    if r.get(k) not in (None, ""):
                        r[k] = float(r[k]) if "." in str(r[k]) else int(r[k])
                for k in ("accepted",):
                    r[k] = str(r.get(k)).lower() in ("true", "1")
                for k in ("px_med", "px_max", "floor_med_m", "floor_max_m", "focal_rel",
                          "confidence", "coverage", "rmse_px", "explained_frac", "n_t", "n_l",
                          "n_absent", "n_lines", "n_hyp", "n_valid", "margin"):
                    v = r.get(k)
                    if v in (None, "", "None"):
                        r[k] = None
                    else:
                        try:
                            r[k] = float(v)
                        except ValueError:
                            r[k] = None
                rows.append(r)
        text = summary_text(rows)
        print(text)
        if not args.no_heatmap:
            write_heatmap(rows, Path(args.heatmap))
            print(f"热图: {args.heatmap}")
        Path(args.from_csv).with_name("calib_sweep_summary.txt").write_text(
            text + f"\n\nCSV: {args.from_csv}\n", encoding="utf-8")
        print("中文摘要: " + str(Path(args.from_csv).with_name("calib_sweep_summary.txt")))
        return 0

    cases = build_cases(args.scenes, args.frames, args.quick)
    print(f"标定范围扫描：{len(cases)} 个 case（{args.workers} 进程，"
          f"{args.scenes} 场景/格，{args.frames} 帧/场景）")
    print(f"  高度 {HEIGHTS} m，距近端底线 {DISTANCES} m，横向 {LATERALS} m，"
          f"roll {ROLLS}°，focal={FOCAL:.0f}px")
    t0 = time.time()
    rows = run_sweep(cases, args.workers, Path(args.csv), None if args.no_heatmap else Path(args.heatmap))
    text = summary_text(rows)
    print("\n" + text)
    print(f"\nCSV: {args.csv}")
    if not args.no_heatmap:
        print(f"热图: {args.heatmap}")
    print(f"总耗时 {time.time() - t0:.0f}s")
    summary_path = Path(args.csv).with_name("calib_sweep_summary.txt")
    summary_path.write_text(text + f"\n\nCSV: {args.csv}\n", encoding="utf-8")
    print(f"中文摘要: {summary_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VenueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
