#!/bin/bash
# V · one-shot iPhone test pass (final phase only). v5 = v4 + launch fix + Mac sleep detection + judge fixes.
#
#   tools/device-final/run-device-tests-v5.sh <path/to/Shuttl.app> [--skip-install] [--tests t2,t3,t4,t5,t6]
#
# v5 changes from v4 (v4 is kept untouched):
#  V1. launch() FIXED: app arguments must come after `--`. Without it, devicectl reads -ShuttlOpenTab as
#      its own -t flag → "The value 'matches' is invalid for '-t <seconds>'" and exits 1. v3/v4 swallowed
#      rc + stderr, so no relaunch ever ran. Now: `… launch --terminate-existing --device $DEV $BUNDLE -- -ShuttlOpenTab matches`.
#      Log rc + stderr of launch / signal / copy-to. Retry a failed launch once. If lockState shows
#      passcodeRequired=true, prompt "请解锁手机" and wait.
#  V2. (fake xcrun) Rejects app arguments not after `--`, so the offline suite catches launch bugs.
#  V3. Wrap the whole pass in `caffeinate -dims` (self-exec) to prevent Mac sleep. Detect wall-clock gaps
#      > 3× poll interval: log "MAC SLEPT n s" and exclude that time from ingest/match timeouts.
#  V4. judge.py: KILLED timing uses the script's real kill time (recorded in kills.txt as "t4 <time>").
#      Progress lost before the first detect checkpoint (< 120 s of video) is INFO "lost-before-first-checkpoint",
#      not F-P3 FAIL (a partial should exist only after the first save). FAIL stays when a partial existed and was not loaded.
#  V5. Pre-pass check: warn if Low Power Mode or Auto-Lock are not optimal (devicectl can't read them → prompt once).
# Guards kept from v4: refuses without "[time] PHONE CONNECTED" AFTER the latest READY-FOR-PHONE; prompts only at T3 + T7;
# relaunches use `-- -ShuttlOpenTab matches`; every test waits for its own ingested row (pk > before, clip length matches);
# heartbeat every 5 min; wait reasons + thermal + checkpoint log go in report.txt.
#
# Offline self-test: V5_OFFLINE=<state dir> with fake xcrun first on PATH; see tools/device-final/tests/test-v5-offline.sh.
set -u

# V3: wrap in caffeinate if not already wrapped
if [ -z "${CAFFEINATED:-}" ]; then
  export CAFFEINATED=1
  exec caffeinate -dims "$0" "$@"
fi

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

if [ -n "${V5_OFFLINE:-}" ]; then
  # Offline self-test: xcrun MUST be the fake in tests/fake-bin, or nothing runs (exit 4).
  FAKE="$HERE/tests/fake-bin/xcrun"
  [ "$(command -v xcrun)" = "$FAKE" ] && [ "$(xcrun devicectl --t-fake-probe 2>/dev/null)" = "T-FAKE-DEVICE" ] \
    || { echo "V5_OFFLINE set but xcrun is not $FAKE — refusing (would reach a real phone)."; exit 4; }
  MONLOG="$V5_OFFLINE/monitor.log"; M="$V5_OFFLINE/clips"; OUT="$V5_OFFLINE/out"
  PROMPT="$V5_OFFLINE/prompt.txt"; GO="$V5_OFFLINE/go"; SKIP="$V5_OFFLINE/skip"
  now() { cat "$V5_OFFLINE/clock"; }
  nap() {
    local delta=$1 t0=$(now) sleep_at=${V5_MAC_SLEEP_AT:-0}
    if [ "$sleep_at" -gt 0 ] && [ "$t0" -lt "$sleep_at" ] && [ $(( t0 + delta )) -ge "$sleep_at" ]; then
      echo $(( t0 + delta + 1900 )) > "$V5_OFFLINE/clock"
    else
      echo $(( t0 + delta )) > "$V5_OFFLINE/clock"
    fi
  }
  stamp() { date -r "$(now)" +%H:%M:%S; }
  LAST_POLL="$V5_OFFLINE/last_poll"
  : > "$LAST_POLL"
