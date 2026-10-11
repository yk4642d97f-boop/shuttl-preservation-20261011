#!/usr/bin/env python3
"""Judge the one-shot device pass (run-device-tests-v4.sh; the v3 call forms still work).

  judge.py status <pull-dir>                          newest match row (the form v3 used on 09-30 17:16)
  judge.py status <pull-dir> <after-pk>               v3 form: first row with pk > after-pk, else "waiting"
  judge.py status <pull-dir> --after <pk> [--secs S]  this test's row: the lowest pk > <pk> whose clip lasts S s
                                                      (±2 %, at least ±1 s); "waiting-ingest …" until it exists
  judge.py status <pull-dir> --pk <P>                 row P, once ensure_ingested has pinned it
  judge.py maxpk <pull-dir>                           highest match pk (taken right before a push)
  judge.py newrows <pull-dir> --after <pk>            every row with pk > <pk> as "pk=secs" (stale-inbox check)
  judge.py started <pull-dir> <prev-metrics> [--frames N]     "yes" once a run_start (of ~N frames) follows prev
  judge.py progress <pull-dir> <prev-metrics> [--pk P]        one line: the row, the last metric, open waits/pauses
  judge.py evidence <pull-dir> <prev-metrics> <tag> [--pk P]  per test: thermal, admission waits, cancelled and
                                                      failed stages, pause gaps, wasted stages, lost detect progress
  judge.py report <pull-dir> <metrics-before.jsonl> <tests.txt>   PASS / FAIL / PENDING / SKIP per test T1–T7

Inputs pulled from the phone: Documents/Diagnostics/stage-metrics.jsonl (StageMetrics, AdmissionLog and
the pause log all append to it) and the SwiftData store default.store (ZMATCH: ZSTATUS, ZFAILUREREASON,
ZLOCALVIDEOPATH, ZDURATIONSECONDS, ZCREATEDAT).
tests.txt lines (written by the script): "<tag> <done|failed> <pk> <secs>s <reason…>" or
"<tag> <pending|skip|timeout|not-ingested|not-run|invalid|missing|error> <why…>"; a later line for a tag wins.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

UNSTEADY = "三脚架"          # AnalysisOutcome.cameraUnsteady message
NO_SHUTTLE = "没有看到羽毛球"   # AnalysisOutcome.noShuttle message
APPLE_EPOCH = 978307200      # ZCREATEDAT counts seconds from 2001-01-01 UTC
# The pause log (workstream Q, requests.log 10-01 00:48):
#   analysis_paused  {ts, match (= ZID UUID), video, reason camera|recording|thermal, stage, frame|null, frames,
#                     fraction, thermal, camera_live}
#   analysis_resumed {ts, match, video, reason (of the pause it closes), seconds (whole pause), thermal}
# One pause = one paused + at most one resumed line; none if the app is killed while paused (the next line is
# then a run_start). admission_wait lines inside a pause belong to it and are not added on top.
PAUSE_EVENTS = {"analysis_paused"}
RESUME_EVENTS = {"analysis_resumed"}
PAUSE_FIELDS = {"event", "ts", "match", "video", "reason", "seconds", "stage", "frame", "frames", "fraction",
                "thermal", "camera_live"}
# P's checkpoint log (requests.log 10-01 01:06): detect_partial_load {verdict ok|missing|unreadable|
# fingerprint_mismatch|empty, next_frame, bytes, error}, detect_partial_save {verdict created|appended|
# unchanged|saved|failed, next_frame, bytes, error}, detect_partial_clear {reason}, checkpoints_clear {reason}.
# Players checkpoint events (same structure): players_partial_load, players_partial_save, players_partial_clear.
# Players progress events: players_progress {frames_done}, players_stall {seconds_since_last_frame}.
PARTIAL_SAVE_OK = {"created", "appended", "unchanged", "saved"}
LOST_DETECT_S = 60          # progress lost before the first partial save is INFO, not FAIL; a retry after this much detect should resume
THERMAL_ORDER = ["nominal", "fair", "serious", "critical"]
NAMES = {"t1": "T1 1-min", "t2": "T2 10-min", "t3": "T3 lock", "t4": "T4 kill", "t5": "T5 hand-held",
         "t6": "T6 no-shuttle", "t7": "T7 tripod"}
RAN = ("done", "failed")

def matches(d: Path) -> list[dict]:
    """ZMATCH rows by pk. A missing or half-copied store reads as no rows (= not ingested yet)."""
    db = d / "default.store"
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cols = {r[1] for r in con.execute("pragma table_info(ZMATCH)")}
        zid = "hex(ZID)" if "ZID" in cols else "NULL"
        rows = con.execute("select Z_PK, ZSTATUS, ZFAILUREREASON, ZLOCALVIDEOPATH, ZDURATIONSECONDS, ZCREATEDAT, "
                           f"{zid} from ZMATCH order by Z_PK").fetchall()
        con.close()
    except sqlite3.DatabaseError:
        return []
    out = []
    for pk, st, reason, path, secs, created, h in rows:
        epoch = (created or 0) + APPLE_EPOCH if created is not None else None
        uuid = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}".upper() if h and len(h) == 32 else ""
        out.append(dict(pk=pk, status=st or "", reason=reason or "", path=path or "", secs=secs or 0,
                        epoch=epoch, uuid=uuid, video=Path(path).name if path else "",
                        created=datetime.fromtimestamp(epoch, timezone.utc).strftime("%H:%M:%S") if epoch else "",
                        created_local=datetime.fromtimestamp(epoch).strftime("%H:%M:%S") if epoch else ""))
    return out


def events(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def since(d: Path, before: Path) -> list[dict]:
    """Metric lines appended after the snapshot `before` (the file only grows)."""
    return events(d / "stage-metrics.jsonl")[len(events(before)):]


def ts(e: dict) -> float | None:
    s = e.get("ts") or ""
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def hms(e: dict) -> str:
    return (e.get("ts") or "")[11:19] or "?"


def runs(ev: list[dict]) -> list[dict]:
    """Group stage events by run_start. detect_partial_load is logged just BEFORE its run_start (the
    pipeline loads the partial, then detect logs run_start with resume_from), so it joins the next run.
    players_partial_load follows the same pattern."""
    rs: list[dict] = []
    load = None
    players_load = None
    for e in ev:
        k = e.get("event")
        if k == "detect_partial_load":
            load = e
        elif k == "players_partial_load":
            players_load = e
        elif k == "run_start":
            rs.append(dict(start=e, stages={}, resume=[], focal=[], load=load, saves=[], clears=[],
                          players_load=players_load, players_saves=[], players_clears=[],
                          players_progress=[], players_stall=[]))
            load = None
            players_load = None
        elif rs and k == "stage":
            rs[-1]["stages"].setdefault(e.get("stage"), []).append(e)
        elif rs and k == "detect_resume":
            rs[-1]["resume"].append(e)
        elif rs and k == "calibration_focal":
            rs[-1]["focal"].append(e)
        elif rs and k == "detect_partial_save":
            rs[-1]["saves"].append(e)
        elif rs and k in ("detect_partial_clear", "checkpoints_clear"):
            rs[-1]["clears"].append(e)
        elif rs and k == "players_partial_save":
            rs[-1]["players_saves"].append(e)
        elif rs and k == "players_partial_clear":
            rs[-1]["players_clears"].append(e)
        elif rs and k == "players_progress":
            rs[-1]["players_progress"].append(e)
        elif rs and k == "players_stall":
            rs[-1]["players_stall"].append(e)
    return rs


def partial_summary(r: dict) -> str:
    """P's checkpoint log for one run (10-01 01:06): why it resumed or started from 0, and every save."""
    parts = []
    ld = r.get("load")
    if ld is not None:
        s = f'load {ld.get("verdict", "?")}'
        if ld.get("next_frame") is not None:
            s += f' next_frame {float(ld["next_frame"]):.0f}'
        if ld.get("error"):
            s += f' error={str(ld["error"])[:80]}'
        parts.append(s)
    sv = r.get("saves") or []
    if sv:
        bad = [e for e in sv if e.get("verdict") not in PARTIAL_SAVE_OK]
        last = sv[-1]
        s = f'{len(sv)} save(s), last {last.get("verdict", "?")} at frame {float(last.get("next_frame") or 0):.0f}'
        if bad:
            s += f'; {len(bad)} FAILED: ' + ", ".join(
                f'{e.get("verdict")} {str(e.get("error") or "")[:60]}'.strip() for e in bad[:3])
        parts.append(s)
    parts += [f'{e.get("event")} ({e.get("reason", "")})' for e in r.get("clears") or []]
    return "; ".join(parts)


