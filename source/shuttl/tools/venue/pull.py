#!/usr/bin/env python3
"""pull.py — copy the Shuttl iPhone's recordings + analyses (read-only) to tools/venue/data/<ts>/.

Usage:
  ./pull.py [-h] [--dest DIR] [--device ID] [--list-only] [--bulk]
            [--no-library] [--analyses-only] [--timeout S] [--force-copy]

Never deletes or changes anything on the phone: it only runs
`xcrun devicectl device info files` (list) and `... device copy from` (copy).

Why per-file copies by default: `devicectl`'s recursive directory copy fails
with a socket timeout on iOS 26 / iPhone 16 Pro here, while single-file copies
work. --bulk tries the directory copy first (fast when it works).

Writes <dest>/index.json: every recording (file, duration, fps, resolution,
size), which recordings have an on-device analysis, and how the two were paired
(SwiftData store first, else video metadata).

Phone: 0F92DDA9-7A87-4F05-8368-0E834177D8F3   app: com.ycyangcong.shuttl
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
import re
import shutil
import sqlite3
import time
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from venue_common import (BUNDLE_ID, DATA_DIR, PHONE_DEVICE, VenueError, fmt_dur,  # noqa: E402
                          load_json, run, save_json, video_props)

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
META_KEYS = ("fps", "width", "height", "frames")
WANT_PREFIXES = ("Documents/Matches/", "Documents/Analyses/", "Documents/", "Library/Application Support/")
VIDEO_EXT = (".mov", ".mp4", ".m4v")


# --------------------------------------------------------------------------- devicectl

def _ensure_dir(path: Path) -> None:
    """mkdir -p that also replaces a stray file left by a failed devicectl copy."""
    if path.exists() and not path.is_dir():
        path.unlink()
    path.mkdir(parents=True, exist_ok=True)


def devicectl_copy(device: str, source: str, destination: Path, timeout: float) -> tuple[bool, str]:
    _ensure_dir(destination.parent)
    if destination.exists() and not destination.is_dir():
        destination.unlink()          # a failed copy can leave an empty file behind
    cmd = ["xcrun", "devicectl", "device", "copy", "from",
           "--device", device,
           "--domain-type", "appDataContainer",
           "--domain-identifier", BUNDLE_ID,
           "--source", source,
           "--destination", str(destination),
           "--timeout", f"{int(timeout)}"]
    rc, out = run(cmd, timeout=timeout + 60)
    if rc != 0 and destination.exists() and destination.is_dir():
        got = any(destination.rglob("*"))
        if got:
            return True, f"partial ({rc}): {out.strip().splitlines()[-1] if out.strip() else ''}"
    return rc == 0, out.strip()


def device_present(device: str) -> tuple[bool, str]:
    """True when `device` is listed and available (connected + paired)."""
    rc, out = run(["xcrun", "devicectl", "list", "devices"], timeout=60)
    if rc != 0:
        return False, out.strip()
    for line in out.splitlines():
        if device.lower() not in line.lower():
            continue
        if any(s in line for s in ("available", "connected", "paired")):
            return True, line.strip()
        return False, line.strip()
    return False, ("设备未出现在 `xcrun devicectl list devices` 中："
                   + (out.strip().splitlines()[-1] if out.strip() else "no output"))


def lock_state(device: str) -> str:
    rc, out = run(["xcrun", "devicectl", "device", "info", "lockState", "--device", device],
                  timeout=60)
    if rc != 0:
        return "unknown"
    for line in out.splitlines():
        if "passcodeRequired" in line or "unlockedSinceBoot" in line:
            return line.strip(" •")
    return "unknown"


def list_container_files(device: str, timeout: float = 120.0) -> list[str]:
    """Every file path in the app data container (relative, '/' separated)."""
    rc, out = run(["xcrun", "devicectl", "device", "info", "files",
                   "--device", device,
                   "--domain-type", "appDataContainer",
                   "--domain-identifier", BUNDLE_ID], timeout=timeout)
    if rc != 0:
        raise VenueError("无法列出手机文件（devicectl device info files 失败）：\n"
                         + out.strip()[-500:])
    files = []
    for line in out.splitlines():
        s = line.strip()
        if not s or " " in s[:1]:
            continue
        if s.startswith(("Documents/", "Library/Application Support/")):
            files.append(s)
    return files


def copy_container_files(device: str, files: list[str], dest: Path, timeout: float,
                         force: bool = False, quiet: bool = False) -> dict:
    """Copy single files (devicectl's directory copy is unreliable); returns a report."""
    ok, failed, skipped = [], [], []
    t0 = time.time()
    for i, rel in enumerate(files, 1):
        dst = dest / rel
        if dst.is_file() and dst.stat().st_size > 0 and not force:
            skipped.append(rel)
            continue
        _ensure_dir(dst.parent)
        rc, out = run(["xcrun", "devicectl", "device", "copy", "from",
                       "--device", device,
                       "--domain-type", "appDataContainer",
                       "--domain-identifier", BUNDLE_ID,
                       "--source", rel, "--destination", str(dst),
                       "--timeout", f"{int(timeout)}"], timeout=timeout + 60)
        if rc == 0 and dst.is_file():
            ok.append(rel)
            if not quiet:
                print(f"  [{i}/{len(files)}] {rel}  {dst.stat().st_size / 1e6:.1f}MB "
                      f"({time.time() - t0:.0f}s)")
        else:
            if dst.exists() and dst.is_file() and dst.stat().st_size == 0:
                dst.unlink()
            failed.append(rel)
            if not quiet:
                print(f"  [{i}/{len(files)}] 失败 {rel}: "
                      f"{out.strip().splitlines()[-1] if out.strip() else rc}")
    return {"copied": ok, "failed": failed, "skipped_existing": skipped,
            "seconds": round(time.time() - t0, 1)}


def flatten_double_nesting(root: Path) -> None:
    """devicectl sometimes copies Documents into <dest>/Documents/Documents."""
    for _ in range(3):
        doubles = list(root.glob("**/Documents/Documents"))
        if not doubles:
            break
        for d in doubles:
            inner = d
            for item in list(inner.iterdir()):
                target = inner.parent / item.name
                if target.exists():
                    continue
                shutil.move(str(item), str(target))
            try:
                inner.rmdir()
            except OSError:
                pass


# --------------------------------------------------------------------------- pairing

def analysis_meta_fast(path: Path) -> dict:
    """(fps, w, h, frames) from an analysis JSON — tolerant of big/odd files."""
    try:
        ans = load_json(path)
        v = ans.get("video") or {}
        return {k: v.get(k) for k in META_KEYS}
    except Exception:
        pass
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:400_000]
        v = {}
        for k in META_KEYS:
            m = re.search(rf'"{k}"\s*:\s*(-?\d+(?:\.\d+)?)', head)
            if m:
                v[k] = float(m.group(1))
        return v
    except Exception:
        return {}


