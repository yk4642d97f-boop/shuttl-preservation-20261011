#!/usr/bin/env python3
"""Replay the 09-30 17:16 re-pass from the saved evidence (.agent-logs/device-evidence-0930), OFFLINE.

snapshot(t) rebuilds what `devicectl copy from` would have pulled at UTC epoch t: the store with only the
rows created by t (and their status at t), and stage-metrics.jsonl cut at t. Always writes to a new dir.

Facts from the evidence (UTC; Beijing = +8):
  match 17 (T1, 60 s)       created 09:16:58, score 09:19:35
  match 18 (t3_lock, 60 s)  created 09:25:18, score 09:26:14   (pushed 17:21:05 local, AFTER T2)
  match 19 (T2, 600 s)      created 09:25:19, still analyzing when the evidence ends (09:35:53)
  pushes (report.txt of /tmp/shuttl-device-final-0930-1716): t2 17:20:30, t3 17:21:05 local.
Beyond the evidence, the offline v4 run needs T2 to end: SYNTH_DONE_19 marks match 19 done at 09:42:00.
That line is SYNTHETIC (not phone data) and only used by the fake device; the proof table stops at 09:35:53.

  python replay_0930.py [evidence-dir]     prints the old-vs-new verdict table and both wait loops
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import judge  # noqa: E402

REPO = HERE.parents[2]
EVIDENCE = REPO / ".agent-logs" / "device-evidence-0930"


def utc(hms: str) -> float:
    return datetime.strptime(f"2026-09-30T{hms}", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


FINISH = {17: utc("09:19:35"), 18: utc("09:26:14")}
SYNTH_DONE_19 = utc("09:42:00")
EVIDENCE_END = utc("09:35:53")
PUSH_T2 = utc("09:20:30")
NEVER_CLAMP = utc("09:25:17")          # "never" scenario: the store freezes just before 18/19 appear


def snapshot(t: float, out: Path | None = None, evidence: Path = EVIDENCE, scenario: str = "replay",
             synthetic: bool = False) -> Path:
    """The phone's store + metrics at UTC epoch t. synthetic=True lets match 19 finish at SYNTH_DONE_19."""
    out = Path(tempfile.mkdtemp(prefix="replay-", dir="/tmp")) if out is None else out
    out.mkdir(parents=True, exist_ok=True)
    if scenario == "never":
        t = min(t, NEVER_CLAMP)
    db = out / "default.store"
    for s in ("default.store", "default.store-wal", "default.store-shm"):
        (out / s).unlink(missing_ok=True)
    shutil.copyfile(evidence / "default.store", db)
    con = sqlite3.connect(db)
    con.execute("pragma journal_mode=delete")
    con.execute("delete from ZMATCH where ZCREATEDAT + ? > ?", (judge.APPLE_EPOCH, t))
    for pk, done_at in FINISH.items():
        if t < done_at:
            con.execute("update ZMATCH set ZSTATUS='analyzing' where Z_PK=?", (pk,))
    if synthetic and t >= SYNTH_DONE_19:
        con.execute("update ZMATCH set ZSTATUS='done', ZFAILUREREASON=NULL where Z_PK=19")
    con.commit()
    con.close()
    lines = (evidence / "stage-metrics-1732.jsonl").read_text().splitlines()
    keep = [ln for ln in lines if (judge.ts(judge.json.loads(ln)) or 0) <= t]
    (out / "stage-metrics.jsonl").write_text("".join(ln + "\n" for ln in keep))
    return out


def hm(t: float) -> str:
    return datetime.fromtimestamp(t + 8 * 3600, timezone.utc).strftime("%H:%M:%S")


def verdicts(t: float) -> dict:
    d = snapshot(t)
    try:
        return dict(old=judge.status(d), half=judge.status(d, 17, legacy=True),
                    new=judge.status(d, after_pk=17, secs=600))
    finally:
        shutil.rmtree(d)


def old_wait_loop() -> tuple[float, str]:
    """v3 as run at 17:16: wait_match polled every 30 s after the push and read the NEWEST row."""
    t = PUSH_T2
    while True:
        t += 30
        st = verdicts(t)["old"]
        if st.startswith(("done", "failed")):
            return t, st


def new_wait_loop() -> list[tuple[float, str]]:
    """v4: every 15 s status --after 17 --secs 600 until the row exists, then --pk <pinned> to the end."""
    t, seen, pk = PUSH_T2, [], None
    while t < EVIDENCE_END:
        t += 15
        d = snapshot(t)
        st = judge.status(d, pk=pk) if pk else judge.status(d, after_pk=17, secs=600)
        shutil.rmtree(d)
        if pk is None and not st.startswith("waiting"):
            pk = int(st.split()[1])
            st = f"PINNED match {pk}: {st}"
        if not seen or seen[-1][1] != st:
            seen.append((t, st))
    return seen


def main() -> None:
    global EVIDENCE
    if len(sys.argv) > 1:
        EVIDENCE = Path(sys.argv[1])
    print("Replay of the 09-30 17:16 re-pass (local time), T2 = 10-min clip pushed 17:20:30, before-pk 17")
    print(f'{"time":8}  {"OLD: status <dir> (newest row)":32}  {"HALF-FIX: status <dir> 17":26}  NEW: status --after 17 --secs 600')
    for s in ("09:20:30", "09:21:00", "09:21:02", "09:23:00", "09:25:18", "09:25:19", "09:25:30",
              "09:26:20", "09:30:40", "09:35:53"):
        v = verdicts(utc(s))
        print(f'{hm(utc(s)):8}  {v["old"]:32}  {v["half"]:26}  {v["new"]}')
    t, st = old_wait_loop()
    print(f"\nOLD wait_match loop: first poll {hm(t)} → \"T2 {st}\"  (the INVALID 17:21:02 report line)")
    print("NEW v4 loop (state changes only):")
    for t, st in new_wait_loop():
        print(f"  {hm(t)}  {st}")


if __name__ == "__main__":
    main()