def max_pk(d: Path) -> int:
    return max((x["pk"] for x in matches(d)), default=0)

def fmt_row(r: dict) -> str:
    if r["status"] in RAN:
        return f'{r["status"]} {r["pk"]} {r["secs"]:.0f}s {r["reason"]}'.strip()
    return f'running {r["pk"]} {r["status"]}'


def secs_ok(r: dict, secs: float | None) -> bool:
    return secs is None or abs(r["secs"] - secs) <= max(1.0, 0.02 * secs)


def status(d: Path, after_pk: int | None = None, secs: float | None = None, pk: int | None = None,
           legacy: bool = False) -> str:
    """This test's match row.
    pk        → row pk (pinned by ensure_ingested); "waiting-ingest pk P missing" if it is gone.
    after_pk  → the LOWEST pk > after_pk whose clip length matches `secs` (when given). The drain takes the
                inbox oldest-mtime first, so a later push can get the lower pk (09-30: t3_lock → 18, t2 → 19);
                the length tells them apart. "waiting-ingest …" until that row exists.
    legacy    → the v3 positional form: first pk > after_pk regardless of length, else "waiting".
    neither   → the newest row (the 09-30 17:16 logic that read T1's match 17 as T2's result)."""
    m = matches(d)
    if pk is not None:
        row = next((x for x in m if x["pk"] == pk), None)
        return fmt_row(row) if row else f"waiting-ingest pk {pk} missing from the store"
    if after_pk is None:
        return fmt_row(m[-1]) if m else "no-store"
    new = [x for x in m if x["pk"] > after_pk]
    if legacy:
        return fmt_row(new[0]) if new else "waiting"
    hit = [x for x in new if secs_ok(x, secs)]
    if hit:
        return fmt_row(hit[0])
    if not (d / "default.store").exists():
        return f"waiting-ingest after {after_pk} (no store pulled)"
    want = f" of {secs:g}s" if secs is not None else ""
    other = ", ".join(f'{x["pk"]}={x["secs"]:.0f}s' for x in new)
    return f"waiting-ingest after {after_pk}{want}" + (f" (other new rows: {other})" if other else "")


def started(d: Path, before: Path, frames: float | None = None) -> bool:
    """True once a run_start (of about `frames` frames, when given) follows the snapshot `before`."""
    for e in since(d, before):
        if e.get("event") == "run_start":
            if frames is None or abs(float(e.get("frames") or 0) - frames) <= max(60.0, 0.01 * frames):
                return True
    return False

