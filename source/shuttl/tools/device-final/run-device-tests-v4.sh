#!/bin/bash
# T · one-shot iPhone test pass (final phase only). v4 = v3 + a deterministic ingest (09-30 17:16 re-pass bug).
#
#   tools/device-final/run-device-tests-v4.sh <path/to/Shuttl.app> [--skip-install] [--tests t2,t3,t4,t5,t6]
#
# v4 changes (v3 is kept untouched):
#  - Each pushed test notes the highest match Z_PK first, then accepts ONLY a row with pk > that AND the
#    pushed clip's length (judge.py status --after <pk> --secs <s>). On 09-30 the newest row was still T1's
#    match 17 → "T2 done 17"; and the drain takes the inbox oldest-mtime first, so t3_lock (pushed later)
#    became 18 and T2 19 → "first pk > before" alone would also have been wrong.
#  - Deterministic ingest: the drain only runs on launch / scene-active / thermal→run, so after a push the
#    script polls the pulled store every 15 s and relaunches (-ShuttlOpenTab matches) every 3rd poll until
#    the row exists, then pins that pk for the rest of the test. No row in 600 s → the pass STOPS with an
#    "INGEST TIMEOUT" line (a late ingest would otherwise be read as the next test's row).
#  - The next clip is pushed only after the previous test has finished, so the inbox never holds two.
#  - Evidence per test (judge.py evidence): thermal, admission_wait, analysis_paused/resumed (workstream Q),
#    cancelled / failed stages, pause gaps (UNLOGGED when nothing explains them), wasted stages after a
#    failure, lost detect progress (F-P3). A 5-min heartbeat while a test runs.
#  - T3 uses the 10-min clip, so detect is still running when the user locks (the 1-min detect takes 17 s).
#  - T7 is PENDING, not FAIL, when the user is not at a court (answer "skip").
#  - push retries once; a failed store pull never reads as "done".
# Guards kept from v3: refuses to run unless .agent-logs/monitor.log has a "PHONE CONNECTED" line AFTER the
# latest READY-FOR-PHONE line; the user is prompted only at T3 (lock) and T7 (court recording); every relaunch
# lands on 比赛; wait reasons and thermal state go into report.txt.
#
# Offline self-test (never touches a phone): V4_OFFLINE=<state dir> with a fake xcrun first on PATH; see
# tools/device-final/tests/test-v4-offline.sh.
set -u
REPO="$HOME/Downloads/华北五省"
DEV=0F92DDA9-7A87-4F05-8368-0E834177D8F3
BUNDLE=com.ycyangcong.shuttl
PY="$REPO/backend/.venv/bin/python"
HERE="$(cd "$(dirname "$0")" && pwd)"
ORDER="t1 t2 t3 t4 t5 t6 t7"

APP=""; SKIP_INSTALL=0; TESTS="t1,t2,t3,t4,t5,t6,t7"
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-install) SKIP_INSTALL=1 ;;
    --tests) TESTS="${2:-}"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) APP="$1" ;;
  esac
  shift
done
selected() { case ",$TESTS," in *",$1,"*) return 0 ;; esac; return 1; }

if [ -n "${V4_OFFLINE:-}" ]; then
  # Offline self-test: xcrun MUST be the fake in tests/fake-bin, or nothing runs (exit 4).
  FAKE="$HERE/tests/fake-bin/xcrun"
  [ "$(command -v xcrun)" = "$FAKE" ] && [ "$(xcrun devicectl --t-fake-probe 2>/dev/null)" = "T-FAKE-DEVICE" ] \
    || { echo "V4_OFFLINE set but xcrun is not $FAKE — refusing (would reach a real phone)."; exit 4; }
  MONLOG="$V4_OFFLINE/monitor.log"; M="$V4_OFFLINE/clips"; OUT="$V4_OFFLINE/out"
  PROMPT="$V4_OFFLINE/prompt.txt"; GO="$V4_OFFLINE/go"; SKIP="$V4_OFFLINE/skip"
  now() { cat "$V4_OFFLINE/clock"; }
  nap() { echo $(( $(now) + $1 )) > "$V4_OFFLINE/clock"; }
  stamp() { date -r "$(now)" +%H:%M:%S; }
