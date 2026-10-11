#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/tools/robustness/gen"
swift build -c release --scratch-path /tmp/luna10/gen -j 4
cd "$ROOT/backend"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python ../tools/robustness/generate.py