def is_pause(e: dict) -> bool:
    return e.get("event") in PAUSE_EVENTS


def is_resume(e: dict) -> bool:
    return e.get("event") in RESUME_EVENTS


def pair_pauses(ev: list[dict]) -> list[dict]:
    """analysis_paused → its analysis_resumed (same match; else same reason; else the oldest open pause).
    A pause still open at the next run_start had no resumed line (app killed / jetsammed while paused):
    it ends there with ended="killed". A pause open at the end of the window stays OPEN."""
    out: list[dict] = []
    open_: list[dict] = []
    for e in ev:
        if is_pause(e):
            p = dict(reason=e.get("reason", "?"), begin=ts(e), begin_hms=hms(e), end=None, end_hms=None,
                     seconds=None, stage=e.get("stage"), frame=e.get("frame"), frames=e.get("frames"),
                     fraction=e.get("fraction"), thermal=e.get("thermal"), camera_live=e.get("camera_live"),
                     match=e.get("match"), video=e.get("video"), ended=None,
                     extra={k: v for k, v in e.items() if k not in PAUSE_FIELDS})
            open_.append(p)
            out.append(p)
        elif is_resume(e):
            p = (next((x for x in open_ if e.get("match") and x["match"] == e.get("match")), None)
                 or next((x for x in open_ if x["reason"] == e.get("reason")), None)
                 or (open_[0] if open_ else None))
            if p is None:
                out.append(dict(reason=e.get("reason", "?"), begin=None, begin_hms="?", end=ts(e), end_hms=hms(e),
                                seconds=e.get("seconds"), stage=None, frame=None, frames=None, fraction=None,
                                thermal=e.get("thermal"), camera_live=None, match=e.get("match"),
                                video=e.get("video"), ended="resumed", orphan=True,
                                extra={k: v for k, v in e.items() if k not in PAUSE_FIELDS}))
                if out[-1]["seconds"] is not None and out[-1]["end"]:
                    out[-1]["begin"] = out[-1]["end"] - float(out[-1]["seconds"])
                continue
            open_.remove(p)
            p["end"], p["end_hms"], p["ended"] = ts(e), hms(e), "resumed"
            p["seconds"] = e.get("seconds") if e.get("seconds") is not None else (
                p["end"] - p["begin"] if p["end"] and p["begin"] else None)
            p["thermal_end"] = e.get("thermal")
            p["extra"].update({k: v for k, v in e.items() if k not in PAUSE_FIELDS})
        elif e.get("event") == "run_start" and open_:
            for p in open_:
                p["end"], p["end_hms"], p["ended"] = ts(e), hms(e), "killed"
                p["seconds"] = p["end"] - p["begin"] if p["end"] and p["begin"] else None
            open_ = []
    return out


def in_pause(w: dict, pauses: list[dict]) -> bool:
    """An admission_wait that lies inside a pause belongs to that pause (Q: do not sum both)."""
    return any(p["begin"] is not None and w.get("begin") is not None and p["begin"] - 2 <= w["begin"]
               and (p["end"] is None or (w.get("end") or w["begin"]) <= p["end"] + 2) for p in pauses)


def pair_waits(ev: list[dict]) -> list[dict]:
    """admission_wait begin → end (same reason). end carries seconds; an unpaired begin is still open."""
    out: list[dict] = []
    open_: list[dict] = []
    for e in ev:
        if e.get("event") != "admission_wait":
            continue
        if e.get("phase") == "begin":
            w = dict(reason=e.get("reason", "?"), begin=ts(e), begin_hms=hms(e), end=None, end_hms=None,
                     seconds=None, outcome=None, thermal_begin=e.get("thermal"), thermal_end=None,
                     camera_live=e.get("camera_live"))
            open_.append(w)
            out.append(w)
        elif e.get("phase") == "end":
            w = next((x for x in open_ if x["reason"] == e.get("reason")), None)
            if w is None:
                w = dict(reason=e.get("reason", "?"), begin=None, begin_hms="?", camera_live=None,
                         thermal_begin=None)
                out.append(w)
            else:
                open_.remove(w)
            w.update(end=ts(e), end_hms=hms(e), seconds=e.get("seconds"), outcome=e.get("outcome"),
                     thermal_end=e.get("thermal"))
            if w["begin"] is None and w["end"] and w["seconds"] is not None:
                w["begin"] = w["end"] - float(w["seconds"])
    return out

def overlaps(a0: float | None, a1: float | None, b0: float | None, b1: float | None, slack: float = 2.0) -> bool:
    lo, hi = (a0 or 0) - slack, (a1 if a1 is not None else float("inf")) + slack
    return (b0 if b0 is not None else 0) <= hi and (b1 if b1 is not None else float("inf")) >= lo


