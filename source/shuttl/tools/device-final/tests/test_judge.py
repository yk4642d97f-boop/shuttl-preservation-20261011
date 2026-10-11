"""pytest for tools/device-final/judge.py (offline; synthetic stores + the saved 09-30 evidence).

  backend/.venv/bin/python -m pytest tools/device-final/tests -q
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import judge  # noqa: E402
import replay_0930  # noqa: E402


def store(d: Path, rows: list[tuple]) -> Path:
    """rows: (pk, status, secs, reason)."""
    d.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(d / "default.store")
    con.execute("create table ZMATCH (Z_PK integer primary key, ZSTATUS varchar, ZFAILUREREASON varchar, "
                "ZLOCALVIDEOPATH varchar, ZDURATIONSECONDS float, ZCREATEDAT timestamp)")
    for pk, st, secs, reason in rows:
        con.execute("insert into ZMATCH values (?,?,?,?,?,?)", (pk, st, reason, f"Matches/m{pk}.mp4", secs, 812500000.0 + pk))
    con.commit()
    con.close()
    return d


def metrics(d: Path, ev: list[dict]) -> Path:
    (d / "stage-metrics.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    return d / "stage-metrics.jsonl"


def T(s: str) -> str:
    return f"2026-10-01T{s}Z"


# ---- status: the 09-30 race -------------------------------------------------------------------

def test_newest_row_is_the_old_bug_and_after_waits(tmp_path):
    d = store(tmp_path, [(16, "done", 600, ""), (17, "done", 60, "")])   # T2 pushed, not ingested yet
    assert judge.status(d) == "done 17 60s"                               # what v3 printed as "T2 done"
    assert judge.status(d, after_pk=17, secs=600) == "waiting-ingest after 17 of 600s"
    assert judge.main(["status", str(d), "--after", "17", "--secs", "600"]).startswith("waiting-ingest")


def test_drain_order_is_by_mtime_so_length_picks_the_row(tmp_path):
    # t3_lock (60 s, pushed later but older mtime) became 18, T2 (600 s) became 19.
    d = store(tmp_path, [(17, "done", 60, ""), (18, "done", 60, ""), (19, "analyzing", 600, "")])
    assert judge.status(d, 17, legacy=True) == "done 18 60s"             # the half-fix: wrong clip
    assert judge.status(d, after_pk=17, secs=600) == "running 19 analyzing"
    assert judge.status(d, after_pk=17, secs=60) == "done 18 60s"
    assert judge.main(["newrows", str(d), "--after", "17"]) == "18=60s 19=600s"


def test_waiting_ingest_names_other_new_rows(tmp_path):
    d = store(tmp_path, [(17, "done", 60, ""), (18, "analyzing", 60, "")])
    assert judge.status(d, after_pk=17, secs=600) == "waiting-ingest after 17 of 600s (other new rows: 18=60s)"


def test_length_tolerance(tmp_path):
    d = store(tmp_path, [(4, "failed", 10.8667, "请用三脚架"), (6, "failed", 12.0, "x")])
    assert judge.status(d, after_pk=3, secs=10.87).startswith("failed 4")
    assert judge.status(d, after_pk=4, secs=10.87).startswith("waiting-ingest")
    assert judge.status(d, after_pk=4, secs=12).startswith("failed 6")


def test_pinned_pk_and_missing(tmp_path):
    d = store(tmp_path, [(19, "failed", 600, "没有看到羽毛球")])
    assert judge.status(d, pk=19) == "failed 19 600s 没有看到羽毛球"
    assert judge.status(d, pk=20) == "waiting-ingest pk 20 missing from the store"


def test_no_or_broken_store_is_waiting_not_done(tmp_path):
    assert judge.status(tmp_path, after_pk=17, secs=600) == "waiting-ingest after 17 (no store pulled)"
    assert judge.status(tmp_path) == "no-store"
    (tmp_path / "default.store").write_bytes(b"not a database, half copied")
    assert judge.status(tmp_path, after_pk=17, secs=600).startswith("waiting-ingest")
    assert judge.max_pk(tmp_path) == 0


def test_v3_positional_form_still_works(tmp_path):
    d = store(tmp_path, [(17, "done", 60, "")])
    assert judge.main(["status", str(d), "17"]) == "waiting"
    assert judge.main(["status", str(d)]) == "done 17 60s"
    assert judge.main(["maxpk", str(d)]) == "17"


def test_started_matches_the_clip_frames(tmp_path):
    before = metrics(tmp_path, [{"event": "run_start", "frames": 3600, "ts": T("00:00:00")}])
    shutil.copy(before, tmp_path / "before.jsonl")
    metrics(tmp_path, [{"event": "run_start", "frames": 3600, "ts": T("00:00:00")},
                       {"event": "run_start", "frames": 3600, "ts": T("00:01:00")}])
    assert judge.started(tmp_path, tmp_path / "before.jsonl")
    assert not judge.started(tmp_path, tmp_path / "before.jsonl", frames=35999)


# ---- interruptions, pauses, admission waits -----------------------------------------------------

RUN60 = {"event": "run_start", "frames": 3600, "fps": 60, "resume_from": 0}
RUN600 = {"event": "run_start", "frames": 35999, "fps": 60, "resume_from": 0}


def stage(name, outcome="ok", secs=1.0, t="00:00:00", **kw):
    return {"event": "stage", "stage": name, "outcome": outcome, "seconds": secs, "ts": T(t), **kw}


def done_run(t):
    return [stage("detect", t=t), stage("players", t=t), stage("score", t=t)]


def test_cancel_with_no_pause_line_is_unlogged():
    ev = [dict(RUN60, ts=T("00:00:00")), stage("detect", "cancelled", 8.4, "00:00:08"),
          dict(RUN60, ts=T("00:01:39")), *done_run("00:02:00")]
    (r,) = judge.timeline(ev)
    assert (r["kind"], r["stage"], round(r["gap"]), r["unlogged"]) == ("cancelled", "detect", 91, True)
    assert "UNLOGGED" in judge.interruption_line(r)


def test_cancel_explained_by_analysis_paused():
    ev = [dict(RUN60, ts=T("00:00:00")),
          {"event": "analysis_paused", "reason": "camera", "stage": "detect", "frame": 480, "ts": T("00:00:08")},
          stage("detect", "cancelled", 8.4, "00:00:08"),
          {"event": "analysis_resumed", "reason": "camera", "seconds": 90.5, "ts": T("00:01:38")},
          dict(RUN60, ts=T("00:01:39"), resume_from=0), *done_run("00:02:00")]
    (r,) = judge.timeline(ev)
    assert not r["unlogged"] and r["causes"] == ["paused camera 90s"]
    (p,) = judge.pair_pauses(ev)
    assert (p["reason"], p["seconds"], p["frame"]) == ("camera", 90.5, 480)
    assert "analysis_paused camera 00:00:08→00:01:38 90.5s stage=detect frame=480" in judge.pause_line(p)


def test_unknown_pause_fields_are_printed_verbatim():
    ev = [{"event": "analysis_paused", "reason": "thermal", "newfield": 7, "ts": T("00:00:01")}]
    (p,) = judge.pair_pauses(ev)
    assert p["end"] is None and '"newfield": 7' in judge.pause_line(p) and "OPEN" in judge.pause_line(p)


Q_PAUSE = {"event": "analysis_paused", "match": "275D4E7F-AFA9-4641-B53B-02A73B3A97D9",
           "video": "match_1790760319370.mp4", "reason": "camera", "stage": "detect", "frame": 9000,
           "frames": 35999, "fraction": 0.12, "thermal": "fair", "camera_live": True}


def test_q_spec_pause_pairs_by_match_and_maps_to_pk():
    ev = [dict(RUN600, ts=T("00:00:00")), dict(Q_PAUSE, ts=T("00:02:30")),
          stage("detect", "cancelled", 150, "00:02:30"),
          {"event": "admission_wait", "phase": "begin", "reason": "camera", "ts": T("00:02:31")},
          {"event": "admission_wait", "phase": "end", "reason": "camera", "seconds": 88, "outcome": "admitted",
           "ts": T("00:03:59")},
          {"event": "analysis_resumed", "match": Q_PAUSE["match"], "video": Q_PAUSE["video"], "reason": "camera",
           "seconds": 90.0, "thermal": "fair", "ts": T("00:04:00")},
          dict(RUN600, ts=T("00:04:01"), resume_from=7200), *done_run("00:12:00")]
    (p,) = judge.pair_pauses(ev)
    assert (p["ended"], p["seconds"], p["frame"]) == ("resumed", 90.0, 9000)
    line = judge.pause_line(p, {"275D4E7F-AFA9-4641-B53B-02A73B3A97D9": 19})
    assert "match=19" in line and "frame=9000/35999" in line and "fraction=0.12" in line and "extra" not in line
    (w,) = judge.pair_waits(ev)
    assert judge.in_pause(w, [p])                                         # counted in the pause, not on top
    (r,) = judge.timeline(ev)
    assert r["causes"] == ["paused camera 90s"] and not r["unlogged"] and not r["lost"]


def test_pause_without_resumed_ends_at_the_next_run_start_as_a_kill():
    ev = [dict(RUN600, ts=T("00:00:00")), dict(Q_PAUSE, ts=T("00:01:00")),
          stage("detect", "cancelled", 60, "00:01:00"), dict(RUN600, ts=T("00:03:00"), resume_from=3600)]
    (p,) = judge.pair_pauses(ev)
    assert p["ended"] == "killed" and p["seconds"] == 120
    assert "ENDED BY A KILL" in judge.pause_line(p)
    (r,) = judge.timeline(ev)
    assert r["causes"] == ["paused camera 120s (ended by a kill)"]


def P(event, t, **kw):
    return {"event": event, "ts": T(t), **kw}


def test_p_checkpoint_log_explains_a_resume_and_joins_the_next_run():
    # P's fixed path: detect error → the run stops after detect → in-process retry loads the partial.
    ev = [P("detect_partial_load", "00:00:00", verdict="missing"), dict(RUN600, ts=T("00:00:00")),
          P("detect_partial_save", "00:00:40", verdict="created", next_frame=7200, bytes=900000),
          P("detect_partial_save", "00:01:20", verdict="appended", next_frame=14400, bytes=1800000),
          stage("detect", "error", 185.5, "00:03:05", error="-11847"),
          P("detect_partial_load", "00:03:06", verdict="ok", next_frame=14400, bytes=1800000),
          dict(RUN600, ts=T("00:03:06"), resume_from=14400), *done_run("00:09:00"),
          P("detect_partial_clear", "00:09:00", reason="candidates_saved")]
    rs = judge.runs(ev)
    assert rs[0]["load"]["verdict"] == "missing" and rs[1]["load"]["verdict"] == "ok"
    assert "load ok next_frame 14400" in judge.partial_summary(rs[1])
    assert "2 save(s), last appended at frame 14400" in judge.partial_summary(rs[0])
    (r,) = judge.timeline(ev)
    assert not r["lost"] and r["wasted"] == [] and r["resume_next"] == 14400
    line = judge.interruption_line(r)
    assert "2 partial save(s) before it, last appended at frame 14400" in line
    assert "next run loaded the partial: ok next_frame 14400" in line


def test_p_checkpoint_log_names_why_a_retry_lost_progress(tmp_path):
    """Failed save doesn't trigger F-P3 FAIL; it's INFO lost-before-first-checkpoint."""
    ev = [dict(RUN600, ts=T("00:00:00")),
          P("detect_partial_save", "00:00:40", verdict="failed", next_frame=7200, error="No space left on device"),
          stage("detect", "error", 185.5, "00:03:05", error="-11847"),
          P("detect_partial_load", "00:03:06", verdict="fingerprint_mismatch", next_frame=7200),
          dict(RUN600, ts=T("00:03:06"))]
    (r,) = judge.timeline(ev)
    # V5 BUG2 FIX: failed save doesn't count as checkpoint activity → INFO, not FAIL
    assert r["lost_before_first"] and not r["lost"] and len(r["failed_saves"]) == 1
    line = judge.interruption_line(r)
    assert "1 FAILED save(s): No space left on device" in line
    assert "INFO lost-before-first-checkpoint: 186s of detect before the first partial save" in line
    assert "next run loaded the partial: fingerprint_mismatch next_frame 7200" in line
    d = store(tmp_path, [(1, "analyzing", 600, "")])
    metrics(d, ev)
    (tmp_path / "b.jsonl").write_text("")
    (tmp_path / "t.txt").write_text("")
    rep = judge.report(d, tmp_path / "b.jsonl", tmp_path / "t.txt")
    assert "FAIL every detect partial save succeeded: 1 save(s), 1 failed; partial loads {'fingerprint_mismatch': 1}" in rep


def test_match_uuid_is_read_from_zid():
    d = replay_0930.EVIDENCE
    if not (d / "default.store").exists():
        pytest.skip("no evidence")
    m = {x["pk"]: x for x in judge.matches(d)}
    assert m[19]["uuid"] == "275D4E7F-AFA9-4641-B53B-02A73B3A97D9" and m[19]["video"] == "match_1790760319370.mp4"


def test_admission_wait_pairs_and_open_wait():
    ev = [{"event": "admission_wait", "phase": "begin", "reason": "thermal", "thermal": "serious",
           "camera_live": True, "ts": T("00:00:00")},
          {"event": "admission_wait", "phase": "end", "reason": "thermal", "seconds": 412.3, "outcome": "admitted",
           "thermal": "fair", "ts": T("00:06:52")},
          {"event": "admission_wait", "phase": "begin", "reason": "busy", "ts": T("00:07:00")}]
    a, b = judge.pair_waits(ev)
    assert (a["seconds"], a["thermal_begin"], a["thermal_end"]) == (412.3, "serious", "fair")
    assert b["seconds"] is None and "OPEN" in judge.wait_line(b)


def test_detect_error_retry_from_zero_is_lost_progress_and_wasted_stages():
    # V4 BUG2 FIX: 185s of detect with NO saves is lost_before_first (INFO), not lost (FAIL)
    ev = [dict(RUN600, ts=T("00:00:00")), stage("detect", "error", 185.5, "00:03:05", error="-11847"),
          stage("calibration_frames", secs=1.2, t="00:03:06"), stage("players", "cancelled", 5.6, "00:04:00"),
          dict(RUN600, ts=T("00:04:14"))]
    (r,) = judge.timeline(ev)
    assert r["kind"] == "error" and r["lost_before_first"] and not r["lost"]
    assert [w[0] for w in r["wasted"]] == ["calibration_frames", "players"]
    assert "lost-before-first-checkpoint" in judge.interruption_line(r).lower()


def test_resumed_retry_is_not_lost_and_kill_is_detected():
    ev = [dict(RUN600, ts=T("00:00:00")), {"event": "compute_plan", "ts": T("00:00:01")},
          dict(RUN600, ts=T("00:03:30"), resume_from=14400), *done_run("00:10:00")]
    (r,) = judge.timeline(ev)
    assert r["kind"] == "killed" and not r["lost"] and r["resume_next"] == 14400


def test_by_design_failures_and_running_runs_are_not_interruptions():
    ev = [dict(RUN60, ts=T("00:00:00")), *done_run("00:00:30"),        # no shuttle still scores
          dict(RUN60, ts=T("00:01:00")), stage("detect", t="00:01:10")]  # still running
    assert judge.timeline(ev) == []


# ---- report --------------------------------------------------------------------------------------

def test_report_pending_skip_and_later_line_wins(tmp_path):
    d = store(tmp_path, [(17, "done", 60, ""), (19, "done", 600, "")])
    metrics(d, [])
    before = tmp_path / "before.jsonl"
    before.write_text("")
    tests = tmp_path / "tests.txt"
    tests.write_text("t1 done 17 60s\nt2 done 19 600s\nt3 done 19 600s\nt3 invalid detect never started\n"
                     "t4 skip not selected\nt5 skip not selected\nt6 skip not selected\n"
                     "t7 pending the user is not at a court\n")
    rep = judge.report(d, tests, before)
    assert "PASS T1 1-min: match 17 done" in rep and "PASS T2 10-min: match 19 done" in rep
    assert "FAIL T3 lock: invalid detect never started" in rep
    assert "SKIP T4 kill" in rep and "PENDING T7 tripod: the user is not at a court" in rep
    assert "T4 detect resumed" not in rep and "T7 no auto-accepted" not in rep


# ---- replay of the saved 09-30 evidence (the offline proof) ----------------------------------------

needs_evidence = pytest.mark.skipif(not (replay_0930.EVIDENCE / "default.store").exists(),
                                    reason="no .agent-logs/device-evidence-0930")


@needs_evidence
def test_replay_0930_old_says_t2_done_17_new_waits_then_19():
    u = replay_0930.utc
    assert replay_0930.verdicts(u("09:21:02")) == dict(
        old="done 17 60s", half="waiting", new="waiting-ingest after 17 of 600s")
    assert replay_0930.verdicts(u("09:25:30"))["new"] == "running 19 analyzing"
    later = replay_0930.verdicts(u("09:26:20"))
    assert later["half"] == "done 18 60s" and later["new"] == "running 19 analyzing"
    t, st = replay_0930.old_wait_loop()
    assert st == "done 17 60s" and replay_0930.hm(t) == "17:21:00"
    seen = replay_0930.new_wait_loop()
    assert seen[0][1].startswith("waiting-ingest") and seen[1][1] == "PINNED match 19: running 19 analyzing"
    assert not any("done 17" in s for _, s in seen)


@needs_evidence
def test_replay_0930_evidence_shows_the_cancel_the_wait_and_f_p3(tmp_path):
    d = replay_0930.snapshot(replay_0930.EVIDENCE_END, tmp_path / "snap")
    before = tmp_path / "before.jsonl"
    before.write_text("".join(ln + "\n" for ln in (replay_0930.EVIDENCE / "stage-metrics-1732.jsonl")
                              .read_text().splitlines()[:205]))
    ev = judge.evidence(d, before, "t2", pk=19)
    assert "CANCELLED detect after 8.4s at 09:17:07" in ev and "gap 91s" in ev and "UNLOGGED" in ev
    assert "admission_wait busy 09:25:19→09:26:14 55.5s outcome=admitted" in ev
    assert "ERROR detect after 185.5s" in ev and "INFO lost-before-first-checkpoint" in ev
    assert "match 19 analyzing 600s" in ev


# V4 BUG1 test: kill line must not overwrite done verdict
def test_bug1_kill_line_must_not_overwrite_done_verdict(tmp_path):
    # V5: NOW OBSOLETE - the real fix is kills.txt separate from tests.txt
    # This test kept for regression: read_tests() should ignore "killed" lines if they somehow appear
    tests_txt = tmp_path / "tests.txt"
    tests_txt.write_text("t4 done 22 600s\nt4 killed 2026-10-01T01:58:20Z\n")
    tests = judge.read_tests(tests_txt)
    # After V4 fix: read_tests() skips "killed" lines, so tests["t4"] = ["t4", "done", "22", "600s"]
    assert tests["t4"] == ["t4", "done", "22", "600s"], f"kill line overwrote done: {tests['t4']}"

    # V5: parse_kill_time now reads from kills.txt, not tests.txt
    # Without kills.txt, parse_kill_time returns None
    kill_time = judge.parse_kill_time(tests_txt, "t4")
    assert kill_time is None  # V5: expects kills.txt, not tests.txt


# V4 BUG2 test: real T4 case (130s detect, no saves) should be INFO not FAIL
def test_bug2_real_t4_lost_before_first_checkpoint():
    from datetime import datetime, timezone
    # Real T4 lines 311-320: 52s detect error, retry with no load, then killed at 01:58:20
    ev = [
        dict(RUN600, ts=T("01:55:13"), frames=35999),
        stage("detect", "error", 52.263, "01:56:06", error="-11847"),
        {"event": "detect_partial_load", "ts": T("01:56:10"), "verdict": "missing"},
        dict(RUN600, ts=T("01:56:10"), frames=35999),
        stage("load_detector", "ok", 0.038, "02:01:06"),
        {"event": "detect_partial_load", "ts": T("02:01:09"), "verdict": "missing"},
        dict(RUN600, ts=T("02:01:09"), frames=35999)
    ]
    kill_ts = datetime.strptime("2026-10-01T01:58:20", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    runs = judge.timeline(ev, kill_time=kill_ts)
    # First run: 52s detect error → kind=error
    assert runs[0]["kind"] == "error"
    assert runs[0]["detect_s"] == 52.263
    # Second run: killed after 130s with no saves → lost_before_first=True, lost=False (INFO, not FAIL)
    assert runs[1]["kind"] == "killed"
    assert runs[1]["detect_s"] == 130.0
    assert runs[1]["lost_before_first"] and not runs[1]["lost"]


# V4 BUG2 test: positive F-P3 case (saved 21600, retry from 0 → FAIL)
def test_bug2_positive_f_p3_saved_then_retry_from_zero():
    # Run saves a checkpoint at frame 21600, then gets killed
    # Next run loads but verdict=missing, resume_from=0 → lost=True (F-P3 FAIL)
    ev = [
        dict(RUN600, ts=T("00:00:00")),
        stage("detect", "ok", 180.0, "00:03:00"),
        {"event": "detect_partial_save", "ts": T("00:03:00"), "verdict": "created", "next_frame": 21600},
        # Run gets killed here (no stage event, just a gap before next run_start)
        {"event": "detect_partial_load", "ts": T("00:04:10"), "verdict": "missing"},
        dict(RUN600, ts=T("00:04:10"))  # Next run starts with resume_from=0
    ]
    runs = judge.timeline(ev)
    assert len(runs) == 1  # Only the killed run (second run has no score or failure yet)
    r = runs[0]
    assert r["kind"] == "killed"
    assert r["lost"] and not r["lost_before_first"]  # This is F-P3 FAIL
    assert "LOST DETECT PROGRESS (F-P3)" in judge.interruption_line(r)


# V5 BUG1 test: kills.txt separate from tests.txt to avoid overwriting verdicts
def test_bug1_kills_file_separate_from_tests(tmp_path):
    """BUG1: tests.txt with two t4 lines (done + killed) had read_tests keeping only the killed line.

    Fix: write kill times to kills.txt instead.
    """
    tests_txt = tmp_path / "tests.txt"
    tests_txt.write_text("t4 done 22 600s\n")

    kills_txt = tmp_path / "kills.txt"
    kills_txt.write_text("t4 2026-10-01T01:58:20Z\n")

    # parse_kill_time should read from kills.txt
    kill_time = judge.parse_kill_time(tests_txt, "t4")
    assert kill_time is not None

    from datetime import datetime, timezone
    expected = datetime.strptime("2026-10-01T01:58:20", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    assert kill_time == expected

    # read_tests should only see the verdict line, not a killed line
    by_tag = judge.read_tests(tests_txt)
    assert by_tag["t4"] == ["t4", "done", "22", "600s"]

