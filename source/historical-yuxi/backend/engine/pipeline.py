"""
羽析 · 分析管线: 视频 + 场地四角 => 完整分析报告 (JSON)

    追踪羽毛球 (TrackNetV3)  ->  候选击球/回合切分  ->  球员检测 (YOLOX)
        ->  击球验证 + 击球方 HMM  ->  落点判定  ->  统计汇总

命令行用法 (开发调试):
    python -m engine.pipeline 视频.mp4 --corners "x1,y1,x2,y2,x3,y3,x4,y4" --out result.json
"""
from __future__ import annotations

import json
import time
from typing import Callable, List, Optional

from .analysis import RallyAnalyzer
from .court import Court
from .players import PlayerDetector
from .tracker import ShuttleTracker

_tracker: Optional[ShuttleTracker] = None


def get_tracker() -> ShuttleTracker:
    """模型只加载一次 (约 150MB), 后续分析复用。"""
    global _tracker
    if _tracker is None:
        _tracker = ShuttleTracker()
    return _tracker


def analyze_video(video_path: str, corners: List[List[float]], match_type: str = "singles",
                  mode: str = "accurate", progress: Optional[Callable[[str, float], None]] = None,
                  track_cache: Optional[dict] = None) -> dict:
    """
    corners: 画面上双打外边线四角 [[x,y] * 4], 顺序任意 (会自动整理)
    match_type: singles 单打 / doubles 双打
    mode: accurate 精确 / fast 快速
    progress(stage: str, ratio: 0~1)
    track_cache: 已有的追踪结果 (改标定后重新分析时跳过最耗时的追踪)
    """
    t0 = time.time()
    p = progress or (lambda s, r: None)
    court = Court.from_corners(corners)

    if track_cache is None:
        tracker = get_tracker()
        # 追踪占总进度的 0 ~ 80%
        tr = tracker.track(video_path, mode=mode, progress=lambda s, r: p(s, r * 0.8))
        track = tr.to_dict()
    else:
        track = track_cache
    t_track = time.time() - t0

    p("识别球员", 0.82)
    det = PlayerDetector(court)
    analyzer = RallyAnalyzer(track, court, match_type)
    result = analyzer.run(player_fn=lambda frames: det.detect_frames(
        video_path, frames, progress=lambda r: p("识别球员", 0.82 + 0.15 * r)))

    p("生成报告", 0.98)
    result["video"] = {"width": track["width"], "height": track["height"], "fps": track["fps"],
                       "num_frames": track["num_frames"],
                       "duration": round(track["num_frames"] / (track["fps"] or 30), 2)}
    result["court"] = {"corners_px": court.corners_px.round(1).tolist(),
                       "lines_px": court.court_lines_px()}
    result["meta"] = {"mode": mode, "device": str(get_tracker().device) if track_cache is None else None,
                      "time_track_s": round(t_track, 1), "time_total_s": round(time.time() - t0, 1),
                      "engine": "羽析 v0.1 · TrackNetV3 + YOLOX"}
    result["track_raw"] = track
    p("完成", 1.0)
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="羽析 · 羽毛球视频分析")
    ap.add_argument("video")
    ap.add_argument("--corners", required=True, help="四角像素坐标 x1,y1,x2,y2,x3,y3,x4,y4")
    ap.add_argument("--match", default="singles", choices=["singles", "doubles"])
    ap.add_argument("--mode", default="accurate", choices=["accurate", "fast"])
    ap.add_argument("--out", default="result.json")
    a = ap.parse_args()
    v = [float(t) for t in a.corners.split(",")]
    cs = [[v[i], v[i + 1]] for i in range(0, 8, 2)]
    res = analyze_video(a.video, cs, a.match, a.mode,
                        progress=lambda s, r: print(f"\r[{r * 100:5.1f}%] {s}      ", end="", flush=True))
    print()
    json.dump(res, open(a.out, "w"), ensure_ascii=False)
    s = res["summary"]
    print(f"回合 {s['num_rallies']}  总拍数 {s['total_shots']}  比分 近端 {s['points']['near']} : 远端 {s['points']['far']}")
    print(f"耗时 {res['meta']['time_total_s']}s  -> {a.out}")
