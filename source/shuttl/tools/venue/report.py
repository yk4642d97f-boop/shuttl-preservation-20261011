#!/usr/bin/env python3
"""report.py — single self-contained HTML report (Chinese) for a pulled folder.

Usage:
  ./report.py <pulled dir> [more dirs] [-o report.html] [--open] [-h]

For every recording: duration/fps, phone vs Mac stage timings, shuttle visible
fraction, hits/rallies/camera, top speed, rally table, the calibration sheet and
4 overlay thumbnails — all images embedded as base64 JPEG. A summary table of all
recordings is at the top. Uses pull.py's index.json when present.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# run under backend/.venv/bin/python even when started with the python
_VENV = Path(__file__).resolve().parents[2] / "backend" / ".venv" / "bin" / "python"
if _VENV.exists() and Path(sys.executable).resolve() != _VENV.resolve():
    os.execv(str(_VENV), [str(_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

import argparse
import base64
import html
from datetime import datetime

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venue_common import (CALIB_SUFFIX, COMPARE_SUFFIX, MAC_SUFFIX, OVERLAY_SUFFIX,  # noqa: E402
                          VenueError, camera_info, compare_analyses, fmt_dur, hits_from_analysis,
                          load_json, open_capture, rally_rows, resize_keep, stage_seconds,
                          top_speed_kmh, video_props, visible_fraction)

VIDEO_EXT = (".mov", ".mp4", ".m4v")
REASON_ZH = {"in": "界内", "out": "出界", "net": "下网", "unknown": "未知"}
WINNER_ZH = {"near": "近端", "far": "远端", "unknown": "未知"}
SIDE_ZH = {"near": "近端", "far": "远端", "unknown": "未知"}
STAGE_ZH = {"probe": "读取视频", "detect": "羽毛球检测", "link": "轨迹连接", "calibrate": "场地标定",
            "players": "球员检测", "hits": "击球检测", "reconstruct3d": "三维重建",
            "rallies": "回合划分", "shots": "球种分类", "score": "计分"}
TYPE_ZH = {"serve": "发球", "smash": "杀球", "kill": "扑杀", "clear": "高远球", "drop": "吊球",
           "net": "网前球", "drive": "平抽", "lift": "挑球", "push": "推球", "block": "挡网",
           "unknown": "未知"}


def b64_jpeg(img: np.ndarray, max_w: int = 1300, quality: int = 80) -> str:
    img = resize_keep(img, max_w)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def read_frames_spread(path: Path, n: int = 4, max_w: int = 560) -> list[str]:
    """n evenly spread thumbnails (base64) from a video; [] when unreadable."""
    cap = open_capture(path)
    if not cap.isOpened():
        return []
    out = []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return []
        for frac in np.linspace(0.12, 0.88, n):
            idx = int(round(frac * (total - 1)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            out.append(b64_jpeg(resize_keep(frame, max_w), max_w, 76))
    finally:
        cap.release()
    return out


def find_files(video: Path) -> dict:
    mac = video.with_suffix(MAC_SUFFIX)
    return {
        "mac": mac if mac.is_file() else None,
        "compare": video.with_suffix(COMPARE_SUFFIX) if video.with_suffix(COMPARE_SUFFIX).is_file() else None,
        "calib": video.with_name(video.stem + CALIB_SUFFIX) if video.with_name(video.stem + CALIB_SUFFIX).is_file() else None,
        "overlay": video.with_name(video.stem + OVERLAY_SUFFIX) if video.with_name(video.stem + OVERLAY_SUFFIX).is_file() else None,
    }


def stats_card(ans: dict | None) -> dict:
    if not ans:
        return {"found": False}
    info = camera_info(ans)
    hits = hits_from_analysis(ans)
    rallies = rally_rows(ans)
    return {"found": True, "camera": info, "hits": len(hits), "rallies": len(rallies),
            "top_speed": top_speed_kmh(ans), "visible": visible_fraction(ans),
            "stages": stage_seconds(ans.get("diagnostics")),
            "processing": ans.get("processing_time_seconds"),
            "rallies_rows": rallies, "hits_rows": hits,
            "summary": ans.get("summary") or {}}


def load_pulled(root: Path) -> tuple[dict, list[dict]]:
    """(index or {}, recordings) — every recording dict has file/name/analysis/meta."""
    idx_path = root / "index.json"
    index = load_json(idx_path) if idx_path.is_file() else {}
    records = []
    if index.get("recordings"):
        for r in index["recordings"]:
            video = root / r["file"]
            rec = dict(r)
            rec["video_path"] = video
            rec["phone_analysis_path"] = (root / r["analysis"]) if r.get("analysis") else None
            records.append(rec)
    else:
        for v in sorted([p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXT]):
            try:
                props = video_props(v)
            except RuntimeError:
                props = {}
            records.append({"file": str(v.relative_to(root)), "name": v.name,
                            "video_path": v, "phone_analysis_path": None,
                            "duration": props.get("duration"), "fps": props.get("fps"),
                            "width": props.get("width"), "height": props.get("height"),
                            "frames": props.get("frames"), "analysis": None,
                            "duration_text": fmt_dur(props.get("duration"))})
    return index, records


def stage_table(pst: dict, mst: dict) -> str:
    names = sorted(set(pst) | set(mst), key=lambda k: (mst.get(k, {}).get("seconds", 0),
                                                       pst.get(k, {}).get("seconds", 0)))
    rows = []
    for n in names:
        p, m = pst.get(n, {}), mst.get(n, {})
        rows.append(
            f"<tr><td>{html.escape(STAGE_ZH.get(n, n))}<span class='dim'> {html.escape(n)}</span></td>"
            f"<td>{_sec(p.get('seconds'))}</td><td>{_sec(m.get('seconds'))}</td>"
            f"<td>{'✓' if m.get('ok', True) else '✗ ' + html.escape(str(m.get('error', ''))[:80])}</td></tr>")
    return "".join(rows)


def _sec(v) -> str:
    return f"{float(v):.1f}s" if v is not None else "—"


def _val(v, suffix: str = "", digits: int = 1, dash: str = "—") -> str:
    if v is None:
        return dash
    if isinstance(v, float):
        return f"{v:.{digits}f}{suffix}"
    return f"{v}{suffix}"


def rally_table(rows: list[dict], note: str) -> str:
    if not rows:
        return "<p class='dim'>（没有检测到回合）</p>"
    head = ("<tr><th>回合</th><th>起始帧</th><th>结束帧</th><th>击球数</th><th>结束原因</th>"
            "<th>得分方</th><th>判定置信</th><th>最快球速</th></tr>")
    body = []
    for r in rows:
        body.append(
            f"<tr><td>{r['index']}</td><td>{r['start']}</td><td>{r['end']}</td><td>{r['shots']}</td>"
            f"<td>{html.escape(REASON_ZH.get(r['end_reason'], r['end_reason']))}</td>"
            f"<td>{html.escape(WINNER_ZH.get(r['winner'], r['winner']))}</td>"
            f"<td>{_val(r['outcome_confidence'], '', 2)}</td>"
            f"<td>{_val(r['max_speed_kmh'], ' km/h', 0)}</td></tr>")
    return (f"<p class='dim'>{html.escape(note)}</p><table class='tbl'>{head}{''.join(body)}</table>")


def hits_table(hits: list[dict], limit: int = 40) -> str:
    if not hits:
        return "<p class='dim'>（没有检测到击球）</p>"
    head = ("<tr><th>#</th><th>帧</th><th>时间</th><th>击球方</th><th>球种</th>"
            "<th>出球速度</th><th>置信</th></tr>")
    body = []
    for k, h in enumerate(hits[:limit], 1):
        body.append(
            f"<tr><td>{k}</td><td>{h['frame']}</td><td>{_val(h['t'], 's', 2)}</td>"
            f"<td>{html.escape(SIDE_ZH.get(h['hitter'], h['hitter']))}</td>"
            f"<td>{html.escape(TYPE_ZH.get(h['shot_type'], h['shot_type']))}"
            f"<span class='dim'> {html.escape(h['shot_type'])}</span></td>"
            f"<td>{_val(h['speed_kmh'], ' km/h', 0)}</td>"
            f"<td>{_val(h['confidence'], '', 2)}</td></tr>")
    more = f"<p class='dim'>（仅显示前 {limit} 个，共 {len(hits)} 个）</p>" if len(hits) > limit else ""
    return f"<table class='tbl'>{head}{''.join(body)}</table>{more}"


def compare_block(cmp: dict | None) -> str:
    if not cmp:
        return "<p class='dim'>没有手机端分析，无法对比。</p>"
    h, r = cmp["hits"], cmp["rallies"]
    pc, mc = cmp["camera"]["phone"], cmp["camera"]["mac"]
    pv, mv = cmp["visible"]["phone"], cmp["visible"]["mac"]
    rows = [
        ("击球数", h["phone"], h["mac"]),
        (f"击球匹配（±{h['tol_frames']}帧）", f"{h['matched']} 个匹配", f"仅手机 {h['only_phone']} / 仅Mac {h['only_mac']}"),
        ("回合数", r["phone"], r["mac"]),
        (f"回合匹配（IoU≥{r['iou_threshold']}）", f"{r['matched']} 个匹配", f"仅手机 {r['only_phone']} / 仅Mac {r['only_mac']}"),
        ("相机标定", "有" if pc["found"] else "无", "有" if mc["found"] else "无"),
        ("标定置信度", _val(pc["confidence"], "", 2), _val(mc["confidence"], "", 2)),
        ("最快球速", _val(cmp["top_speed_kmh"]["phone"], " km/h", 0),
         _val(cmp["top_speed_kmh"]["mac"], " km/h", 0)),
        ("羽毛球有坐标占比", _val(pv["known_frac"] * 100, "%", 1), _val(mv["known_frac"] * 100, "%", 1)),
        ("羽毛球真检测占比", _val(pv["detected_frac"] * 100, "%", 1), _val(mv["detected_frac"] * 100, "%", 1)),
        ("处理耗时", _val(cmp["processing_time_seconds"]["phone"], "s", 1),
         _val(cmp["processing_time_seconds"]["mac"], "s", 1)),
    ]
    body = "".join(f"<tr><td>{html.escape(a)}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in rows)
    hits_detail = "".join(
        f"<li>手机帧 {p['phone_frame']} ↔ Mac帧 {p['mac_frame']} (差 {p['df']:+d}) "
        f"类型 {html.escape(str(p['phone_type']))} / {html.escape(str(p['mac_type']))}</li>"
        for p in h["pairs"][:20])
    detail = f"<details><summary>匹配上的击球明细（前20）</summary><ul>{hits_detail}</ul></details>" \
        if hits_detail else ""
    return ("<table class='tbl'><tr><th>指标</th><th>手机端</th><th>Mac 参考端</th></tr>"
            + body + "</table>" + detail)


def build_record(rec: dict) -> dict:
    video: Path = rec["video_path"]
    files = find_files(video)
    mac = load_json(files["mac"]) if files["mac"] else None
    phone = None
    if rec.get("phone_analysis_path") and Path(rec["phone_analysis_path"]).is_file():
        try:
            phone = load_json(rec["phone_analysis_path"])
        except Exception:                                               # noqa: BLE001
            phone = None
    cmp = load_json(files["compare"]) if files["compare"] else None
    if cmp is None and mac and phone:
        try:
            cmp = compare_analyses(phone, mac)
        except Exception:                                               # noqa: BLE001
            cmp = None
    props = video_props(video) if video.is_file() else {}
    overlay = files["overlay"]
    thumbs = read_frames_spread(overlay, 4) if overlay else []
    if not thumbs:
        thumbs = read_frames_spread(video, 4)
    calib_b64 = ""
    if files["calib"]:
        img = cv2.imread(str(files["calib"]))
        if img is not None:
            calib_b64 = b64_jpeg(img, 1500, 82)
    main = mac or phone
    return {"rec": rec, "props": props, "mac": mac, "phone": phone, "cmp": cmp,
            "mac_stats": stats_card(mac), "phone_stats": stats_card(phone),
            "overlay": overlay, "calib": files["calib"], "calib_b64": calib_b64,
            "thumbs": thumbs, "main": stats_card(main),
            "has_mac": mac is not None, "has_phone": phone is not None}


# --------------------------------------------------------------------------- html

CSS = """
body{font-family:-apple-system,'Hiragino Sans GB','PingFang SC',sans-serif;margin:0;background:#f4f5f7;color:#1c1e21}
header{background:#0f172a;color:#fff;padding:18px 26px}
header h1{margin:0 0 6px;font-size:22px}
header .sub{color:#94a3b8;font-size:13px}
main{padding:18px 26px 60px;max-width:1500px;margin:0 auto}
section{background:#fff;border-radius:10px;padding:16px 20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h2{font-size:19px;margin:4px 0 10px;border-left:5px solid #2563eb;padding-left:10px}
h3{font-size:15px;margin:16px 0 6px;color:#334155}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #e2e8f0;padding:5px 8px;text-align:left}
th{background:#f1f5f9;font-weight:600}
.tbl tr:nth-child(even) td{background:#fafbfc}
.dim{color:#64748b;font-size:12px}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
.card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;min-width:120px}
.card b{display:block;font-size:18px}
.card i{font-style:normal;color:#64748b;font-size:12px}
.ok{color:#15803d}.bad{color:#b91c1c}.warn{color:#b45309}
.thumbs{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.thumbs img{width:330px;border-radius:6px;border:1px solid #cbd5e1}
.calib{max-width:100%;border:1px solid #cbd5e1;border-radius:6px}
.legend{font-size:12.5px;color:#475569;background:#f8fafc;border:1px dashed #cbd5e1;padding:8px 12px;border-radius:8px}
a.top{font-size:12px}
details{margin-top:6px;font-size:13px}
"""


def render_html(index: dict, records: list[dict], root: Path) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    # summary table
    srows = []
    for k, r in enumerate(records):
        main = r["main"]
        cam = main.get("camera", {})
        cam_txt = ("<span class='ok'>成功 " + _val(cam.get('confidence'), '', 2) + "</span>"
                   if main.get("found") and cam.get("found") else
                   ("<span class='bad'>失败</span>" if main.get("found") else "<span class='dim'>无分析</span>"))
        p = r["props"]
        vis = main.get("visible") or {}
        vis_txt = _val(vis.get("known_frac") * 100, "%", 0) if vis else "—"
        srows.append(
            f"<tr><td><a href='#rec{k}'>{html.escape(r['rec']['name'])}</a></td>"
            f"<td>{fmt_dur(p.get('duration'))}</td><td>{_val(p.get('fps'), '', 1)}</td>"
            f"<td>{p.get('width')}×{p.get('height')}</td>"
            f"<td>{cam_txt}</td><td>{main.get('hits', '—')}</td><td>{main.get('rallies', '—')}</td>"
            f"<td>{_val(main.get('top_speed'), ' km/h', 0)}</td>"
            f"<td>{vis_txt}</td>"
            f"<td>{'✔' if r['has_phone'] else '—'}</td><td>{'✔' if r['has_mac'] else '—'}</td></tr>")
    summary = ("<table class='tbl'><tr><th>录像</th><th>时长</th><th>帧率</th><th>分辨率</th>"
               "<th>相机标定</th><th>击球</th><th>回合</th><th>最快球速</th><th>球可见</th>"
               "<th>手机分析</th><th>Mac分析</th></tr>" + "".join(srows) + "</table>")

    sections = []
    for k, r in enumerate(records):
        rec = r["rec"]
        p = r["props"]
        main = r["main"]
        cam = main.get("camera", {})
        ms = r["mac_stats"]
        ps = r["phone_stats"]
        cam_card = ("<span class='ok'>成功</span>" if cam.get("found") else
                    "<span class='bad'>失败</span>") if main.get("found") else "<span class='dim'>无分析</span>"
        cards = [
            ("时长", fmt_dur(p.get("duration")), f"{p.get('width')}×{p.get('height')} @ {_val(p.get('fps'), '', 1)}fps"),
            ("相机标定", cam_card, f"置信 {_val(cam.get('confidence'), '', 2)} · RMSE {_val(cam.get('rmse_px'), 'px', 2)}"),
            ("击球", str(main.get("hits", "—")), "检测到的击球点"),
            ("回合", str(main.get("rallies", "—")), "检测到的回合"),
            ("最快球速", _val(main.get("top_speed"), " km/h", 0), "来自三维轨迹"),
            ("球可见比例", _val((main.get("visible") or {}).get("known_frac", 0) * 100 if main.get("visible") else None, "%", 1),
             "有坐标的帧占比"),
        ]
        cards_html = "".join(f"<div class='card'><i>{html.escape(a)}</i><b>{b}</b><i>{c}</i></div>"
                             for a, b, c in cards)
        note = r["calib"].name if r["calib"] else ""
        imgs = "".join(f"<img src='{t}' alt='overlay frame'>" for t in r["thumbs"])
        thumbs_html = (f"<h3>叠加视频截图（{html.escape(Path(r['overlay']).name)}, 每帧都有 HUD/场地线/轨迹）</h3>"
                       f"<div class='thumbs'>{imgs}</div>") if imgs else \
            "<p class='dim'>没有叠加视频截图（先生成 overlay）</p>"
        calib_html = (f"<h3>标定检查图 <span class='dim'>{html.escape(note)}</span></h3>"
                      f"<img class='calib' src='{r['calib_b64']}' alt='calibration sheet'>") \
            if r["calib_b64"] else "<p class='dim'>没有标定检查图（先生成 calib_sheet）</p>"
        table_note = "以下是 Mac 参考端的结果。" if r["has_mac"] else \
            ("以下是手机端的分析结果（还没有 Mac 分析）。" if r["has_phone"] else "")
        sections.append(f"""
<section id='rec{k}'>
  <h2>{k + 1}. {html.escape(rec['name'])} <a class='top' href='#top'>↑顶部</a></h2>
  <div class='cards'>{cards_html}</div>
  <h3>分阶段耗时对比（秒）</h3>
  <table class='tbl'><tr><th>阶段</th><th>手机端</th><th>Mac 参考端</th><th>Mac状态</th></tr>
  {stage_table(ps.get('stages', {}), ms.get('stages', {}))}</table>
  <h3>手机 vs Mac 对比</h3>
  {compare_block(r['cmp'])}
  <h3>回合明细</h3>
  {rally_table(main.get('rallies_rows', []), table_note)}
  <h3>击球明细</h3>
  {hits_table(main.get('hits_rows', []))}
  {calib_html}
  {thumbs_html}
</section>""")

    return f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'>
<title>Shuttl 场地分析报告 {now}</title><style>{CSS}</style></head>
<body><a id='top'></a>
<header>
  <h1>Shuttl 现场分析报告</h1>
  <div class='sub'>生成时间 {now} · 目录 {html.escape(str(root))} · 录像 {len(records)} 个
   {(' · 手机拉取时间 ' + html.escape(str(index.get('created')))) if index.get('created') else ''}
   {(' · 录像↔分析配对方式 ' + html.escape(str(index.get('pairing_method')))) if index.get('pairing_method') else ''}</div>
</header>
<main>
<section>
  <h2>总览</h2>
  <div class='legend'>看什么：<b>相机标定</b>失败 ⇒ 球速/落点全部不可用，先看标定检查图的场地线是否贴合真实线条；
  <b>击球/回合匹配</b>数字越低，说明手机 App 与 Mac 参考差得越远；<b>球可见比例</b>低 ⇒ 检测器漏检多。</div>
  <p></p>
  {summary}
</section>
{''.join(sections)}
<section><h2>说明</h2>
<p class='dim'>手机端＝App 在 iPhone 上算出的结果（Documents/Analyses/*.json）；Mac 参考端＝用电脑上的
pipeline_v2 对同一段录像重新分析的结果。两者帧号都从视频第 0 帧开始，可直接比较。
叠加视频里：绿线=标定置信≥0.7 的场地线，橙线=置信偏低，红字 NO CAMERA=未标定；
黄圈=近端击球，洋红圈=远端击球，白点＋拖尾=羽毛球二维轨迹。</p>
</section>
</main></body></html>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="report.py",
        description="Build a self-contained Chinese HTML report for a pulled folder.",
        epilog="Default output: <pulled dir>/report.html")
    ap.add_argument("input", nargs="+", help="pulled folder(s) from pull.py (or a video file)")
    ap.add_argument("-o", "--out", default=None, help="output HTML (default <first input>/report.html)")
    ap.add_argument("--open", action="store_true", help="open the report in the browser")
    args = ap.parse_args(argv)

    roots = []
    for raw in args.input:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            raise VenueError(f"input not found: {p}")
        roots.append(p if p.is_dir() else p.parent)
    root = roots[0]
    index, records = load_pulled(root)
    extra = []
    for r in roots[1:]:
        _, recs = load_pulled(r)
        for rec in recs:
            rec["name"] = f"{r.name}/{rec['name']}"
            extra.append(rec)
    records.extend(extra)
    if not records:
        raise VenueError(f"no recordings found in {root} (run pull.py first)")
    built = []
    for rec in records:
        print(f"  读取 {rec['name']} …")
        built.append(build_record(rec))
    html_doc = render_html(index, built, root)
    out = Path(args.out) if args.out else root / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"报告: {out}  ({out.stat().st_size / 1e6:.2f}MB, {len(built)} 个录像)")
    for r in built:
        c = r["cmp"]
        extra_txt = ""
        if c:
            extra_txt = (f"  击球匹配 {c['hits']['matched']}/{c['hits']['phone']}"
                         f"  回合匹配 {c['rallies']['matched']}/{c['rallies']['phone']}")
        print(f"  - {r['rec']['name']}: 相机={r['main'].get('camera', {}).get('confidence')}"
              f" 击球={r['main'].get('hits')} 回合={r['main'].get('rallies')}"
              f" 最快={r['main'].get('top_speed')}{extra_txt}")
    if args.open:
        import subprocess
        subprocess.Popen(["open", str(out)])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VenueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
