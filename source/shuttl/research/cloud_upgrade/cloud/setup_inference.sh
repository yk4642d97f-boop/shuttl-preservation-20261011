#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
mode="${1:-cuda}"
if [[ "$mode" != "cuda" && "$mode" != "cpu" ]]; then
  echo 'Usage: setup_inference.sh [cuda|cpu]' >&2
  exit 2
fi
python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,12), "Use Python 3.11 or 3.12 for this pinned runtime"'
python3 -m venv .venv-inference
.venv-inference/bin/python -m pip install pip==25.0.1
if [[ "$mode" == "cuda" ]]; then
  .venv-inference/bin/python -m pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu124
  .venv-inference/bin/python -m pip install onnxruntime-gpu==1.20.1
else
  .venv-inference/bin/python -m pip install torch==2.4.1 torchvision==0.19.1
  .venv-inference/bin/python -m pip install onnxruntime==1.20.1
fi
.venv-inference/bin/python -m pip install -r research/cloud_upgrade/cloud/requirements-inference.txt
# rtmlib declares several mutually overlapping OpenCV wheels and CPU ORT;
# the required numpy/OpenCV/ORT runtimes above are explicit for this environment.
.venv-inference/bin/python -m pip install rtmlib==0.0.16 ultralytics==8.2.103 --no-deps
.venv-inference/bin/python research/cloud_upgrade/cloud/run_inference.py preflight --device "$mode" --report runtime-preflight.json
