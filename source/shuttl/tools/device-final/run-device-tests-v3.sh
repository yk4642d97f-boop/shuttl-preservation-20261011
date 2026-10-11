#!/bin/bash
# B · one-shot iPhone test pass (final phase only). v3: no taps except T3 (lock) + T7 (tripod); relaunches land on 比赛
# while a match is pending (app fix A2d); per-test thermal +
# admission_wait + ingest→start delay in report.txt. v2: prompts relayable via /tmp/shuttl-device-prompt.txt + /tmp/shuttl-device-go. Writes a report to $OUT/report.txt.
#
#   tools/device-final/run-device-tests.sh <path/to/Shuttl.app> [--skip-install]
#
# Refuses to run until .agent-logs/monitor.log contains "PHONE CONNECTED" (monitor's rule, 09-28 22:50).
# Tests, in order (each one is judged from Documents/Diagnostics/stage-metrics.jsonl and the app's
# SwiftData store, both pulled with devicectl):
#   T1  1-min 1080p60 clip          → done, per-stage seconds, peak MB, thermal, compute plan (ANE)
#   T2  10-min 1080p60 clip         → done, total ≲ 1× real time, peak MB, thermal
#   T3  lock screen during detect   → user presses the side button; after unlock the run resumes and ends done
#   T4  force-kill during detect    → 10-min clip, SIGKILL ~180 s into detect; relaunch → resume_from > 0 → done
#   T5  hand-held clip (match 4)    → failed with the "三脚架" (cameraUnsteady) message, not a result
#   T6  no-shuttle 12 s             → failed with "没有看到羽毛球", analysed ONCE (no auto-retry)
#   T7  focal hint vs solved focal  → every calibration_focal line: |focal_rel_diff| ≤ 0.15 when reason ok
#       (a real tripod recording is needed for T7; the script asks the user to record 30 s and waits)
set -u
REPO="$HOME/Downloads/华北五省"
DEV=0F92DDA9-7A87-4F05-8368-0E834177D8F3
BUNDLE=com.ycyangcong.shuttl
M=/tmp/shuttl-measure
[ -f "$M/singles_10min_1080p60.mp4" ] || M="$REPO/.ui-backup/final-0930/device-clips"   # durable copy (/tmp is wiped on reboot)
OUT=/tmp/shuttl-device-final-$(date +%m%d-%H%M)
PY="$REPO/backend/.venv/bin/python"
HERE="$(cd "$(dirname "$0")" && pwd)"
APP=${1:-}
SKIP_INSTALL=0; [ "${2:-}" = "--skip-install" ] && SKIP_INSTALL=1

grep -q "PHONE CONNECTED" "$REPO/.agent-logs/monitor.log" || { echo "monitor.log has no 'PHONE CONNECTED' — not allowed to touch the phone yet."; exit 3; }
[ -n "$APP" ] && [ -d "$APP" ] || { echo "usage: $0 <Shuttl.app> [--skip-install]"; exit 2; }
for f in singles_1min_1080p60.mp4 singles_10min_1080p60.mp4 noshuttle_12s_1080p60.mp4 userclip/match_1790584367970.mov; do
  [ -f "$M/$f" ] || { echo "missing clip $M/$f"; exit 2; }
done
mkdir -p "$OUT"
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/report.txt"; }
# A prompt goes to the terminal AND to $PROMPT (so a session can relay it to the user in chat).
# It continues on Enter in the terminal OR when $GO exists (touch it after the user has done the step).
PROMPT=/tmp/shuttl-device-prompt.txt; GO=/tmp/shuttl-device-go
ask() {
  rm -f "$GO"; printf '%s\n' "$1" > "$PROMPT"
  printf '\a\n>>> %s\n    做完后按回车继续（或 touch %s）…' "$1" "$GO"
  while [ ! -e "$GO" ]; do read -r -t 5 _ && break; done
  rm -f "$GO" "$PROMPT"; echo; echo "[$(date +%H:%M:%S)] continued: $1" >> "$OUT/report.txt"
}

