#!/usr/bin/env python3
"""analyze.py — run the Mac reference pipeline and compare it with the phone's own analysis.

Usage:
  ./analyze.py <pulled dir | video file> [more ...] [-h] [--force] [--max-seconds N]
               [--limit N] [--verbose] [--no-copy]

For every video it writes `<stem>.mac_analysis.json` next to the video and
`<stem>.compare.json` with the phone-vs-Mac comparison (hits ±3 frames, rallies
IoU ≥ 0.5, camera + confidence, top speed, per-stage seconds).

--max-seconds N analyses only the first N seconds (a temporary trimmed copy is
analysed, so frame numbers still match the original video).
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
import logging
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venue_common import (COMPARE_SUFFIX, DATA_DIR, MAC_SUFFIX, VenueError,  # noqa: E402
                          add_backend, camera_info, compare_analyses, iter_video_frames,
                          load_json, open_writer, save_json, stage_seconds, top_speed_kmh,
                          video_props, visible_fraction)

add_backend()

VIDEO_EXT = (".mov", ".mp4", ".m4v")


# --------------------------------------------------------------------------- helpers

def find_index_root(video: Path) -> tuple[Path | None, dict | None]:
    """Walk up from the video to a pulled folder that has index.json."""
    for parent in [video.parent, *video.parents[:4]]:
        idx = parent / "index.json"
        if idx.is_file():
            try:
                return parent, load_json(idx)
            except Exception:                                       # noqa: BLE001
                return parent, None
    return None, None


def record_for(index: dict | None, root: Path | None, video: Path) -> dict | None:
    if not index or not root:
        return None
    try:
        rel = str(video.resolve().relative_to(root.resolve()))
    except ValueError:
        return None
    for r in index.get("recordings", []):
        if r.get("file") == rel:
            return r
    return None


def _meta_ok(video_meta: dict, am: dict) -> bool:
    for k, tol in (("width", 0), ("height", 0)):
        if am.get(k) and video_meta.get(k) and int(am[k]) != int(video_meta[k]):
            return False
    if am.get("fps") and video_meta.get("fps") \
            and abs(float(am["fps"]) - float(video_meta["fps"])) > 0.6:
        return False
    if am.get("frames") and video_meta.get("frames"):
        return abs(float(am["frames"]) - float(video_meta["frames"])) <= \
            max(3.0, 0.02 * float(video_meta["frames"]))
    return True


def find_phone_analysis(video: Path, index: dict | None, root: Path | None,
                        vmeta: dict) -> tuple[Path | None, str]:
    rec = record_for(index, root, video)
    if rec and rec.get("analysis") and root:
        p = root / rec["analysis"]
        if p.is_file():
            return p, "index.json"
    cands: list[Path] = [video.with_suffix(".json")]
    for d in (video.parent / "Analyses", video.parent.parent / "Analyses",
              video.parent / ".." / "Analyses"):
        if d.is_dir():
            cands.extend(sorted(d.glob("*.json")))
    seen = set()
    for c in cands:
        c = c.resolve()
        if c in seen or not c.is_file() or c.name.endswith(MAC_SUFFIX):
            continue
        seen.add(c)
        try:
            ans = load_json(c)
        except Exception:                                           # noqa: BLE001
            continue
        if not isinstance(ans, dict) or "rallies" not in ans:
            continue                          # not a Shuttl analysis file
        v = ans.get("video") or {}
        if _meta_ok(vmeta, v):
            return c, "metadata"
    return None, ""


def collect_videos(inputs: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser()
        if not p.exists():
            raise VenueError(f"input not found: {p}")
        if p.is_dir():
            vids = sorted([q for q in p.rglob("*") if q.suffix.lower() in VIDEO_EXT
                           and not _is_own_output(q)])
            out.extend(vids)
        else:
            if p.suffix.lower() not in VIDEO_EXT:
                raise VenueError(f"not a video file: {p}")
            out.append(p)
    return out


def _is_own_output(path: Path) -> bool:
    """Our own diagnostic videos / temp trims / hidden files are not phone recordings."""
    name = path.name
    if path.stem.endswith("_overlay") or name.startswith("."):
        return True
    return ".tmp" in path.parts


class _Progress:
    def __init__(self, name: str):
        self.name = name
        self.t0 = time.time()
        self.stage = None
        self.last = -1.0
        self.last_t = 0.0

    def __call__(self, pct: float, stage: str) -> None:
        now = time.time()
        if stage == self.stage and pct - self.last < 1.0 and now - self.last_t < 1.0:
            return
        if stage != self.stage:
            self.stage = stage
            sys.stdout.write("\n")
        self.last, self.last_t = pct, now
        end = "\n" if not sys.stdout.isatty() else ""
        sys.stdout.write(f"\r  [{pct:5.1f}%] {stage:<14s} {now - self.t0:6.0f}s {end}")
        sys.stdout.flush()

    def done(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


def trim_video(src: Path, dst: Path, seconds: float) -> Path:
    props = video_props(src)
    fps = float(props["fps"] or 30.0)
    size = (int(props["width"]), int(props["height"]))
    dst.parent.mkdir(parents=True, exist_ok=True)
    writer, cc = open_writer(dst, fps, size)
    stop = max(1, int(round(seconds * fps)))
    n = 0
    try:
        for _i, frame in iter_video_frames(src, stop=stop):
            if frame.shape[1] != size[0] or frame.shape[0] != size[1]:
                import cv2
                frame = cv2.resize(frame, size)
            writer.write(frame)
            n += 1
    finally:
        writer.release()
    if n == 0:
        raise VenueError(f"could not trim any frame from {src}")
    print(f"  --max-seconds {seconds:g}s → 临时片段 {n} 帧 ({cc}) {dst.name}")
    return dst


# --------------------------------------------------------------------------- one video

def analyze_one(video: Path, args, index: dict | None, root: Path | None) -> dict:
    from app.services.tracking import pipeline_v2, serialize

    mac_path = video.with_suffix(MAC_SUFFIX)
    cmp_path = video.with_suffix(COMPARE_SUFFIX)
    if mac_path.exists() and not args.force:
        print(f"\n跳过 {video.name}（已有 {mac_path.name}，用 --force 重算）")
        out_skip = {"video": str(video), "skipped": True, "mac_analysis": str(mac_path)}
        try:
            vmeta0 = video_props(video)
            if not cmp_path.exists():
                phone_path, how = find_phone_analysis(video, index, root, vmeta0)
                if phone_path:
                    cmp = compare_analyses(load_json(phone_path), load_json(mac_path))
                    cmp["phone_analysis"] = str(phone_path)
                    cmp["matched_by"] = how
                    save_json(cmp_path, cmp)
                    out_skip["compare"] = str(cmp_path)
                    print(f"  （补上了 {cmp_path.name}）")
                    _print_compare(cmp)
        except Exception as exc:                                    # noqa: BLE001
            print(f"  警告：跳过时无法生成对比：{type(exc).__name__}: {exc}")
        return out_skip
    try:
        vmeta = video_props(video)
    except RuntimeError as exc:
        raise VenueError(str(exc)) from exc

    print(f"\n分析 {video.name}  {vmeta['width']}x{vmeta['height']} "
          f"{vmeta['fps']:.2f}fps {vmeta['frames']}帧 {vmeta['duration']:.1f}s")
    src = video
    tmp_dir = None
    if args.max_seconds:
        tmp_dir = DATA_DIR / ".tmp"
        src = trim_video(video, tmp_dir / f"{video.stem}_first{int(args.max_seconds)}s.mp4",
                         args.max_seconds)
    prog = _Progress(video.name)
    t0 = time.time()
    try:
        opts = pipeline_v2.PipelineOptions(device=args.device) if args.device else None
        res = pipeline_v2.analyze_video(str(src), opts, progress=prog)
    finally:
        prog.done()
    if tmp_dir is not None:
        try:
            Path(src).unlink()
        except OSError:
            pass
    wall = time.time() - t0
    analysis = serialize.to_dict(res)
    if analysis.get("camera") is None and not args.no_explain:
        diag = explain_calibration(src, analysis)          # why did it fail? (Chinese report)
        if diag:
            analysis["diagnostics"]["calibration_attempt"] = diag
    save_json(mac_path, analysis)
    print(f"  完成 {wall:.0f}s（pipeline 自报 {res.processing_time_seconds:.0f}s）"
          f" → {mac_path.name}")
    diag = analysis.get("diagnostics") or {}
    st = stage_seconds(diag)
    print("  阶段耗时: " + ", ".join(f"{k}={v['seconds']:.1f}s" for k, v in st.items()))
    print(f"  相机: {'有' if camera_info(analysis)['found'] else '无'}"
          f" (confidence={camera_info(analysis)['confidence']})"
          f"  击球={len([s for r in analysis.get('rallies') or [] for s in r.get('shots') or []])}"
          f"  回合={len(analysis.get('rallies') or [])}"
          f"  最快={top_speed_kmh(analysis)}km/h")
    vis = visible_fraction(analysis)
    print(f"  羽毛球可见: 有坐标 {vis['known_frac'] * 100:.1f}% / 真检测 {vis['detected_frac'] * 100:.1f}%")

    out: dict = {"video": str(video), "skipped": False, "mac_analysis": str(mac_path),
                 "wall_seconds": round(wall, 1), "video_props": vmeta,
                 "analyzed_seconds": args.max_seconds}
    phone_path, how = find_phone_analysis(video, index, root, vmeta)
    if phone_path:
        phone = load_json(phone_path)
        cmp = compare_analyses(phone, analysis)
        cmp["phone_analysis"] = str(phone_path)
        cmp["matched_by"] = how
        save_json(cmp_path, cmp)
        out["compare"] = str(cmp_path)
        out["phone_analysis"] = str(phone_path)
        _print_compare(cmp)
    else:
        print("  手机端分析: 未找到（只保存 Mac 结果）")
    return out


def explain_calibration(src: Path, analysis: dict) -> dict:
    """Re-run the automatic calibration with diagnostics to record WHY it failed.

    pipeline_v2 does not pass a diagnostics dict, so a failed calibration leaves
    nothing to explain in the JSON. This is the single most useful diagnostic on
    real footage, so it is repeated here (same frames the pipeline uses) and the
    stats are stored under diagnostics['calibration_attempt'].
    """
    try:
        from app.services.tracking import court_calibration, video_io
        v = analysis.get("video") or {}
        n = int(v.get("frames") or 0)
        size = (int(v.get("width") or 0), int(v.get("height") or 0))
        frames = [f for _, f in video_io.sample_frames(str(src), 24, n)]
        if not frames:
            return {}
        diag: dict = {}
        court_calibration.calibrate_from_frames(frames, size, diagnostics=diag)
        return {k: val for k, val in diag.items() if k != "candidates"}
    except Exception as exc:                                            # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _print_compare(cmp: dict) -> None:
    h, r = cmp["hits"], cmp["rallies"]
    print(f"  ── 手机 vs Mac ──")
    print(f"  击球(±{h['tol_frames']}帧): 手机 {h['phone']}, Mac {h['mac']}, "
          f"匹配 {h['matched']}, 仅手机 {h['only_phone']}, 仅Mac {h['only_mac']}")
    print(f"  回合(IoU≥{r['iou_threshold']}): 手机 {r['phone']}, Mac {r['mac']}, "
          f"匹配 {r['matched']}, 仅手机 {r['only_phone']}, 仅Mac {r['only_mac']}")
    pc, mc = cmp["camera"]["phone"], cmp["camera"]["mac"]
    print(f"  相机: 手机 {'有' if pc['found'] else '无'}({pc['confidence']}) / "
          f"Mac {'有' if mc['found'] else '无'}({mc['confidence']})")
    print(f"  最快球速: 手机 {cmp['top_speed_kmh']['phone']} / Mac {cmp['top_speed_kmh']['mac']} km/h")
    for side in ("phone", "mac"):
        st = cmp["stages_seconds"][side] or {}
        if st:
            print(f"  {side} 阶段: " + ", ".join(f"{k}={v['seconds']:.1f}s" for k, v in st.items()))


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="analyze.py",
        description="Run the Mac pipeline on pulled phone recordings and compare with the phone.",
        epilog="Writes <stem>.mac_analysis.json and <stem>.compare.json next to each video.")
    ap.add_argument("input", nargs="+", help="pulled folder (from pull.py) or video file(s)")
    ap.add_argument("--force", action="store_true", help="re-analyse even if mac_analysis.json exists")
    ap.add_argument("--max-seconds", type=float, default=None,
                    help="analyse only the first N seconds of each video")
    ap.add_argument("--limit", type=int, default=None, help="analyse at most N videos")
    ap.add_argument("--device", default=None,
                    help="torch device for pose/players: 'cpu', 'mps' or 'cuda' (default: auto)")
    ap.add_argument("--no-explain", action="store_true",
                    help="do not re-run calibration to record the failure reason")
    ap.add_argument("--verbose", action="store_true", help="show pipeline INFO logs")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    videos = collect_videos(args.input)
    if args.limit:
        videos = videos[:args.limit]
    if not videos:
        print("错误：没有找到任何视频文件 (.mov/.mp4)。", file=sys.stderr)
        return 1
    progs = f"前 {args.max_seconds:.0f} 秒" if args.max_seconds else "完整"
    print(f"共 {len(videos)} 个视频，{progs}分析"
          + (f"（device={args.device}）" if args.device else ""))
    results = []
    for i, video in enumerate(videos, 1):
        print(f"\n=== [{i}/{len(videos)}] {video} ===")
        try:
            root, index = find_index_root(video)
            results.append(analyze_one(video, args, index, root))
        except VenueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            results.append({"video": str(video), "error": str(exc)})
        except KeyboardInterrupt:
            print("\n中断（已经完成的视频保留结果）", file=sys.stderr)
            break
    print("\n===== 汇总 =====")
    for r in results:
        if r.get("error"):
            print(f"  失败 {Path(r['video']).name}: {r['error']}")
        elif r.get("skipped"):
            print(f"  跳过 {Path(r['video']).name}")
        else:
            c = r.get("compare")
            extra = ""
            if c:
                cmp = load_json(c)
                extra = (f"  击球匹配 {cmp['hits']['matched']}/{cmp['hits']['phone']}，"
                         f"回合匹配 {cmp['rallies']['matched']}/{cmp['rallies']['phone']}")
            print(f"  完成 {Path(r['video']).name}  {r.get('wall_seconds')}s{extra}")
    return 1 if all(r.get("error") for r in results) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VenueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
