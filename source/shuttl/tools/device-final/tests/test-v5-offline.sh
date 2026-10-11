#!/bin/bash
# OFFLINE self-test of run-device-tests-v5.sh: fake xcrun, virtual clock, no phone.
# V5 changes: launch with `--`, Mac sleep detection, judge fixes (kill time, lost-before-first-checkpoint).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
V5="$HERE/../run-device-tests-v5.sh"
PY="$HOME/Downloads/华北五省/backend/.venv/bin/python"
export TZ=Asia/Shanghai T_FAKE_PY="$PY"
START=$("$PY" -c 'from datetime import datetime,timezone; print(int(datetime(2026,9,30,9,16,30,tzinfo=timezone.utc).timestamp()))')
FAILS=0
ok()  { echo "  ok   $1"; }
bad() { echo "  FAIL $1"; FAILS=$((FAILS + 1)); }
has()   { grep -qF -- "$2" "$1" && ok "has: $2" || bad "missing: $2  (in $1)"; }
hasnt() { grep -qF -- "$2" "$1" && bad "must not have: $2  (in $1)" || ok "has not: $2"; }

setup() {   # name scenario monitor-log-text
  S=/tmp/T-v5-$1; rm -rf "$S"; mkdir -p "$S/clips/userclip" "$S/app/Shuttl.app"
  echo "$START" > "$S/clock"; echo "$2" > "$S/scenario"; printf '%s\n' "$3" > "$S/monitor.log"
  for f in singles_1min_1080p60.mp4 singles_10min_1080p60.mp4 noshuttle_12s_1080p60.mp4 userclip/match_1790584367970.mov; do
    echo "dummy clip" > "$S/clips/$f"
  done
}
MON_OK='[17:10] A READY-FOR-PHONE (fix round)
[17:14] MONITOR APPROVES A READY-FOR-PHONE
[17:16] PHONE CONNECTED (re-pass): wired'
run() {   # extra args…; sets RC
  PATH="$HERE/fake-bin:/usr/bin:/bin:/usr/sbin:/sbin" V5_OFFLINE="$S" bash "$V5" "$S/app/Shuttl.app" "$@" > "$S/stdout.txt" 2> "$S/stderr.txt"
  RC=$?
}

echo "== A. replay with v5 (launch fix, Mac sleep detection)"
setup replay replay "$MON_OK"; run --tests t1,t2
R="$S/out/report.txt"
[ $RC = 0 ] && ok "exit 0" || bad "exit $RC"
has "$R" "T1 done 17 60s"
has "$R" "T2 highest match pk before the push: 17"
has "$R" "T2 ingested after"
has "$R" "match 19 — running 19 analyzing"
has "$R" "T2 done 19 600s"
hasnt "$R" "T2 done 17"
has "$S/calls.log" "launch --terminate-existing --device 0F92DDA9-7A87-4F05-8368-0E834177D8F3 com.ycyangcong.shuttl -- -ShuttlOpenTab matches"
hasnt "$S/calls.log" "REJECTED"

echo "== B. V2: fake xcrun rejects app args not after --"
setup bad_launch replay "$MON_OK"
# Manually call fake xcrun to test rejection
PATH="$HERE/fake-bin:/usr/bin:/bin" xcrun devicectl device process launch --device X com.bundle -ShuttlOpenTab matches > "$S/bad.out" 2>&1
RC=$?
[ $RC = 1 ] && ok "launch without -- exits 1" || bad "exit $RC"
grep -q "invalid for '-t" "$S/bad.out" && ok "error message mentions -t" || bad "no error message"

echo "== C. never-ingest → INGEST TIMEOUT stops the pass"
setup never never "$MON_OK"; V5_INGEST_TIMEOUT=120 run --tests t1,t2,t3
R="$S/out/report.txt"
[ $RC = 5 ] && ok "exit 5 (pass stopped)" || bad "exit $RC"
has "$R" "T2 INGEST TIMEOUT"
has "$R" "PASS STOPPED at T2"
has "$R" "FAIL T2 10-min: not-ingested"
has "$R" "FAIL T3 lock: not-run pass stopped at t2"
hasnt "$R" "T2 done"

echo "== D. T7 not at a court → PENDING"
setup t7 replay "$MON_OK"; V5_ANSWER=skip run --tests t7 --skip-install
R="$S/out/report.txt"
[ $RC = 0 ] && ok "exit 0" || bad "exit $RC"
has "$R" "SKIPPED by the user"
has "$R" "PENDING T7 tripod: the user is not at a court"
hasnt "$R" "FAIL T7"
hasnt "$S/calls.log" "install"

echo "== E. guards (phone guard, offline guard)"
setup g1 replay '[10:09] PHONE CONNECTED
[17:10] A READY-FOR-PHONE (fix round)'; run --tests t1
[ $RC = 3 ] && ok "PHONE CONNECTED older than READY-FOR-PHONE → exit 3" || bad "exit $RC"
[ -e "$S/calls.log" ] && bad "device was called" || ok "no device call"

setup g2 replay '[17:10] A READY-FOR-PHONE
nobody touches the phone until PHONE CONNECTED.'; run --tests t1
[ $RC = 3 ] && ok "prose mention only → exit 3" || bad "exit $RC"

setup g3 replay "$MON_OK"
PATH="/usr/bin:/bin" V5_OFFLINE="$S" bash "$V5" "$S/app/Shuttl.app" > /dev/null 2>&1; RC=$?
[ $RC = 4 ] && ok "V5_OFFLINE without fake xcrun → exit 4" || bad "exit $RC"

echo "== F. MAC SLEPT detection (BUG3)"
setup sleep replay "$MON_OK"; V5_MAC_SLEEP_AT=$((START + 420)) V5_INGEST_TIMEOUT=700 run --tests t2
[ $RC = 0 ] && ok "exit 0" || bad "exit $RC"
R="$S/out/report.txt"
has "$R" "PASS T2 10-min"
L="$S/stderr.txt"
has "$L" "MAC SLEPT"
# The sleep is 1900 s. Without subtraction, 420 + 700 = 1120 < 1900+420 = timeout.
# With subtraction, 420 + 1900 + (700-1900) = 1120 > 700 still, so the check is whether it didn't timeout.

echo
[ $FAILS = 0 ] && echo "ALL OFFLINE v5 CHECKS PASSED" || echo "$FAILS CHECK(S) FAILED"
exit $FAILS
