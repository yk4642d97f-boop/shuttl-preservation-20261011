#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
python3 -m venv .venv-cloud
.venv-cloud/bin/python -m pip install pip==25.0.1
.venv-cloud/bin/python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
.venv-cloud/bin/python -m pip install -r research/cloud_upgrade/cloud/requirements.txt
.venv-cloud/bin/python research/cloud_upgrade/cloud/run_detector.py preflight
