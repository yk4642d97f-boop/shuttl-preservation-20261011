#!/bin/bash
# B · final fixture pass (monitor gate step 2). Run through the heavy queue AFTER B and C code is final:
#   /tmp/heavy.sh B-final-fixtures tools/device-final/final-fixtures.sh
# 1. device-measure.log line  2. live_e2e 3 (must be 3 cases)  3. eval --full
# 4. ShuttlLive SHUTTL_LIVE_E2E=1 (release)  5. ShuttlEval (release)  → summary in /tmp/shuttl-final-fixtures/summary.txt
set -u
R="$HOME/Downloads/华北五省"; O=/tmp/shuttl-final-fixtures; mkdir -p "$O"
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$O/summary.txt"; }
cd "$R/backend" || exit 1
echo "[$(date +%H:%M)] B: final fixture pass — regenerating live_e2e.json (3 cases) and bench_*.json via eval --full (tools/device-final/final-fixtures.sh)." >> "$R/.agent-logs/device-measure.log"

log "live_e2e 3"
.venv/bin/python -m scripts.swift_fixtures.live_e2e 3 > "$O/live_e2e.log" 2>&1; log "live_e2e exit $?"
n=$(.venv/bin/python -c "import json;print(len(json.load(open('$R/iOS/Packages/ShuttlLive/Tests/ShuttlLiveTests/Fixtures/live_e2e.json'))['cases']))")
log "live_e2e.json cases: $n"; [ "$n" = 3 ] || { log "FAIL: live_e2e must have 3 cases"; exit 1; }

log "eval --full"
.venv/bin/python -m scripts.swift_fixtures.eval --full > "$O/eval.log" 2>&1; log "eval exit $?"

log "ShuttlLive SHUTTL_LIVE_E2E=1"
cd "$R/iOS/Packages/ShuttlLive" && SHUTTL_LIVE_E2E=1 swift test -c release -j 4 -Xswiftc -enable-testing \
  --scratch-path /tmp/sc_final/live > "$O/live.log" 2>&1
log "ShuttlLive exit $? — $(grep -E 'Executed [0-9]+ tests' "$O/live.log" | tail -1 | sed 's/^[[:space:]]*//')"
grep -E ": error -\[" "$O/live.log" | head -10 | tee -a "$O/summary.txt"

log "ShuttlEval"
cd "$R/iOS/Packages/ShuttlEval" && swift test -c release -j 4 --scratch-path /tmp/sc_final/eval > "$O/evalswift.log" 2>&1
log "ShuttlEval exit $? — $(grep -E 'Executed [0-9]+ tests' "$O/evalswift.log" | tail -1 | sed 's/^[[:space:]]*//')"
grep -E ": error -\[" "$O/evalswift.log" | head -10 | tee -a "$O/summary.txt"
log "FINAL_FIXTURES_DONE"