xcrun devicectl list devices 2>&1 | grep -q "$DEV.*available" || { log "phone not available (unlocked + trusted + cable?)"; exit 1; }

dc_copy_to() { xcrun devicectl device copy to --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE \
                 --source "$1" --destination "$2" >/dev/null 2>&1; }
dc_copy_from() { xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE \
                   --source "$1" --destination "$2" >/dev/null 2>&1; }
# Relaunches open on 比赛 (-ShuttlOpenTab, D, release builds too; A2d does the same while a match is pending),
# so they never land on the live camera.
launch() { xcrun devicectl device process launch --terminate-existing --device $DEV $BUNDLE -ShuttlOpenTab matches >/dev/null 2>&1; }
app_pid() {
  xcrun devicectl device info processes --device $DEV --json-output "$OUT/procs.json" >/dev/null 2>&1
  "$PY" - "$OUT/procs.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for p in d.get("result", {}).get("runningProcesses", []):
    if "Shuttl.app/" in (p.get("executable") or ""):
        print(p["processIdentifier"]); break
EOF
}
pull() {   # metrics + store into $OUT/pull-<tag>/
  local d="$OUT/pull-$1"; mkdir -p "$d"
  dc_copy_from Documents/Diagnostics/stage-metrics.jsonl "$d/stage-metrics.jsonl"
  for s in default.store default.store-wal default.store-shm; do
    dc_copy_from "Library/Application Support/$s" "$d/$s"
  done
  echo "$d"
}
push() { dc_copy_to "$1" "Documents/DebugInbox/$2" && log "pushed $2 ($(du -h "$1" | cut -f1))"; }
# Each test: note the highest match pk, push, then make the ingest deterministic (relaunch until the
# DebugInbox drain has created the new row — it lagged the push by ~5 min once), then wait for THAT row.
BEFORE_PK=0
prepush() { local d; d=$(pull "pre-$1"); BEFORE_PK=$("$PY" "$HERE/judge.py" maxpk "$d" 2>/dev/null || echo 0); }
ensure_ingested() {   # tag timeout
  local tag=$1 timeout=${2:-900} t0=$SECONDS d st n=0
  while [ $((SECONDS - t0)) -lt "$timeout" ]; do
    sleep 20
    d=$(pull "ing-$tag"); st=$("$PY" "$HERE/judge.py" status "$d" "$BEFORE_PK" 2>/dev/null)
    [ "$st" != "waiting" ] && { log "$tag ingested after $((SECONDS - t0)) s: $st"; return 0; }
    n=$((n + 1)); [ $((n % 3)) = 0 ] && { log "$tag not ingested yet — relaunching"; launch; }
  done
  log "$tag NOT ingested within ${timeout}s"; return 1
}
wait_started() {   # tag timeout: until this test's detect run has started (admission may hold it)
  local tag=$1 timeout=${2:-3600} t0=$SECONDS d
  while [ $((SECONDS - t0)) -lt "$timeout" ]; do
    sleep 10
    d=$(pull "st-$tag")
    [ "$("$PY" "$HERE/judge.py" started "$d" "$PREV_METRICS" 2>/dev/null)" = yes ] && { log "$tag detect started after $((SECONDS - t0)) s"; return 0; }
  done
  log "$tag detect did not start within ${timeout}s"; return 1
}
wait_match() {   # tag timeout: waits for the row with pk > BEFORE_PK
  local tag=$1 timeout=$2 t0=$SECONDS d st
  while [ $((SECONDS - t0)) -lt "$timeout" ]; do
    sleep 30
    d=$(pull "$tag")
    st=$("$PY" "$HERE/judge.py" status "$d" "$BEFORE_PK" 2>/dev/null)
    case "$st" in done*|failed*) echo "$tag $st" >> "$OUT/tests.txt"; echo "$st"; return 0;; esac
  done
  echo "timeout"; return 1
}
# Per-test evidence from the newest pull: thermal, admission waits, ingest→start delay, stage times.
PREV_METRICS="$OUT/metrics-before.jsonl"
evidence() {
  "$PY" "$HERE/judge.py" evidence "$OUT/pull-$1" "$PREV_METRICS" "$1" >> "$OUT/report.txt" 2>&1
  [ -f "$OUT/pull-$1/stage-metrics.jsonl" ] && PREV_METRICS="$OUT/pull-$1/stage-metrics.jsonl"
}