def timeline(ev: list[dict], kill_time: float | None = None) -> list[dict]:
    """One record per run that did not reach `score` (runs that fail by design — no shuttle, unsteady —
    still score first): how it ended (cancelled / error / killed = no line at all), the gap to the next
    run_start and what explains it (analysis_paused, admission_wait, retry, relaunch, or UNLOGGED), stages
    that ran after the failure anyway (wasted), and whether a detect retry threw away its progress.

    V4: kill_time (from tests.txt "t4 killed <ISO>") is the script's real SIGKILL time, used for KILLED timing."""
    starts = [i for i, e in enumerate(ev) if e.get("event") == "run_start"]
    pauses, waits = pair_pauses(ev), pair_waits(ev)
    out = []
    for n, i in enumerate(starts):
        j = starts[n + 1] if n + 1 < len(starts) else len(ev)
        start, body = ev[i], ev[i + 1:j]
        stages = [e for e in body if e.get("event") == "stage"]
        if any(e.get("stage") == "score" for e in stages):
            continue
        nxt = ev[j] if j < len(ev) else None
        bad = next((e for e in stages if e.get("outcome") in ("cancelled", "error")), None)
        if bad is None and nxt is None:
            continue                                   # still running when the window ends
        if bad is not None:
            kind, stage, t0 = bad["outcome"], bad.get("stage"), ts(bad)
            after = stages[stages.index(bad) + 1:]
            detect_s = float(bad.get("seconds") or 0) if "detect" in stage else 0.0
        else:
            last_ok = [e.get("stage") for e in stages if e.get("stage") != "load_detector"]
            kind, after = "killed", []
            stage = f"after {last_ok[-1]}" if last_ok else "detect"
            # V4 BUG3 FIX: only use kill_time if it falls within this run's window [ts(start), ts(next_start))
            t_start = ts(start)
            t_next_start = ts(ev[j]) if j < len(ev) else None
            use_kill_time = (kill_time is not None and t_start is not None and
                           kill_time >= t_start and
                           (t_next_start is None or kill_time < t_next_start))
            t0 = kill_time if use_kill_time else (ts(body[-1]) if body else ts(start))
            detect_s = (t0 or 0) - (ts(start) or 0) if "detect" in stage else 0.0
        t1 = ts(nxt) if nxt else None
        same = nxt is not None and abs(float(nxt.get("frames") or 0) - float(start.get("frames") or 0)) <= 2
        resume_next = float(nxt.get("resume_from") or 0) if nxt else 0.0
        saves = [e for e in body if e.get("event") == "detect_partial_save"]
        # V5 BUG2 FIX: detect_partial_load appears BEFORE run_start, not inside the body.
        # current_load is at ev[i-1] (before this run's start), next_load is at ev[j-1] (before next run's start).
        current_load = None
        if i > 0 and i < len(ev) and ev[i-1].get("event") == "detect_partial_load":
            current_load = ev[i-1]
        next_load = None
        if j > 0 and j < len(ev) and ev[j-1].get("event") == "detect_partial_load":
            next_load = ev[j-1]
        # Players checkpoint events (same pattern)
        players_saves = [e for e in body if e.get("event") == "players_partial_save"]
        players_current_load = None
        if i > 0 and i < len(ev) and ev[i-1].get("event") == "players_partial_load":
            players_current_load = ev[i-1]
        players_next_load = None
        if j > 0 and j < len(ev) and ev[j-1].get("event") == "players_partial_load":
            players_next_load = ev[j-1]
        players_progress = [e for e in body if e.get("event") == "players_progress"]
        players_stalls = [e for e in body if e.get("event") == "players_stall"]
        ps = [p for p in pauses if overlaps(t0, t1, p["begin"], p["end"])]
        ws = [w for w in waits if overlaps(t0, t1, w["begin"], w["end"]) and not in_pause(w, ps)]
        causes = [f'paused {p["reason"]} {p["seconds"]:.0f}s' + (" (ended by a kill)" if p["ended"] == "killed" else "")
                  if p["seconds"] is not None else f'paused {p["reason"]} (open)' for p in ps]
        causes += [f'admission_wait {w["reason"]} {float(w["seconds"]):.0f}s' if w["seconds"] is not None
                   else f'admission_wait {w["reason"]} (open)' for w in ws]
        if not causes:
            causes = [{"error": "in-process retry", "killed": "relaunch"}.get(kind, "UNLOGGED")]
            if kind == "cancelled":
                causes = ["UNLOGGED (no analysis_paused / admission_wait covers it)"]
        # V5 BUG2 FIX: lost is FAIL only if a checkpoint existed (this run saved one, OR loaded an earlier one)
        # AND the next run didn't resume from it.
        #
        # had_checkpoint_activity means:
        #   - this run saved at least one partial with verdict created/appended, OR
        #   - this run loaded an existing partial successfully (verdict=ok with next_frame>0) at its start
        #
        # If neither happened, the checkpoint system never had a chance to work → INFO lost-before-first-checkpoint
        # If either happened but the next run still resumed from 0 → F-P3 FAIL
        had_successful_save = any(e.get("verdict") in ("created", "appended") for e in saves)
        loaded_existing = current_load and current_load.get("verdict") == "ok" and float(current_load.get("next_frame") or 0) > 0
        had_checkpoint_activity = had_successful_save or loaded_existing
        next_load_resumed = next_load and next_load.get("verdict") == "ok" and float(next_load.get("next_frame") or 0) > 0

        # Lost before first checkpoint (INFO): interrupted before any checkpoint activity
        lost_before_first = bool(same and "detect" in stage and resume_next == 0 and
                                not had_checkpoint_activity and detect_s >= LOST_DETECT_S)
        # Lost after checkpoint (F-P3 FAIL): had checkpoint activity but next run didn't resume
        lost_after_checkpoint = bool(same and "detect" in stage and resume_next == 0 and
                                   had_checkpoint_activity and not next_load_resumed and detect_s >= LOST_DETECT_S)

        # V5 BUG1 FIX: for killed runs, at_hms must use kill_time (already in t0), not body[-1]
        if kind == "killed" and t0 is not None:
            at_hms = datetime.fromtimestamp(t0, tz=timezone.utc).strftime("%H:%M:%S")
        else:
            at_hms = hms(bad) if bad else (hms(body[-1]) if body else hms(start))
        out.append(dict(
            run_hms=hms(start), frames=float(start.get("frames") or 0), kind=kind, stage=stage,
            at_hms=at_hms,
            error=(bad or {}).get("error"), detect_s=detect_s,
            gap=(t1 - t0) if (t1 is not None and t0 is not None) else None,
            next_hms=hms(nxt) if nxt else None, next_same_clip=same, resume_next=resume_next,
            causes=causes, unlogged=kind == "cancelled" and not ps and not ws,
            wasted=[(e.get("stage"), float(e.get("seconds") or 0), e.get("outcome")) for e in after],
            saves=len(saves), failed_saves=[e for e in saves if e.get("verdict") not in PARTIAL_SAVE_OK],
            last_save=(saves[-1].get("verdict"), float(saves[-1].get("next_frame") or 0)) if saves else None,
            next_load=(next_load.get("verdict"), next_load.get("next_frame"), next_load.get("error"))
            if next_load else None,
            lost=lost_after_checkpoint,
            lost_before_first=lost_before_first,
            players_saves=len(players_saves),
            players_failed_saves=[e for e in players_saves if e.get("verdict") not in PARTIAL_SAVE_OK],
            players_last_save=(players_saves[-1].get("verdict"), float(players_saves[-1].get("next_frame") or 0)) if players_saves else None,
            players_next_load=(players_next_load.get("verdict"), players_next_load.get("next_frame"), players_next_load.get("error"))
            if players_next_load else None,
            players_progress_count=len(players_progress),
            players_stall_count=len(players_stalls)))
    return out


