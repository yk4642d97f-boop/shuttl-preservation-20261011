#!/bin/bash
# Usage: tools/endurance/run-one.sh <label> <clip> <singles|doubles> [uuid]
# One analysis attempt via the shared heavy queue; env ENDURANCE_KILL passes through.
set -uo pipefail
cd "$(dirname "$0")/../.."
label="$1"; clip="$2"; mode="$3"; id="${4:-11111111-1111-1111-1111-$(printf %012d $RANDOM)}"
dir="${ENDURANCE_RUNS:-/tmp/luna11/runs}/$label"; mkdir -p "$dir"
echo "$id" > "$dir/uuid"
/tmp/heavy.sh "T11-$label" tools/endurance/run-timed.sh "$label" \
  "${ENDURANCE_DRIVER:-/tmp/luna11/driver/release/EnduranceDriver}" analyze "$clip" "$dir" "$id" "$mode"