else
  MONLOG="$REPO/.agent-logs/monitor.log"
  M=/tmp/shuttl-measure
  [ -f "$M/singles_10min_1080p60.mp4" ] || M="$REPO/.ui-backup/final-0930/device-clips"   # durable copy (/tmp is wiped on reboot)
  OUT=/tmp/shuttl-device-final-v4-$(date +%m%d-%H%M)
  PROMPT=/tmp/shuttl-device-prompt.txt; GO=/tmp/shuttl-device-go; SKIP=/tmp/shuttl-device-skip
  now() { date +%s; }
  nap() { sleep "$1"; }
  stamp() { date +%H:%M:%S; }
fi
INGEST_TIMEOUT=${V4_INGEST_TIMEOUT:-600}; INGEST_POLL=15; INGEST_RELAUNCH_EVERY=3
MATCH_POLL=30; HEARTBEAT=300

# Guard: the latest "PHONE CONNECTED" line (a line that starts with it after its [time]) must come AFTER the
# latest line mentioning READY-FOR-PHONE, i.e. the monitor connected the phone for the build now on offer.
phone_guard() {
  local rfp pc
  [ -f "$MONLOG" ] || { echo "no $MONLOG — not allowed to touch the phone."; return 1; }
  rfp=$(grep -n "READY-FOR-PHONE" "$MONLOG" | tail -1 | cut -d: -f1)
  pc=$(grep -nE '^\[[^]]*\] PHONE CONNECTED' "$MONLOG" | tail -1 | cut -d: -f1)
  [ -n "$pc" ] || { echo "monitor.log has no '[time] PHONE CONNECTED' line — not allowed to touch the phone yet."; return 1; }
  if [ -n "$rfp" ] && [ "$pc" -lt "$rfp" ]; then
    echo "monitor.log: latest PHONE CONNECTED (line $pc) is older than the latest READY-FOR-PHONE (line $rfp)."
    echo "The monitor must write a new '[time] PHONE CONNECTED' line for this build first. Not touching the phone."
    return 1
  fi
  return 0
}
phone_guard || exit 3
[ -n "$APP" ] && [ -d "$APP" ] || { echo "usage: $0 <Shuttl.app> [--skip-install] [--tests t1,t2,…]"; exit 2; }
clip_for() {
  case "$1" in
    t1) echo singles_1min_1080p60.mp4 ;; t2|t3|t4) echo singles_10min_1080p60.mp4 ;;
    t5) echo userclip/match_1790584367970.mov ;; t6) echo noshuttle_12s_1080p60.mp4 ;;
  esac
}
for t in $ORDER; do
  selected "$t" || continue
  f=$(clip_for "$t"); [ -z "$f" ] || [ -f "$M/$f" ] || { echo "missing clip $M/$f"; exit 2; }
done
mkdir -p "$OUT"
# Log lines go to report.txt and stderr, so functions used inside $(…) never swallow them.
log() { echo "[$(stamp)] $*" | tee -a "$OUT/report.txt" >&2; }
up() { echo "$1" | tr '[:lower:]' '[:upper:]'; }

