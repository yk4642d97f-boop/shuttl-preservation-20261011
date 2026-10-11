#!/bin/bash
# Reruns the whole Task 10 robustness suite. Every heavy step goes through the shared queue
# /tmp/heavy.sh (one heavy job across all agents, niced). Private scratch only (/tmp/luna10).
#   ./tools/robustness/run_all.sh            # build, regenerate corpus, sweep, matrices, merge
#   FORCE=1 ./tools/robustness/run_all.sh    # also re-run clips that already have raw/ results
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; ROB="$ROOT/tools/robustness"; PY="$ROOT/backend/.venv/bin/python"
Q=/tmp/heavy.sh
mkdir -p /tmp/luna10
$Q T10-genbuild   bash -c "cd '$ROB/gen' && swift build -c release --scratch-path /tmp/luna10/gen -j 4"
$Q T10-drvbuild   bash -c "cd '$ROB/driver' && swift build -c release --scratch-path /tmp/luna10/driver -j 4"
$Q T10-corpus     bash -c "cd '$ROOT/backend' && PYTHONDONTWRITEBYTECODE=1 '$PY' '$ROB/generate.py'"
# Python + Swift over every clip, one lock for the batch; timeouts are measured inside it.
$Q T10-sweep      env T10_IN_HEAVY=1 "$PY" "$ROB/sweep.py" ${FORCE:+--force}
# Fake-stage matrix (deterministic stages, every stage incl. reconstruct3d) and the real-pipeline matrix.
$Q T10-fakematrix bash -c "'/tmp/luna10/driver/release/RobustnessDriver' matrix '$ROB/corpus/seed_valid.mp4' /tmp/luna10/checkpoints > '$ROB/matrix_fake.txt' 2>&1 || true"
$Q T10-matrix     env T10_IN_HEAVY=1 "$PY" "$ROB/matrix_live.py"
"$PY" "$ROB/merge_results.py"
echo "results: $ROB/results.csv  matrix: $ROB/matrix_live.jsonl  $ROB/matrix_fake.txt"