def interruption_line(r: dict) -> str:
    what = f'{r["stage"]}'
    if r["detect_s"]:
        what += f' after {r["detect_s"]:.1f}s'
    what += f' at {r["at_hms"]} (run {r["run_hms"]}, {r["frames"]:.0f} fr)'
    if r["error"]:
        what += f' error={r["error"][:90]}'
    if r["next_hms"] is None:
        gap = "no run_start after it in this window"
    else:
        gap = f'gap {r["gap"]:.0f}s → run_start {r["next_hms"]}' if r["gap"] is not None else f'→ run_start {r["next_hms"]}'
        gap += f' resume_from {r["resume_next"]:.0f}' if r["next_same_clip"] else " (a different clip)"
    s = f'    {r["kind"].upper()} {what}; {gap}; cause: {", ".join(r["causes"])}'
    if r["wasted"]:
        s += "\n      wasted after the failure: " + ", ".join(f"{st} {sec:.1f}s {oc}" for st, sec, oc in r["wasted"]) + \
             f' (= {sum(sec for _, sec, _ in r["wasted"]):.1f}s)'
    if r.get("saves") or r.get("next_load"):
        cp = []
        if r.get("last_save"):
            cp.append(f'{r["saves"]} partial save(s) before it, last {r["last_save"][0]} at frame {r["last_save"][1]:.0f}')
        elif r.get("next_load") is not None:
            cp.append("no partial save before it")
        if r.get("failed_saves"):
            cp.append(f'{len(r["failed_saves"])} FAILED save(s): ' + ", ".join(
                str(e.get("error") or e.get("verdict"))[:60] for e in r["failed_saves"][:3]))
        if r.get("next_load"):
            v, nf, err = r["next_load"]
            cp.append(f'next run loaded the partial: {v}' + (f' next_frame {float(nf):.0f}' if nf is not None else "")
                      + (f' error={str(err)[:60]}' if err else ""))
        s += "\n      checkpoint: " + "; ".join(cp)
    if r["lost"]:
        why = f' — load verdict {r["next_load"][0]}' if r.get("next_load") else " (no detect_partial_load line: build without P's log)"
        s += f'\n      LOST DETECT PROGRESS (F-P3): {r["detect_s"]:.0f}s of detect, retry resume_from 0{why}'
    # V4: progress lost before first checkpoint is INFO, not F-P3
    if r.get("lost_before_first"):
        s += f'\n      INFO lost-before-first-checkpoint: {r["detect_s"]:.0f}s of detect before the first partial save'
    # Players checkpoint info
    if r.get("players_saves") or r.get("players_next_load"):
        pcp = []
        if r.get("players_last_save"):
            pcp.append(f'{r["players_saves"]} players partial save(s) before it, last {r["players_last_save"][0]} at frame {r["players_last_save"][1]:.0f}')
        elif r.get("players_next_load") is not None:
            pcp.append("no players partial save before it")
        if r.get("players_failed_saves"):
            pcp.append(f'{len(r["players_failed_saves"])} FAILED players save(s): ' + ", ".join(
                str(e.get("error") or e.get("verdict"))[:60] for e in r["players_failed_saves"][:3]))
        if r.get("players_next_load"):
            v, nf, err = r["players_next_load"]
            pcp.append(f'next run loaded players partial: {v}' + (f' next_frame {float(nf):.0f}' if nf is not None else "")
                      + (f' error={str(err)[:60]}' if err else ""))
        s += "\n      players checkpoint: " + "; ".join(pcp)
    if r.get("players_progress_count"):
        s += f'\n      players_progress: {r["players_progress_count"]} event(s) in this run'
    if r.get("players_stall_count"):
        s += f'\n      players_stall: {r["players_stall_count"]} event(s) in this run'
    return s

def wait_line(w: dict) -> str:
    sec = f'{float(w["seconds"]):.1f}s' if w.get("seconds") is not None else "OPEN (no end line yet)"
    return (f'    admission_wait {w["reason"]} {w["begin_hms"]}→{w.get("end_hms") or "…"} {sec} '
            f'outcome={w.get("outcome") or "-"} thermal {w.get("thermal_begin") or "?"}→{w.get("thermal_end") or "?"} '
            f'camera_live={w.get("camera_live")}')