# A prompt goes to the terminal AND to $PROMPT (so the monitor can relay it to the user in chat).
# It continues on Enter in the terminal or when $GO exists; with allow_skip, typing "skip" or touching
# $SKIP returns 1. Without a terminal it sleeps between checks (v3 spun on read's EOF).
ask() {   # text [allow_skip]
  local ans=""
  rm -f "$GO" "$SKIP"; printf '%s\n' "$1" > "$PROMPT"
  if [ -n "${V4_OFFLINE:-}" ]; then
    case "${V4_ANSWER:-go}" in skip) touch "$SKIP" ;; *) touch "$GO" ;; esac; nap 60
  fi
  if [ "${2:-}" = allow_skip ]; then
    printf '\a\n>>> %s\n    做完后按回车继续；不在球场就输入 skip 回车（或 touch %s / %s）…' "$1" "$GO" "$SKIP" >&2
  else
    printf '\a\n>>> %s\n    做完后按回车继续（或 touch %s）…' "$1" "$GO" >&2
  fi
  while [ ! -e "$GO" ] && [ ! -e "$SKIP" ]; do
    if [ -t 0 ]; then
      if read -r -t 5 ans; then
        [ "$ans" = skip ] && [ "${2:-}" = allow_skip ] && touch "$SKIP"
        [ -e "$SKIP" ] || touch "$GO"
      fi
    else
      sleep 5
    fi
  done
  local rc=0; [ -e "$SKIP" ] && [ "${2:-}" = allow_skip ] && rc=1
  rm -f "$GO" "$SKIP" "$PROMPT"; echo >&2
  if [ $rc = 0 ]; then log "continued: $1"; else log "SKIPPED by the user: $1"; fi
  return $rc
}

dc_copy_to() { xcrun devicectl device copy to --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE \
                 --source "$1" --destination "$2" >/dev/null 2>&1; }
dc_copy_from() { xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE \
                   --source "$1" --destination "$2" >/dev/null 2>&1; }
# Relaunches open on 比赛 (-ShuttlOpenTab), so they never land on the live camera; launch runs resumePending,
# which is what drains Documents/DebugInbox.
launch() { xcrun devicectl device process launch --terminate-existing --device $DEV $BUNDLE -ShuttlOpenTab matches >/dev/null 2>&1; }
app_pid() {
  xcrun devicectl device info processes --device $DEV --json-output "$OUT/procs.json" >/dev/null 2>&1
  "$PY" - "$OUT/procs.json" <<'EOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for p in d.get("result", {}).get("runningProcesses", []):
    if "Shuttl.app/" in (p.get("executable") or ""):
        print(p["processIdentifier"]); break
EOF
}
# Metrics + store into a FRESH dir, swapped into $OUT/pull-<tag> (a stale -wal next to a new store, or last
# poll's store after a failed copy, must never be read). Prints the dir; returns 1 if the store did not copy.
pull() {
  local d="$OUT/pull-$1" tmp="$OUT/.pull-$1.tmp" ok=0 s
  rm -rf "$tmp"; mkdir -p "$tmp"
  dc_copy_from Documents/Diagnostics/stage-metrics.jsonl "$tmp/stage-metrics.jsonl"
  for s in default.store default.store-wal default.store-shm; do
    dc_copy_from "Library/Application Support/$s" "$tmp/$s" || { [ $s = default.store ] && ok=1; }
  done
  [ -s "$tmp/default.store" ] || ok=1
  rm -rf "$d"; mv "$tmp" "$d"
  echo "$d"; return $ok
}
push() {   # src dest-name
  local i
  for i in 1 2; do
    dc_copy_to "$1" "Documents/DebugInbox/$2" && { log "pushed $2 ($(du -h "$1" | cut -f1))"; return 0; }
    log "push of $2 failed (try $i)"; nap 10
  done
  return 1
}

J() { "$PY" "$HERE/judge.py" "$@" 2>/dev/null; }
BEFORE_PK=0; PIN_PK=""; RESULT=""
PREV_METRICS="$OUT/metrics-before.jsonl"

