#!/bin/bash
# OFFLINE self-test of run-device-tests-v4.sh: a fake xcrun (tests/fake-bin) replays the saved 09-30
# evidence on a virtual clock. No phone, no real devicectl. Each scenario's state stays in /tmp/T-v4-<name>.
#
#   bash tools/device-final/tests/test-v4-offline.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
V4="$HERE/../run-device-tests-v4.sh"
PY="$HOME/Downloads/华北五省/backend/.venv/bin/python"
export TZ=Asia/Shanghai T_FAKE_PY="$PY"
START=$("$PY" -c 'from datetime import datetime,timezone; print(int(datetime(2026,9,30,9,16,30,tzinfo=timezone.utc).timestamp()))')
FAILS=0
ok()  { echo "  ok   $1"; }
bad() { echo "  FAIL $1"; FAILS=$((FAILS + 1)); }
has()   { grep -qF -- "$2" "$1" && ok "has: $2" || bad "missing: $2  (in $1)"; }
hasnt() { grep -qF -- "$2" "$1" && bad "must not have: $2  (in $1)" || ok "has not: $2"; }

setup() {   # name scenario monitor-log-text
  S=/tmp/T-v4-$1; rm -rf "$S"; mkdir -p "$S/clips/userclip" "$S/app/Shuttl.app"
  echo "$START" > "$S/clock"; echo "$2" > "$S/scenario"; printf '%s\n' "$3" > "$S/monitor.log"
  for f in singles_1min_1080p60.mp4 singles_10min_1080p60.mp4 noshuttle_12s_1080p60.mp4 userclip/match_1790584367970.mov; do
    echo "dummy clip" > "$S/clips/$f"
  done
}
MON_OK='[17:10] A READY-FOR-PHONE (fix round)
[17:14] MONITOR APPROVES A READY-FOR-PHONE
[17:16] PHONE CONNECTED (re-pass): wired'
run() {   # extra args…; sets RC
  PATH="$HERE/fake-bin:/usr/bin:/bin:/usr/sbin:/sbin" V4_OFFLINE="$S" bash "$V4" "$S/app/Shuttl.app" "$@" > "$S/stdout.txt" 2> "$S/stderr.txt"
  RC=$?
}

echo "== A. replay of the 09-30 T2 race (T1 + T2)"
setup replay replay "$MON_OK"; run --tests t1,t2
R="$S/out/report.txt"
[ $RC = 0 ] && ok "exit 0" || bad "exit $RC"
has "$R" "T1 done 17 60s"
has "$R" "T2 highest match pk before the push: 17"
has "$R" "T2 waiting-ingest after 17 of 600s"
has "$R" "relaunch 1 (-ShuttlOpenTab matches)"
has "$R" "T2 ingested after"
has "$R" "match 19 — running 19 analyzing"
has "$R" "WARNING: more than one new row since the push (18=60s 19=600s); pinned match 19"
has "$R" "T2 done 19 600s"
hasnt "$R" "T2 done 17"
has "$R" "admission_wait busy 09:25:19→09:26:14 55.5s"
has "$R" "CANCELLED detect after 8.4s at 09:17:07"
has "$R" "LOST DETECT PROGRESS (F-P3)"
has "$R" "PASS T1 1-min: match 17 done"
has "$R" "PASS T2 10-min: match 19 done"
has "$R" "SKIP T3 lock"
has "$S/calls.log" "launch --terminate-existing --device 0F92DDA9-7A87-4F05-8368-0E834177D8F3 com.ycyangcong.shuttl -ShuttlOpenTab matches"
hasnt "$S/calls.log" "UNKNOWN"
grep -E "ingested after|T2 done|INGEST" "$R" | sed 's/^/     /'

echo "== B. the row never appears → INGEST TIMEOUT stops the pass"
setup never never "$MON_OK"; V4_INGEST_TIMEOUT=120 run --tests t1,t2,t3
R="$S/out/report.txt"
[ $RC = 5 ] && ok "exit 5 (pass stopped)" || bad "exit $RC"
has "$R" "T2 INGEST TIMEOUT: no match row with pk > 17 and a 600 s clip after 120 s"
has "$R" "PASS STOPPED at T2"
has "$R" "FAIL T2 10-min: not-ingested"
has "$R" "FAIL T3 lock: not-run pass stopped at t2"
hasnt "$R" "T2 done"

echo "== C. T7 not at a court → PENDING, not FAIL"
setup t7 replay "$MON_OK"; V4_ANSWER=skip run --tests t7 --skip-install
R="$S/out/report.txt"
[ $RC = 0 ] && ok "exit 0" || bad "exit $RC"
has "$R" "SKIPPED by the user"
has "$R" "PENDING T7 tripod: the user is not at a court"
hasnt "$R" "FAIL T7"
hasnt "$S/calls.log" "install"

echo "== D. guards (no device call may happen)"
setup g1 replay '[10:09] PHONE CONNECTED
[17:10] A READY-FOR-PHONE (fix round)'; run --tests t1
[ $RC = 3 ] && ok "PHONE CONNECTED older than READY-FOR-PHONE → exit 3" || bad "exit $RC"
[ -e "$S/calls.log" ] && bad "device was called" || ok "no device call"
setup g2 replay '[17:10] A READY-FOR-PHONE
nobody touches the phone until this file has a line "PHONE CONNECTED".'; run --tests t1
[ $RC = 3 ] && ok "only a prose mention of PHONE CONNECTED → exit 3" || bad "exit $RC"
setup g3 replay "$MON_OK"
PATH="/usr/bin:/bin" V4_OFFLINE="$S" bash "$V4" "$S/app/Shuttl.app" > /dev/null 2>&1; RC=$?
[ $RC = 4 ] && ok "V4_OFFLINE without the fake xcrun → exit 4 before any guard or device call" || bad "exit $RC"

echo
[ $FAILS = 0 ] && echo "ALL OFFLINE v4 CHECKS PASSED" || echo "$FAILS CHECK(S) FAILED"
exit $FAILS