def swiftdata_map(library_dir: Path, analysis_names: list[str]) -> dict[str, str]:
    """Best-effort read-only map {video filename: analysis uuid} from the SwiftData store.

    Generic: scan every table for a row that holds both a '.mov' string and a uuid
    that names an existing analysis file; also try a 1-hop join over Z_PK/foreign keys.
    """
    stores = [p for p in library_dir.rglob("*.store")] if library_dir.exists() else []
    if not stores:
        return {}
    by_name = {Path(n).stem.lower(): n for n in analysis_names}
    uuids = set(by_name)
    rows_by_table: dict[str, list[dict]] = {}
    for store in stores:
        try:
            con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            tables = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table'")]
            for t in tables:
                try:
                    cur = con.execute(f'select * from "{t}" limit 20000')
                    cols = [d[0] for d in cur.description]
                except sqlite3.Error:
                    continue
                rows_by_table[t] = [{c: v for c, v in zip(cols, row)} for row in cur.fetchall()]
        except sqlite3.Error:
            continue
        finally:
            con.close()
    if not rows_by_table:
        return {}
    index: dict[tuple[str, int], dict] = {}          # (table, Z_PK) -> row
    for t, rows in rows_by_table.items():
        for r in rows:
            pk = r.get("Z_PK")
            if pk is not None:
                index[(t, int(pk))] = r

    def text_values(row: dict) -> list[str]:
        return [str(v) for v in row.values() if isinstance(v, (str, bytes)) and v]

    def uuids_in(row: dict) -> list[str]:
        out = []
        for s in text_values(row):
            for u in UUID_RE.findall(s):
                if u.lower() in uuids:
                    out.append(u.lower())
        return out

    mapping: dict[str, str] = {}
    unresolved: list[dict] = []
    for t, rows in rows_by_table.items():
        for r in rows:
            movs = [s for s in text_values(r) if s.lower().endswith((".mov", ".mp4"))]
            if not movs:
                continue
            us = uuids_in(r)
            if us:
                for m in movs:
                    mapping[Path(m).name] = by_name[us[0]]
            else:
                unresolved.append({"table": t, "row": r})
    # 1-hop join: a row with a .mov pointing at another table's Z_PK that has the uuid
    for item in unresolved:
        t, r = item["table"], item["row"]
        for k, v in r.items():
            if not (isinstance(v, int) and v > 0 and k.upper() != "Z_PK"):
                continue
            for t2 in rows_by_table:
                if t2 == t:
                    continue
                target = index.get((t2, int(v)))
                if not target:
                    continue
                us = uuids_in(target)
                if us:
                    for s in text_values(r):
                        if s.lower().endswith((".mov", ".mp4")):
                            mapping[Path(s).name] = by_name[us[0]]
    return mapping