# Everything below runs in the main shell (never inside $(…)), so BEFORE_PK / PIN_PK / RESULT stick
# and stop_pass can really exit.
stop_pass() {   # tag word why…
  local tag=$1 word=$2 t hit=0; shift 2
  log "PASS STOPPED at $(up "$tag"): $*"
  echo "$tag $word $*" >> "$OUT/tests.txt"
  for t in $ORDER; do
    [ "$t" = "$tag" ] && { hit=1; continue; }
    [ $hit = 1 ] && selected "$t" && echo "$t not-run pass stopped at $tag" >> "$OUT/tests.txt"
  done
  finish; exit 5
}
finish() {
  local t d
  for t in $ORDER; do selected "$t" || echo "$t skip not selected (--tests $TESTS)" >> "$OUT/tests.txt"; done
  d=$(pull final) || { log "final pull failed — reporting from the last good pull"; d=$(ls -dt "$OUT"/pull-* 2>/dev/null | head -1); }
  log "== REPORT"
  J report "$d" "$OUT/metrics-before.jsonl" "$OUT/tests.txt" | tee -a "$OUT/report.txt" >&2
  log "report: $OUT/report.txt"
}
prepush() {   # tag: the highest pk right before the push
  local d
  d=$(pull "pre-$1") || stop_pass "$1" error "could not pull the store before the push (devicectl copy from failed)"
  BEFORE_PK=$(J maxpk "$d"); BEFORE_PK=${BEFORE_PK:-0}
  log "$(up "$1") highest match pk before the push: $BEFORE_PK"
}
# Poll the pulled store until this test's row (pk > BEFORE_PK, clip length SECS) exists; relaunch every
# 3rd poll so the drain runs. Pins PIN_PK. Returns 1 on timeout (the caller stops the pass).
ensure_ingested() {   # tag secs|"" timeout relaunch(1|0)
  local tag=$1 secs=$2 timeout=$3 relaunch=$4 t0 d st last="" n=0 nl=0 extra
  t0=$(now); PIN_PK=""
  while [ $(( $(now) - t0 )) -lt "$timeout" ]; do
    nap $INGEST_POLL
    d=$(pull "ing-$tag") || { log "$(up "$tag") store pull failed (poll $((n + 1))) — retrying"; }
    st=$(J status "$d" --after "$BEFORE_PK" ${secs:+--secs "$secs"})
    case "$st" in
      done*|failed*|running*)
        PIN_PK=$(echo "$st" | awk '{print $2}')
        log "$(up "$tag") ingested after $(( $(now) - t0 )) s ($nl relaunch(es)): match $PIN_PK — $st"
        extra=$(J newrows "$d" --after "$BEFORE_PK")
        [ "$(echo "$extra" | wc -w | tr -d ' ')" -gt 1 ] && \
          log "$(up "$tag") WARNING: more than one new row since the push ($extra); pinned match $PIN_PK by clip length ${secs:-any}s"
        return 0 ;;
    esac
    [ "$st" != "$last" ] && log "$(up "$tag") $st"; last=$st
    n=$((n + 1))
    if [ "$relaunch" = 1 ] && [ $((n % INGEST_RELAUNCH_EVERY)) = 0 ]; then
      nl=$((nl + 1)); log "$(up "$tag") not ingested after $(( $(now) - t0 )) s — relaunch $nl (-ShuttlOpenTab matches) to run the inbox drain"; launch
    fi
  done
  log "$(up "$tag") INGEST TIMEOUT: no match row with pk > $BEFORE_PK${secs:+ and a ${secs} s clip} after ${timeout} s and $nl relaunch(es); last: ${last:-no poll}."
  [ "$relaunch" = 1 ] && log "    Check on the phone: is Shuttl signed in (the drain only runs then) and is the file still in Documents/DebugInbox?"
  return 1
}
# Wait for the pinned row to reach done/failed. Sets RESULT; appends "<tag> <status…>" to tests.txt.
wait_match() {   # tag timeout
  local tag=$1 timeout=$2 t0 d="" st hb
  t0=$(now); hb=$t0; RESULT=""
  while [ $(( $(now) - t0 )) -lt "$timeout" ]; do
    nap $MATCH_POLL
    d=$(pull "$tag") || continue
    st=$(J status "$d" --pk "$PIN_PK")
    case "$st" in done*|failed*) RESULT=$st; echo "$tag $st" >> "$OUT/tests.txt"; log "$(up "$tag") $st"; return 0 ;; esac
    if [ $(( $(now) - hb )) -ge $HEARTBEAT ]; then
      hb=$(now); log "$(up "$tag") … $(( $(now) - t0 )) s: $(J progress "$d" "$PREV_METRICS" --pk "$PIN_PK")"
    fi
  done
  RESULT="timeout"
  echo "$tag timeout match $PIN_PK not done/failed after ${timeout}s" >> "$OUT/tests.txt"
  log "$(up "$tag") TIMEOUT after ${timeout} s: $(J progress "$d" "$PREV_METRICS" --pk "$PIN_PK")"
  return 1
}
wait_started() {   # tag frames timeout: until THIS clip's detect run has started (admission may hold it)
  local tag=$1 frames=$2 timeout=$3 t0 d=""
  t0=$(now)
  while [ $(( $(now) - t0 )) -lt "$timeout" ]; do
    nap 10
    d=$(pull "st-$tag") || continue
    [ "$(J started "$d" "$PREV_METRICS" --frames "$frames")" = yes ] && { log "$(up "$tag") detect started after $(( $(now) - t0 )) s"; return 0; }
  done
  log "$(up "$tag") detect did not start within ${timeout}s: $(J progress "$d" "$PREV_METRICS" --pk "$PIN_PK")"; return 1
}
# Per-test evidence since the previous test: thermal, waits, pauses, interruptions, stage times.
evidence() {   # tag
  local d="$OUT/pull-$1"
  J evidence "$d" "$PREV_METRICS" "$1" ${PIN_PK:+--pk "$PIN_PK"} | tee -a "$OUT/report.txt" >&2
  [ -s "$d/stage-metrics.jsonl" ] && { cp "$d/stage-metrics.jsonl" "$OUT/metrics-after-$1.jsonl"; PREV_METRICS="$OUT/metrics-after-$1.jsonl"; }
}
# Push one clip and pin its row: prepush → push → launch → ensure_ingested (or stop the pass).
pushed_test() {   # tag clip dest secs
  local tag=$1
  prepush "$tag"
  push "$M/$2" "$3" || stop_pass "$tag" error "push of $3 failed twice"
  PUSHED_AT=$(now); launch
  ensure_ingested "$tag" "$4" "$INGEST_TIMEOUT" 1 || stop_pass "$tag" not-ingested "no row for $3 (${4}s) within ${INGEST_TIMEOUT}s"
}