else
  MONLOG="$REPO/.agent-logs/monitor.log"
  M=/tmp/shuttl-measure
  [ -f "$M/singles_10min_1080p60.mp4" ] || M="$REPO/.ui-backup/final-0930/device-clips"
  OUT=/tmp/shuttl-device-final-v5-$(date +%m%d-%H%M)
  PROMPT=/tmp/shuttl-device-prompt.txt; GO=/tmp/shuttl-device-go; SKIP=/tmp/shuttl-device-skip
  now() { date +%s; }
  nap() { sleep "$1"; }
  stamp() { date +%H:%M:%S; }
  LAST_POLL="$OUT/.last_poll"
fi
INGEST_TIMEOUT=${V5_INGEST_TIMEOUT:-600}; INGEST_POLL=15; INGEST_RELAUNCH_EVERY=3
MATCH_POLL=30; HEARTBEAT=300
MAC_SLEEP_THRESHOLD=$((INGEST_POLL * 3))  # V3: wall gap > 3× poll = Mac slept

# Guard: the latest "PHONE CONNECTED" line must come AFTER the latest READY-FOR-PHONE line.
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
log() { echo "[$(stamp)] $*" | tee -a "$OUT/report.txt" >&2; }
up() { echo "$1" | tr '[:lower:]' '[:upper:]'; }

ask() {   # text [allow_skip]
  local ans=""
  rm -f "$GO" "$SKIP"; printf '%s\n' "$1" > "$PROMPT"
  if [ -n "${V5_OFFLINE:-}" ]; then
    case "${V5_ANSWER:-go}" in skip) touch "$SKIP" ;; *) touch "$GO" ;; esac; nap 60
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