def pause_line(p: dict, pk_by_uuid: dict | None = None) -> str:
    if p.get("seconds") is None:
        sec = "OPEN (no analysis_resumed yet)"
    else:
        sec = f'{float(p["seconds"]):.1f}s'
        if p.get("ended") == "killed":
            sec += " ENDED BY A KILL/RELAUNCH (no analysis_resumed; next run_start)"
    s = f'    analysis_paused {p["reason"]} {p["begin_hms"]}→{p.get("end_hms") or "…"} {sec}'
    if p.get("match"):
        pk = (pk_by_uuid or {}).get(str(p["match"]).upper())
        s += f' match={pk if pk is not None else p["match"]}'
    if p.get("video"):
        s += f' video={p["video"]}'
    if p.get("stage") is not None or p.get("frame") is not None:
        s += f' stage={p.get("stage")} frame={p.get("frame")}'
        if p.get("frames"):
            s += f'/{float(p["frames"]):.0f}'
    if p.get("fraction") is not None:
        s += f' fraction={float(p["fraction"]):.2f}'
    if p.get("thermal") or p.get("thermal_end"):
        s += f' thermal={p.get("thermal") or "?"}→{p.get("thermal_end") or "?"}'
    if p.get("camera_live") is not None:
        s += f' camera_live={p["camera_live"]}'
    if p.get("orphan"):
        s += " (resumed line without a paused line)"
    if p.get("extra"):
        s += f' extra={json.dumps(p["extra"], ensure_ascii=False, sort_keys=True)}'
    return s


def thermal_peak(ev: list[dict]) -> str:
    seen = [v for e in ev for k in ("thermal_start", "thermal_end", "thermal") if (v := e.get(k)) in THERMAL_ORDER]
    return max(seen, key=THERMAL_ORDER.index) if seen else "?"


def evidence(d: Path, before: Path, tag: str, pk: int | None = None, tests: Path | None = None) -> str:
    """Everything logged since the previous evidence call, one block per test."""
    ev = since(d, before)
    m = matches(d)
    out = [f"  [{tag}] evidence ({len(ev)} new metric lines, thermal peak {thermal_peak(ev)})"]
    # V4: pass kill_time for KILLED timing
    kill_time = parse_kill_time(tests, tag) if tests else None
    waits, pauses, tl = pair_waits(ev), pair_pauses(ev), timeline(ev, kill_time)
    out += [wait_line(w) + (" (inside a pause, counted there)" if in_pause(w, pauses) else "") for w in waits]
    ends = [w for w in waits if w.get("seconds") is not None and not in_pause(w, pauses)]
    if ends:
        out.append(f"    admission_wait total {sum(float(w['seconds']) for w in ends):.0f} s over {len(ends)} wait(s) "
                   f"outside pauses; reasons {sorted({w['reason'] for w in ends})}")
    uuids = {x["uuid"]: x["pk"] for x in m if x.get("uuid")}
    out += [pause_line(p, uuids) for p in pauses]
    closed = [p for p in pauses if p.get("seconds") is not None]
    if closed:
        out.append(f"    analysis_paused total {sum(float(p['seconds']) for p in closed):.0f} s over {len(closed)} pause(s); "
                   f"reasons {sorted({p['reason'] for p in closed})}")
    out += [interruption_line(r) for r in tl]
    for r in runs(ev):
        st = r["start"]
        th = [f"{k}:{es[-1].get('thermal_start', '?')}→{es[-1].get('thermal_end', '?')}"
              for k, es in r["stages"].items() if es[-1].get("thermal_start")]
        secs = {k: round(sum(e.get("seconds", 0) or 0 for e in es), 1) for k, es in r["stages"].items()}
        bad = [f"{k}:{e.get('outcome')}" for k, es in r["stages"].items() for e in es if e.get("outcome") != "ok"]
        peak = max((e.get("footprint_peak_mb", 0) or 0 for es in r["stages"].values() for e in es), default=0)
        out.append(f"    run {st.get('frames', 0):.0f} fr start {hms(st)} resume_from {st.get('resume_from', 0):.0f} "
                   f"peak {peak:.0f} MB thermal [{', '.join(th)}] stages {secs}" + (f" NOT OK {bad}" if bad else ""))
        ps = partial_summary(r)
        if ps:
            out.append(f"      checkpoint: {ps}")
    row = next((x for x in m if x["pk"] == pk), None) if pk is not None else (m[-1] if m else None)
    if row:
        label = "match" if pk is not None else "newest match"
        out.append(f"    {label} {row['pk']} {row['status']} {row['secs']:.0f}s created {row['created'] or '?'}Z "
                   f"({row['created_local'] or '?'} local) {row['reason']}".rstrip())
    if not waits:
        out.append("    (no admission_wait events in this window)")
    if not any(e.get("event") in PAUSE_EVENTS | RESUME_EVENTS for e in ev):
        out.append("    (no analysis_paused / analysis_resumed events in this window — build without Q's pause log?)")
    if any(e.get("event") == "run_start" for e in ev) and not any(
            e.get("event") in ("detect_partial_load", "detect_partial_save") for e in ev):
        out.append("    (no detect_partial_load / detect_partial_save events in this window — build without P's checkpoint log?)")
    if any(e.get("event") == "run_start" for e in ev) and not any(
            e.get("event") in ("players_partial_load", "players_partial_save", "players_progress", "players_stall") for e in ev):
        out.append("    (no players_partial_load / players_partial_save / players_progress / players_stall events in this window — build without players checkpoint log?)")
    return "\n".join(out)