xcrun devicectl list devices 2>&1 | grep "$DEV" | grep -v unavailable | grep -qE "available|connected" \
  || { log "phone not available (unlocked + trusted + cable?)"; exit 1; }
log "OUT=$OUT  app=$APP  tests=$TESTS"
if [ $SKIP_INSTALL = 0 ]; then
  xcrun devicectl device install app --device $DEV "$APP" 2>&1 | grep -E "bundleID|rror" | tee -a "$OUT/report.txt" >&2
fi
dc_copy_from Documents/Diagnostics/stage-metrics.jsonl "$OUT/metrics-before.jsonl" || : > "$OUT/metrics-before.jsonl"
: > "$OUT/tests.txt"
xcrun devicectl device info lockState --device $DEV 2>/dev/null | grep -qi "unlocked\|false" \
  || log "WARNING: the phone may be locked — keep it unlocked with 自动锁定 = 永不 for the whole pass"
launch; nap 5

if selected t1; then
  log "== T1 1-min clip"
  pushed_test t1 singles_1min_1080p60.mp4 t1_singles_1min.mp4 60
  wait_match t1 2400; evidence t1
fi

if selected t2; then
  log "== T2 10-min clip (takes ~10-20 min)"
  pushed_test t2 singles_10min_1080p60.mp4 t2_singles_10min.mp4 600
  wait_match t2 3600; evidence t2