def metadata_map(videos: dict[str, dict], analyses: dict[str, dict]) -> tuple[dict[str, str], list[str]]:
    """Pair videos to analyses by (width, height, fps close, frames close)."""
    notes: list[str] = []
    pairs: dict[str, str] = {}
    used: set[str] = set()
    for vname, vp in videos.items():
        best, best_cost = None, None
        for aname, am in analyses.items():
            if aname in used:
                continue
            if am.get("width") and vp.get("width") and int(am["width"]) != int(vp["width"]):
                continue
            if am.get("height") and vp.get("height") and int(am["height"]) != int(vp["height"]):
                continue
            if am.get("fps") and vp.get("fps") and abs(float(am["fps"]) - float(vp["fps"])) > 0.6:
                continue
            df = abs(float(am.get("frames") or 0) - float(vp.get("frames") or 0))
            cost = df / max(float(vp.get("frames") or 1), 1.0)
            if best is None or cost < best_cost:
                best, best_cost = aname, cost
        if best is not None and best_cost is not None and best_cost < 0.02:
            pairs[vname] = best
            used.add(best)
            notes.append(f"{vname} <-> {Path(best).name} (frames diff {best_cost * 100:.2f}%)")
    return pairs, notes


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pull.py",
        description="Copy the Shuttl iPhone recordings/analyses (read-only) and index them.",
        epilog="The phone must be connected, unlocked and trusted. Nothing on the phone is modified.")
    ap.add_argument("--dest", help="target folder (default tools/venue/data/<YYYYMMDD-HHMMSS>)")
    ap.add_argument("--device", default=PHONE_DEVICE, help="CoreDevice id (default %(default)s)")
    ap.add_argument("--list-only", action="store_true", help="only list the phone's files")
    ap.add_argument("--bulk", action="store_true", help="try devicectl's directory copy first")
    ap.add_argument("--analyses-only", action="store_true", help="copy only Documents/Analyses")
    ap.add_argument("--no-library", action="store_true", help="skip Library/Application Support")
    ap.add_argument("--force-copy", action="store_true", help="re-copy files already on disk")
    ap.add_argument("--timeout", type=float, default=1800.0, help="per-copy timeout seconds")
    args = ap.parse_args(argv)

    ok_phone, info = device_present(args.device)
    if not ok_phone:
        print(f"错误：找不到/无法连接手机 ({args.device})。请连接数据线、解锁手机后再运行。\n"
              f"device not reachable.\n{info}", file=sys.stderr)
        return 1
    print(f"手机连接正常：{info}")
    locked = "passcodeRequired: true" in lock_state(args.device)
    print(f"锁屏状态：{'已锁屏（需要解锁手机才能复制文件）' if locked else '未锁屏'}")

    try:
        remote = list_container_files(args.device)
    except VenueError as exc:
        print(f"错误：{exc}\n提示：手机必须解锁，并在手机上点过“信任此电脑”。", file=sys.stderr)
        remote = []
    videos_remote = [f for f in remote if f.lower().endswith(VIDEO_EXT)]
    analyses_remote = [f for f in remote if f.startswith("Documents/Analyses/") and f.endswith(".json")]
    print(f"手机上有 {len(remote)} 个文件：录像 {len(videos_remote)} 个，"
          f"分析 {len(analyses_remote)} 个，"
          f"SwiftData store {'有' if any('.store' in f for f in remote) else '无'}")
    for f in videos_remote:
        print(f"  {f}")
    if args.list_only:
        return 0

    if args.dest:
        dest = Path(args.dest).expanduser().resolve()
    else:
        dest = DATA_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)

    copies: dict[str, dict] = {}
    if args.bulk:
        print("尝试整体复制 Documents（--bulk）…")
        t0 = time.time()
        ok, out = devicectl_copy(args.device, "Documents", dest / "Documents", args.timeout)
        copies["Documents"] = {"ok": ok, "seconds": round(time.time() - t0, 1), "detail": out[-400:]}
        print(f"  Documents: {'OK' if ok else '失败，改用逐个文件复制'}")
        if not ok:
            print(f"  {out[-300:]}", file=sys.stderr)

    want = []
    for f in remote:
        if f.startswith("Documents/Analyses/"):
            want.append(f)
        elif not args.analyses_only and f.lower().endswith(VIDEO_EXT):
            want.append(f)
        elif not args.analyses_only and not args.no_library \
                and f.startswith("Library/Application Support/") and ".store" in f:
            want.append(f)
    if not args.bulk:
        print(f"逐个文件复制 {len(want)} 个文件（只读）…")
    elif want:
        print(f"继续逐个复制缺失的 {len(want)} 个文件（已存在的跳过）…")
    if want:
        if locked:
            print("注意：手机处于锁屏状态，devicectl 很可能无法复制文件；"
                  "请在手机上解锁（点亮屏幕输入密码）后重跑本命令。", file=sys.stderr)
        copies["files"] = copy_container_files(args.device, want, dest, args.timeout,
                                               force=args.force_copy)
        print(f"  复制完成：成功 {len(copies['files']['copied'])}，"
              f"已存在跳过 {len(copies['files']['skipped_existing'])}，"
              f"失败 {len(copies['files']['failed'])}，耗时 {copies['files']['seconds']}s")
        if copies["files"]["failed"]:
            print(f"  失败文件：{copies['files']['failed'][:5]}", file=sys.stderr)
    flatten_double_nesting(dest)

    # ---------------------------------------------------------------- index
    vdir = dest / "Documents" / "Matches"
    adir = dest / "Documents" / "Analyses"
    vid_files = sorted([p for p in vdir.rglob("*")
                        if p.suffix.lower() in VIDEO_EXT]) if vdir.exists() else []
    ana_files = sorted(adir.rglob("*.json")) if adir.exists() else []
    if not vid_files:
        print("警告：复制到的目录里没有找到任何录像 (.mov)。"
              "如果手机上还没有录像，这是正常的。", file=sys.stderr)

    analyses: dict[str, dict] = {str(a): analysis_meta_fast(a) for a in ana_files}
    videos: dict[str, dict] = {}
    for v in vid_files:
        try:
            p = video_props(v)
        except RuntimeError as exc:
            p = {"error": str(exc)}
        p["path"] = str(v.relative_to(dest))
        p["size_bytes"] = v.stat().st_size
        videos[str(v)] = p

    sd_map: dict[str, str] = {}
    lib = dest / "Library" / "Application Support"
    try:
        sd_map = swiftdata_map(lib, [a.name for a in ana_files])
    except Exception as exc:                                     # noqa: BLE001
        print(f"  (SwiftData 读取失败，改用元数据匹配: {exc})")
    pairs: dict[str, str] = {}
    notes: list[str] = []
    for v in videos:
        hit = sd_map.get(Path(v).name)
        if hit:
            pair = next((a for a in ana_files if a.name == hit), None)
            if pair:
                pairs[v] = str(pair)
                notes.append(f"{Path(v).name} <-> {hit} (SwiftData)")
    method = "swiftdata" if pairs else ""
    if len(pairs) < len(videos):
        by_meta, meta_notes = metadata_map(
            {v: p for v, p in videos.items() if v not in pairs},
            {str(a): m for a, m in analyses.items() if str(a) not in set(pairs.values())})
        pairs.update(by_meta)
        notes.extend(meta_notes)
        if by_meta:
            method = (method + "+metadata") if method else "metadata"

    records = []
    for v, p in videos.items():
        apath = pairs.get(v)
        am = analyses.get(apath or "", {})
        records.append({
            "file": str(Path(v).relative_to(dest)), "name": Path(v).name,
            "duration": p.get("duration"), "duration_text": fmt_dur(p.get("duration")),
            "fps": p.get("fps"), "width": p.get("width"), "height": p.get("height"),
            "frames": p.get("frames"), "size_bytes": p.get("size_bytes"),
            "analysis": str(Path(apath).relative_to(dest)) if apath else None,
            "analysis_meta": am or None,
            "has_analysis": bool(apath),
        })
    records.sort(key=lambda r: r["name"])

    index = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "device": args.device, "bundle_id": BUNDLE_ID, "dest": str(dest),
        "lock_state": lock_state(args.device),
        "copies": copies, "remote_files": len(remote),
        "pairing_method": method or "none", "pairing_notes": notes,
        "n_recordings": len(records),
        "n_with_analysis": sum(1 for r in records if r["has_analysis"]),
        "n_analysis_files": len(ana_files),
        "recordings": records,
    }
    save_json(dest / "index.json", index)

    print(f"\n拉取目录：{dest}")
    print(f"配对方法：{method or '（没有可配对的录像/分析）'}")
    print(f"录像 {len(records)} 个，其中 {index['n_with_analysis']} 个有手机端分析；"
          f"分析文件 {len(ana_files)} 个。")
    for r in records:
        print(f"  {r['name']:44s} {r['duration_text']:>10s} {r['fps']:>6.1f}fps "
              f"{r['width']}x{r['height']} {r['size_bytes'] / 1e6:7.1f}MB "
              f"{'有分析' if r['has_analysis'] else '无分析'}")
    print(f"index.json -> {dest / 'index.json'}")
    if not records and remote:
        print("注意：手机上的文件没有复制成功，请检查手机是否解锁并重试。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VenueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