# V1: log rc + stderr; retry launch once; prompt if locked
dc_logged() {   # operation args…
  local op="$1" rc=0 err
  shift
  err=$(xcrun devicectl "$@" 2>&1 >/dev/null) || rc=$?
  [ $rc != 0 ] && log "$op rc=$rc: $(echo "$err" | head -1)"
  return $rc
}
dc_copy_to() {
  dc_logged "copy-to" device copy to --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE \
    --source "$1" --destination "$2"
}
dc_copy_from() {
  xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE \
    --source "$1" --destination "$2" >/dev/null 2>&1
}
launch() {
  local rc=0
  # V1: app args MUST come after `--`
  dc_logged "launch" device process launch --terminate-existing --device $DEV $BUNDLE -- -ShuttlOpenTab matches || rc=$?
  if [ $rc != 0 ]; then
    # V1: check lock state and retry once
    local lock_json="$OUT/.lockstate.json"
    xcrun devicectl device info lockState --device $DEV --json-output "$lock_json" >/dev/null 2>&1 || true
    if grep -q '"passcodeRequired" *: *true' "$lock_json" 2>/dev/null; then
      log "launch failed, phone is LOCKED"
      ask "请解锁手机"
    fi
    log "launch retry"
    dc_logged "launch-retry" device process launch --terminate-existing --device $DEV $BUNDLE -- -ShuttlOpenTab matches || rc=$?
  fi
  return $rc
}
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
  J report "$d" "$OUT/tests.txt" "$OUT/metrics-before.jsonl" | tee -a "$OUT/report.txt" >&2
  log "report: $OUT/report.txt"
}
prepush() {   # tag
  local d
  d=$(pull "pre-$1") || stop_pass "$1" error "could not pull the store before the push (devicectl copy from failed)"
  BEFORE_PK=$(J maxpk "$d"); BEFORE_PK=${BEFORE_PK:-0}
  log "$(up "$1") highest match pk before the push: $BEFORE_PK"
}
# V3: detect Mac sleep and exclude it from timeouts
ensure_ingested() {   # tag secs|"" timeout relaunch(1|0)
  local tag=$1 secs=$2 timeout=$3 relaunch=$4 t0 d st last="" n=0 nl=0 extra elapsed
  local sleep_total=0 last_poll
  t0=$(now)
  echo "$t0" > "$LAST_POLL"
  PIN_PK=""
  while [ $(( $(now) - t0 - sleep_total )) -lt "$timeout" ]; do
    last_poll=$(cat "$LAST_POLL" 2>/dev/null || echo "$t0")
    nap $INGEST_POLL
    d=$(pull "ing-$tag") || { log "$(up "$tag") store pull failed (poll $((n + 1))) — retrying"; }
    # V3: detect Mac sleep (after pull, so gap includes both nap and devicectl advances)
    local gap=$(( $(now) - last_poll ))
    if [ $gap -gt $MAC_SLEEP_THRESHOLD ]; then
      log "$(up "$tag") MAC SLEPT $(( gap - INGEST_POLL )) s (gap $gap s > threshold $MAC_SLEEP_THRESHOLD s)"
      sleep_total=$(( sleep_total + gap - INGEST_POLL ))
    fi
    echo "$(now)" > "$LAST_POLL"
    st=$(J status "$d" --after "$BEFORE_PK" ${secs:+--secs "$secs"})
    case "$st" in
      done*|failed*|running*)
        PIN_PK=$(echo "$st" | awk '{print $2}')
        elapsed=$(( $(now) - t0 - sleep_total ))
        log "$(up "$tag") ingested after $elapsed s ($nl relaunch(es)${sleep_total:+, $sleep_total s Mac sleep}): match $PIN_PK — $st"
        extra=$(J newrows "$d" --after "$BEFORE_PK")
        [ "$(echo "$extra" | wc -w | tr -d ' ')" -gt 1 ] && \
          log "$(up "$tag") WARNING: more than one new row since the push ($extra); pinned match $PIN_PK by clip length ${secs:-any}s"
        return 0 ;;
    esac
    [ "$st" != "$last" ] && log "$(up "$tag") $st"; last=$st
    n=$((n + 1))
    if [ "$relaunch" = 1 ] && [ $((n % INGEST_RELAUNCH_EVERY)) = 0 ]; then
      nl=$((nl + 1)); log "$(up "$tag") not ingested after $(( $(now) - t0 - sleep_total )) s — relaunch $nl (-- -ShuttlOpenTab matches) to run the inbox drain"; launch
    fi
  done
  elapsed=$(( $(now) - t0 - sleep_total ))
  log "$(up "$tag") INGEST TIMEOUT: no match row with pk > $BEFORE_PK${secs:+ and a ${secs} s clip} after $elapsed s and $nl relaunch(es)${sleep_total:+ ($sleep_total s Mac sleep)}; last: ${last:-no poll}."
  [ "$relaunch" = 1 ] && log "    Check on the phone: is Shuttl signed in (the drain only runs then) and is the file still in Documents/DebugInbox?"
  return 1
}
wait_match() {   # tag timeout
  local tag=$1 timeout=$2 t0 d="" st hb sleep_total=0 last_poll elapsed
  t0=$(now); hb=$t0; RESULT=""
  echo "$t0" > "$LAST_POLL"
  while [ $(( $(now) - t0 - sleep_total )) -lt "$timeout" ]; do
    last_poll=$(cat "$LAST_POLL" 2>/dev/null || echo "$t0")
    nap $MATCH_POLL
    # V3: detect Mac sleep
    local gap=$(( $(now) - last_poll ))
    if [ $gap -gt $MAC_SLEEP_THRESHOLD ]; then
      log "$(up "$tag") MAC SLEPT $(( gap - MATCH_POLL )) s"
      sleep_total=$(( sleep_total + gap - MATCH_POLL ))
    fi
    echo "$(now)" > "$LAST_POLL"

    d=$(pull "$tag") || continue
    st=$(J status "$d" --pk "$PIN_PK")
    case "$st" in done*|failed*) RESULT=$st; echo "$tag $st" >> "$OUT/tests.txt"; log "$(up "$tag") $st"; return 0 ;; esac
    if [ $(( $(now) - hb )) -ge $HEARTBEAT ]; then
      hb=$(now); log "$(up "$tag") … $(( $(now) - t0 - sleep_total )) s: $(J progress "$d" "$PREV_METRICS" --pk "$PIN_PK")"
    fi
  done
  RESULT="timeout"
  elapsed=$(( $(now) - t0 - sleep_total ))
  echo "$tag timeout match $PIN_PK not done/failed after ${elapsed}s" >> "$OUT/tests.txt"
  log "$(up "$tag") TIMEOUT after $elapsed s: $(J progress "$d" "$PREV_METRICS" --pk "$PIN_PK")"
  return 1
}
wait_started() {   # tag frames timeout
  local tag=$1 frames=$2 timeout=$3 t0 d=""
  t0=$(now)
  while [ $(( $(now) - t0 )) -lt "$timeout" ]; do
    nap 10
    d=$(pull "st-$tag") || continue
    [ "$(J started "$d" "$PREV_METRICS" --frames "$frames")" = yes ] && { log "$(up "$tag") detect started after $(( $(now) - t0 )) s"; return 0; }
  done
  log "$(up "$tag") detect did not start within ${timeout}s: $(J progress "$d" "$PREV_METRICS" --pk "$PIN_PK")"; return 1
}
evidence() {   # tag
  local d="$OUT/pull-$1"
  # V4: pass tests.txt for kill time
  J evidence "$d" "$PREV_METRICS" "$1" ${PIN_PK:+--pk "$PIN_PK"} "$OUT/tests.txt" | tee -a "$OUT/report.txt" >&2
  [ -s "$d/stage-metrics.jsonl" ] && { cp "$d/stage-metrics.jsonl" "$OUT/metrics-after-$1.jsonl"; PREV_METRICS="$OUT/metrics-after-$1.jsonl"; }
}
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