fi

if selected t3; then
  log "== T3 lock screen during detect (10-min clip, so detect is still running when the user locks)"
  pushed_test t3 singles_10min_1080p60.mp4 t3_lock.mp4 600
  T3_BAD=""
  if wait_started t3 35999 3600; then
    nap 20
    d=$(pull "t3-prelock"); st=$(J status "$d" --pk "$PIN_PK")
    case "$st" in done*|failed*) T3_BAD="match $PIN_PK had already ended ($st) before the lock prompt" ;; esac
    log "T3 lock window opens (prompt shown): $(J progress "$d" "$PREV_METRICS" --pk "$PIN_PK")"
    ask "现在按一下手机右侧的电源键锁屏，等 1 分钟（看着手表），然后解锁手机、打开 Shuttl。"
    log "T3 lock window closed (user confirmed unlock)"
    launch
  else
    T3_BAD="detect never started, so the lock did not hit a running analysis"
  fi
  wait_match t3 3600; evidence t3   # tolerates a thermal admission wait
  [ -n "$T3_BAD" ] && { log "T3 INVALID: $T3_BAD"; echo "t3 invalid $T3_BAD" >> "$OUT/tests.txt"; }
fi

if selected t4; then
  log "== T4 force-kill during detect"
  # 10-min clip: detect checkpoints every 120 s of video, so a kill ~180 s into detect leaves a
  # detect_partial.bin to resume from (a 1-min clip never writes one).
  pushed_test t4 singles_10min_1080p60.mp4 t4_kill.mp4 600
  T4_BAD=""
  if wait_started t4 35999 3600; then
    nap 180
    pid=$(app_pid)
    if [ -n "$pid" ]; then
      xcrun devicectl device process signal --device $DEV --pid "$pid" --signal SIGKILL >/dev/null 2>&1 \
        && log "T4 killed pid $pid" || T4_BAD="SIGKILL of pid $pid failed"
    else
      T4_BAD="could not find the app pid (kill skipped)"
    fi
    nap 5; launch
  else
    T4_BAD="detect never started, so nothing was killed"
  fi
  wait_match t4 3600; evidence t4   # tolerates a thermal admission wait
  [ -n "$T4_BAD" ] && { log "T4 INVALID: $T4_BAD"; echo "t4 invalid $T4_BAD" >> "$OUT/tests.txt"; }
fi

if selected t5; then
  log "== T5 hand-held clip"
  pushed_test t5 userclip/match_1790584367970.mov t5_handheld.mov 10.87
  wait_match t5 2400; evidence t5
fi

if selected t6; then
  log "== T6 no-shuttle clip"
  pushed_test t6 noshuttle_12s_1080p60.mp4 t6_noshuttle.mp4 12
  wait_match t6 2400; evidence t6
  nap 120; d=$(pull t6b)   # an auto-retry would show a second run_start for the same clip (report checks it)
fi

if selected t7; then
  log "== T7 real tripod recording (focal hint vs solved)"
  prepush t7
  if ask "请在真实球场（或家里地上贴好的场地线）用三脚架：约 1.6 米高、底线后约 5 米、正中间，用 Shuttl 录 30 秒，然后回到首页。现在不在球场就输入 skip。" allow_skip; then
    # Recorded in the app (not pushed): wait for the new row without relaunching, so a take is never killed.
    if ensure_ingested t7 "" 900 0; then
      wait_match t7 1800; evidence t7
    else
      echo "t7 pending no new recording appeared within 900 s of the prompt" >> "$OUT/tests.txt"
    fi
  else
    echo "t7 pending the user is not at a court (answered skip); re-run with --tests t7 at a court" >> "$OUT/tests.txt"
  fi
fi

finish