def progress(d: Path, before: Path, pk: int | None = None) -> str:
    """A one-line heartbeat while a test runs."""
    ev = since(d, before)
    row = status(d, pk=pk) if pk is not None else status(d)
    last = next((e for e in reversed(ev) if e.get("event") in ("stage", "run_start", "admission_wait",
                                                                 "detect_partial_save")
                 or is_pause(e) or is_resume(e)), None)
    if last is None:
        what = "no new metric lines"
    elif last.get("event") == "stage":
        what = f'last stage {last.get("stage")} {last.get("outcome")} {hms(last)} thermal {last.get("thermal_end", "?")}'
    elif last.get("event") == "run_start":
        what = f'run_start {last.get("frames", 0):.0f} fr {hms(last)} resume_from {last.get("resume_from", 0):.0f} (detect running)'
    else:
        what = f'{last.get("event")} {last.get("phase", "")} {last.get("reason", "")} {hms(last)}'.replace("  ", " ")
    open_w = [w for w in pair_waits(ev) if w.get("seconds") is None]
    open_p = [p for p in pair_pauses(ev) if p.get("end") is None and not p.get("orphan")]
    extra = "".join(f"; OPEN admission_wait {w['reason']} since {w['begin_hms']}" for w in open_w)
    extra += "".join(f"; OPEN pause {p['reason']} since {p['begin_hms']}" for p in open_p)
    return f"{row}; {what}{extra}"

def read_tests(tests: Path) -> dict[str, list[str]]:
    by_tag: dict[str, list[str]] = {}
    for line in (tests.read_text().splitlines() if tests.exists() else []):
        p = line.split()
        if len(p) >= 2:
            # V4 BUG1 FIX: skip "killed" lines when picking verdict
            if p[1] != "killed":
                by_tag[p[0]] = p                   # a later line for the same tag wins
    return by_tag