log "OUT=$OUT  app=$APP"
if [ $SKIP_INSTALL = 0 ]; then
  xcrun devicectl device install app --device $DEV "$APP" 2>&1 | grep -E "bundleID|rror" | tee -a "$OUT/report.txt"
fi
dc_copy_from Documents/Diagnostics/stage-metrics.jsonl "$OUT/metrics-before.jsonl"   # baseline line count
xcrun devicectl device info lockState --device $DEV 2>/dev/null | grep -qi "unlocked\|false" \
  || log "WARNING: the phone may be locked — keep it unlocked with 自动锁定 = 永不 for the whole pass"
launch; sleep 5

log "== T1 1-min clip"
prepush t1; push "$M/singles_1min_1080p60.mp4" t1_singles_1min.mp4; launch; ensure_ingested t1
log "T1 $(wait_match t1 2400)"
evidence t1

log "== T2 10-min clip (takes ~10-20 min)"
prepush t2; push "$M/singles_10min_1080p60.mp4" t2_singles_10min.mp4; launch; ensure_ingested t2
log "T2 $(wait_match t2 3600)"
evidence t2

log "== T3 lock screen during detect"
prepush t3; push "$M/singles_1min_1080p60.mp4" t3_lock.mp4; launch; ensure_ingested t3; wait_started t3; sleep 10
ask "现在按一下手机右侧的电源键锁屏，等 1 分钟（看着手表），然后解锁手机、打开 Shuttl。"
launch
log "T3 $(wait_match t3 3600)"   # tolerates a thermal admission wait
evidence t3

log "== T4 force-kill during detect"
# 10-min clip: detect checkpoints every 120 s of video, so a kill ~180 s into detect leaves a
# detect_partial.bin to resume from (a 1-min clip never writes one).
prepush t4; push "$M/singles_10min_1080p60.mp4" t4_kill.mp4; launch; ensure_ingested t4; wait_started t4; sleep 180
pid=$(app_pid)
if [ -n "$pid" ]; then
  xcrun devicectl device process signal --device $DEV --pid "$pid" --signal SIGKILL >/dev/null 2>&1 && log "T4 killed pid $pid"
else
  log "T4 could not find the app pid (kill skipped → T4 INVALID)"
fi
sleep 5; launch
log "T4 $(wait_match t4 3600)"   # tolerates a thermal admission wait
evidence t4

log "== T5 hand-held clip"
prepush t5; push "$M/userclip/match_1790584367970.mov" t5_handheld.mov; launch; ensure_ingested t5
log "T5 $(wait_match t5 2400)"
evidence t5

log "== T6 no-shuttle clip"
prepush t6; push "$M/noshuttle_12s_1080p60.mp4" t6_noshuttle.mp4; launch; ensure_ingested t6
log "T6 $(wait_match t6 2400)"
evidence t6
sleep 120; d=$(pull t6b)   # an auto-retry would show a second run_start for the same clip

log "== T7 real tripod recording (focal hint vs solved)"
prepush t7
ask "请在真实球场（或家里地上贴好的场地线）用三脚架：约 1.6 米高、底线后约 5 米、正中间，用 Shuttl 录 30 秒，然后回到首页。"
log "T7 $(wait_match t7 1800)"
evidence t7

d=$(pull final)
"$PY" "$HERE/judge.py" report "$d" "$OUT/metrics-before.jsonl" "$OUT/tests.txt" | tee -a "$OUT/report.txt"
log "report: $OUT/report.txt"
