#!/usr/bin/env bash
# Run only on the future instance, from the extracted pose-eval archive.
set -euo pipefail
cd "$(dirname "$0")/../../.."
pose_mode="${1:-cuda}"
if [[ "$pose_mode" != cpu && "$pose_mode" != cuda ]]; then
  echo 'Usage: setup_cloud.sh cpu|cuda' >&2
  exit 2
fi
if [[ -e .venv-pose ]]; then
  echo '.venv-pose exists; use a fresh archive directory/environment' >&2
  exit 2
fi
python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,12), "Use Python 3.11 or 3.12"'
python3 -m venv .venv-pose
.venv-pose/bin/python -m pip install pip==25.0.1
if [[ "$pose_mode" == cuda ]]; then
  .venv-pose/bin/python -m pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu124
  .venv-pose/bin/python -m pip install onnxruntime-gpu==1.20.1
else
  .venv-pose/bin/python -m pip install torch==2.4.1 torchvision==0.19.1 onnxruntime==1.20.1
fi
.venv-pose/bin/python -m pip install -r research/cloud_upgrade/pose_benchmark/requirements-runtime.txt
# rtmlib declares CPU ORT and overlapping OpenCV wheels. Supply runtimes above explicitly.
.venv-pose/bin/python -m pip install rtmlib==0.0.16 --no-deps
.venv-pose/bin/python research/cloud_upgrade/pose_benchmark/cloud_eval.py preflight --device "$pose_mode" --report "pose-preflight-${pose_mode}.json"