def parse_kill_time(tests: Path, tag: str) -> float | None:
    """V5 BUG1 FIX: extract the script's kill time from kills.txt.

    Format: kills.txt has lines like "t4 2026-10-01T01:58:20Z" (tag + ISO timestamp).
    The script writes this when killing a test run.
    """
    kills_file = tests.parent / "kills.txt" if tests else None
    if not kills_file or not kills_file.exists():
        return None

    try:
        for line in kills_file.read_text().strip().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == tag:
                # ISO format: 2026-10-01T01:58:20Z
                dt = datetime.strptime(parts[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                return dt.timestamp()
    except (ValueError, OSError):
        pass
    return None


def report(d: Path, tests: Path, before: Path | None = None) -> str:
    ev = since(d, before) if before else events(d / "stage-metrics.jsonl")
    rs = runs(ev)
    m = {x["pk"]: x for x in matches(d)}
    by_tag = read_tests(tests)
    # V4: extract t4 kill time
    kill_time = parse_kill_time(tests, "t4")
    lines = [f"{len(rs)} runs since the pass started; {len(m)} matches in the store"]

    def total(r):
        return sum(e.get("seconds", 0) for es in r["stages"].values() for e in es if e.get("outcome") == "ok")

    def peak(r):
        return max((e.get("footprint_peak_mb", 0) or 0 for es in r["stages"].values() for e in es), default=0)

    for r in rs:
        s = r["start"]
        secs = total(r)
        dur = s.get("frames", 0) / max(s.get("fps", 1), 1)
        lines.append(f'  run {s.get("frames", 0):.0f} fr ({dur:.0f} s video): {secs:.0f} s = {secs / max(dur, 1):.2f}x real time, '
                     f'peak {peak(r):.0f} MB, resume_from {s.get("resume_from", 0):.0f}, '
                     f'stages {",".join(k for k in r["stages"])}')
    ran = set()
    for tag, name in NAMES.items():
        p = by_tag.get(tag)
        if p is None:
            lines.append(f"FAIL {name}: no result (timed out or not run)")
            continue
        word, rest = p[1], " ".join(p[2:])
        if word == "skip":
            lines.append(f"SKIP {name}: {rest or 'not selected (--tests)'}")
            continue
        ran.add(tag)
        if word == "pending":
            lines.append(f"PENDING {name}: {rest}")
            continue
        if word not in RAN or len(p) < 3 or not p[2].isdigit():
            lines.append(f"FAIL {name}: {word} {rest}".rstrip())
            continue
        row = m.get(int(p[2]), dict(status=word, reason=" ".join(p[4:])))
        ok = row["status"] == "done"
        if tag == "t5":
            ok = row["status"] == "failed" and UNSTEADY in row["reason"]
        if tag == "t6":
            ok = row["status"] == "failed" and NO_SHUTTLE in row["reason"]
        lines.append(f'{"PASS" if ok else "FAIL"} {name}: match {p[2]} {row["status"]} {row["reason"]}'.rstrip())
    if "t4" in ran:
        resumed = [r for r in rs if r["start"].get("resume_from", 0) > 0 or any(e.get("used") for e in r["resume"])]
        lines.append(f'{"PASS" if resumed else "FAIL"} T4 detect resumed from a checkpoint: {len(resumed)} run(s)')
    if "t6" in ran:
        n12 = [r for r in rs if abs(r["start"].get("frames", 0) - 720) < 30]   # 12 s @ 60 fps
        lines.append(f'{"PASS" if len(n12) <= 1 else "FAIL"} T6 analysed once (no auto-retry): {len(n12)} run(s)')
    if "t7" in ran and by_tag["t7"][1] != "pending":
        foc = [f for r in rs for f in r["focal"] if f.get("reason") == "ok" and f.get("focal_hint_px")]
        for f in foc:
            rel = f.get("focal_rel_diff")
            lines.append(f'{"PASS" if rel is not None and abs(rel) <= 0.15 else "FAIL"} T7 focal hint {f.get("focal_hint_px"):.0f} '
                         f'vs solved {f.get("focal_solved_px", float("nan")):.0f} px (rel {rel})')
        if not foc:
            lines.append("FAIL T7 no auto-accepted calibration with a focal hint (was the tripod clip recorded with the app?)")
    tl = timeline(ev, kill_time)
    unlogged = [r for r in tl if r["unlogged"]]
    lost = [r for r in tl if r["lost"]]
    lost_before_first = [r for r in tl if r.get("lost_before_first")]
    pauses = pair_pauses(ev)
    waits = [w for w in pair_waits(ev) if w.get("seconds") is not None and not in_pause(w, pauses)]
    lines.append(f"INFO interruptions: {len(tl)} ({sum(r['kind'] == 'cancelled' for r in tl)} cancelled, "
                 f"{sum(r['kind'] == 'error' for r in tl)} error, {sum(r['kind'] == 'killed' for r in tl)} killed); "
                 f"admission_wait {len(waits)} ({sum(float(w['seconds']) for w in waits):.0f} s); "
                 f"analysis_paused {len(pauses)} ({sum(float(p['seconds'] or 0) for p in pauses):.0f} s); "
                 f"thermal peak {thermal_peak(ev)}")
    lines += [interruption_line(r) for r in tl]
    lines.append(f'{"PASS" if not unlogged else "FAIL"} every cancelled run has its pause logged '
                 f'(analysis_paused or admission_wait): {len(unlogged)} unlogged')
    lines.append(f'{"PASS" if not lost else "FAIL"} no detect retry threw away progress (F-P3): {len(lost)} lost')
    # V4: lost before first checkpoint is INFO
    if lost_before_first:
        lines.append(f'INFO lost-before-first-checkpoint: {len(lost_before_first)} run(s) lost progress before the first checkpoint')
    saves = [e for e in ev if e.get("event") == "detect_partial_save"]
    loads = [e for e in ev if e.get("event") == "detect_partial_load"]
    if saves or loads:
        bad = [e for e in saves if e.get("verdict") not in PARTIAL_SAVE_OK]
        verdicts: dict[str, int] = {}
        for e in loads:
            verdicts[e.get("verdict", "?")] = verdicts.get(e.get("verdict", "?"), 0) + 1
        lines.append(f'{"PASS" if not bad else "FAIL"} every detect partial save succeeded: {len(saves)} save(s), '
                     f'{len(bad)} failed; partial loads {verdicts}')
    else:
        lines.append("INFO no detect_partial_load / detect_partial_save lines (build without P's checkpoint log)")

    # Players checkpoint events
    players_saves = [e for e in ev if e.get("event") == "players_partial_save"]
    players_loads = [e for e in ev if e.get("event") == "players_partial_load"]
    players_progress_events = [e for e in ev if e.get("event") == "players_progress"]
    players_stall_events = [e for e in ev if e.get("event") == "players_stall"]
    if players_saves or players_loads or players_progress_events or players_stall_events:
        bad_players = [e for e in players_saves if e.get("verdict") not in PARTIAL_SAVE_OK]
        players_verdicts: dict[str, int] = {}
        for e in players_loads:
            players_verdicts[e.get("verdict", "?")] = players_verdicts.get(e.get("verdict", "?"), 0) + 1
        lines.append(f'{"PASS" if not bad_players else "FAIL"} every players partial save succeeded: {len(players_saves)} save(s), '
                     f'{len(bad_players)} failed; partial loads {players_verdicts}')
        if players_progress_events:
            lines.append(f'INFO players_progress: {len(players_progress_events)} event(s)')
        if players_stall_events:
            lines.append(f'INFO players_stall: {len(players_stall_events)} event(s)')
    else:
        lines.append("INFO no players_partial_load / players_partial_save / players_progress / players_stall lines (build without players checkpoint log)")

    return "\n".join(lines)


def flag(args: list[str], name: str, cast):
    """Pops `--name value` from args."""
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        sys.exit(f"{name} needs a value")
    v = args[i + 1]
    del args[i:i + 2]
    return cast(v) if v != "" else None


def main(argv: list[str]) -> str:
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, args = argv[0], list(argv[1:])
    after, secs, pk = flag(args, "--after", int), flag(args, "--secs", float), flag(args, "--pk", int)
    frames = flag(args, "--frames", float)
    d = Path(args[0])
    if cmd == "status":
        if after is None and pk is None and len(args) > 1:
            return status(d, int(args[1]), legacy=True)        # v3 positional form
        return status(d, after, secs, pk)
    if cmd == "maxpk":
        return str(max_pk(d))
    if cmd == "newrows":
        return " ".join(f'{x["pk"]}={x["secs"]:.0f}s' for x in matches(d) if x["pk"] > (after or 0))
    if cmd == "started":
        return "yes" if started(d, Path(args[1]), frames) else "no"
    if cmd == "progress":
        return progress(d, Path(args[1]), pk)
    if cmd == "evidence":
        tests_path = Path(args[3]) if len(args) > 3 and args[3] != "--pk" else None
        return evidence(d, Path(args[1]), args[2], pk, tests_path)
    if cmd == "report":
        before = Path(args[2]) if len(args) > 2 else None
        return report(d, Path(args[1]), before)
    sys.exit(__doc__)


if __name__ == "__main__":
    print(main(sys.argv[1:]))