# V5: warn about Low Power Mode and Auto-Lock (devicectl can't read them)
if [ -z "${V5_OFFLINE:-}" ]; then
  log "Pre-pass check: please ensure 自动锁定 = 永不 and 低电量模式 = OFF for the whole pass"
  ask "请确认：自动锁定设为永不、低电量模式已关闭"
fi

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
  wait_match t3 3600; evidence t3
  [ -n "$T3_BAD" ] && { log "T3 INVALID: $T3_BAD"; echo "t3 invalid $T3_BAD" >> "$OUT/tests.txt"; }
fi

if selected t4; then
  log "== T4 force-kill during detect"
  pushed_test t4 singles_10min_1080p60.mp4 t4_kill.mp4 600
  T4_BAD=""
  if wait_started t4 35999 3600; then
    nap 180
    pid=$(app_pid)
    if [ -n "$pid" ]; then
      # V4: record kill time in tests.txt for judge
      if dc_logged "signal" device process signal --device $DEV --pid "$pid" --signal SIGKILL; then
        log "T4 killed pid $pid"
        echo "t4 $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/kills.txt"
      else
        T4_BAD="SIGKILL of pid $pid failed"
      fi
    else
      T4_BAD="could not find the app pid (kill skipped)"
    fi
    nap 5; launch
  else
    T4_BAD="detect never started, so nothing was killed"
  fi
  wait_match t4 3600; evidence t4
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
  nap 120; d=$(pull t6b)
fi

if selected t7; then
  log "== T7 real tripod recording (focal hint vs solved)"
  prepush t7
  if ask "请在真实球场（或家里地上贴好的场地线）用三脚架：约 1.6 米高、底线后约 5 米、正中间，用 Shuttl 录 30 秒，然后回到首页。现在不在球场就输入 skip。" allow_skip; then
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
