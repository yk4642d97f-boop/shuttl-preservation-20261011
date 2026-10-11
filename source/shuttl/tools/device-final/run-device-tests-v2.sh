#!/bin/bash
# B · one-shot iPhone test pass (final phase only). v2: prompts relayable via /tmp/shuttl-device-prompt.txt + /tmp/shuttl-device-go. Writes a report to $OUT/report.txt.
#
#   tools/device-final/run-device-tests.sh <path/to/Shuttl.app> [--skip-install]
#
# Refuses to run until .agent-logs/monitor.log contains "PHONE CONNECTED" (monitor's rule, 09-28 22:50).
# Tests, in order (each one is judged from Documents/Diagnostics/stage-metrics.jsonl and the app's
# SwiftData store, both pulled with devicectl):
#   T1  1-min 1080p60 clip          → done, per-stage seconds, peak MB, thermal, compute plan (ANE)
#   T2  10-min 1080p60 clip         → done, total ≲ 1× real time, peak MB, thermal
#   T3  lock screen during detect   → user presses the side button; after unlock the run resumes and ends done
#   T4  force-kill during detect    → SIGKILL at ~40 % of detect; relaunch → detect_resume > 0 → done
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
launch() { xcrun devicectl device process launch --terminate-existing --device $DEV $BUNDLE >/dev/null 2>&1; }
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
# Wait until the newest match row is done/failed (or timeout seconds). Prints the final row.
wait_match() {
  local tag=$1 timeout=$2 t0=$SECONDS d
  while [ $((SECONDS - t0)) -lt "$timeout" ]; do
    sleep 30
    d=$(pull "$tag")
    st=$("$PY" "$HERE/judge.py" status "$d" 2>/dev/null)
    case "$st" in done*|failed*) echo "$tag $st" >> "$OUT/tests.txt"; echo "$st"; return 0;; esac
  done
  echo "timeout"; return 1
}

log "OUT=$OUT  app=$APP"
if [ $SKIP_INSTALL = 0 ]; then
  xcrun devicectl device install app --device $DEV "$APP" 2>&1 | grep -E "bundleID|rror" | tee -a "$OUT/report.txt"
fi
dc_copy_from Documents/Diagnostics/stage-metrics.jsonl "$OUT/metrics-before.jsonl"   # baseline line count
launch; sleep 5

ask "请把手机解锁，打开 Shuttl，停在首页。整个测试期间手机插着电源线、不要锁屏（除非脚本让你锁）。"

log "== T1 1-min clip"
push "$M/singles_1min_1080p60.mp4" t1_singles_1min.mp4; launch
log "T1 $(wait_match t1 900)"

log "== T2 10-min clip (takes ~10-20 min)"
push "$M/singles_10min_1080p60.mp4" t2_singles_10min.mp4; launch
log "T2 $(wait_match t2 3600)"

log "== T3 lock screen during detect"
push "$M/singles_1min_1080p60.mp4" t3_lock.mp4; launch; sleep 25
ask "现在按一下手机右侧的电源键锁屏，等 1 分钟（看着手表），然后解锁手机、打开 Shuttl。"
launch
log "T3 $(wait_match t3 1200)"

log "== T4 force-kill during detect"
push "$M/singles_1min_1080p60.mp4" t4_kill.mp4; launch; sleep 20
pid=$(app_pid)
if [ -n "$pid" ]; then
  xcrun devicectl device process signal --device $DEV --pid "$pid" --signal SIGKILL >/dev/null 2>&1 && log "T4 killed pid $pid"
else
  log "T4 could not find the app pid (kill skipped → T4 INVALID)"
fi
sleep 5; launch
log "T4 $(wait_match t4 1200)"

log "== T5 hand-held clip"
push "$M/userclip/match_1790584367970.mov" t5_handheld.mov; launch
log "T5 $(wait_match t5 600)"

log "== T6 no-shuttle clip"
push "$M/noshuttle_12s_1080p60.mp4" t6_noshuttle.mp4; launch
log "T6 $(wait_match t6 600)"
sleep 120; d=$(pull t6b)   # an auto-retry would show a second run_start for the same clip

log "== T7 real tripod recording (focal hint vs solved)"
ask "请在真实球场（或家里地上贴好的场地线）用三脚架：约 1.6 米高、底线后约 5 米、正中间，用 Shuttl 录 30 秒，然后回到首页。"
log "T7 $(wait_match t7 1800)"

d=$(pull final)
"$PY" "$HERE/judge.py" report "$d" "$OUT/metrics-before.jsonl" "$OUT/tests.txt" | tee -a "$OUT/report.txt"
log "report: $OUT/report.txt"
