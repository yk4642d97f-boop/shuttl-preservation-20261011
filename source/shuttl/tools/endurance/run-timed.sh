#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/../.."
mkdir -p tools/endurance/results
label="$1"; shift
log="tools/endurance/results/timing-${label}${ENDURANCE_TAG:-}.txt"
{
  echo "START $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  uptime
  echo "COMMAND $*"
} > "$log"
set +e
"$@" >> "$log" 2>&1
status=$?
set -e
{
  echo "EXIT_STATUS $status"
  echo "END $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  uptime
} >> "$log"
exit "$status"
