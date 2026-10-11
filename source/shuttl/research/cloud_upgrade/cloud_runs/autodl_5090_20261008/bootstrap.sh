#!/usr/bin/env bash
set -euo pipefail
base=/root/autodl-tmp/shuttl-5090-20261008
mkdir -p "$base/tmp" "$base/pip-cache"
export TMPDIR="$base/tmp" PIP_CACHE_DIR="$base/pip-cache"
export PATH="/root/miniconda3/bin:$PATH"
# Reuse the instance's CUDA-enabled torch 2.8.0+cu128 read-only; dependencies live on the data disk.
# This is a separately recorded runtime variant and must pass the frozen reference checks.
if [[ ! -e "$base/env" ]]; then
  python -m venv --system-site-packages "$base/env"
fi
# Explicit local paths prevent pip from choosing an identical, slower index URL.
"$base/env/bin/python" - <<'PY'
import hashlib
import json
from pathlib import Path
base = Path('/root/autodl-tmp/shuttl-5090-20261008')
pins = [line.strip() for line in (base / 'incoming/requirements-overlay.txt').read_text().splitlines()
        if line.strip() and not line.startswith('#')]
pins.append('llvmlite==0.43.0')
receipts = {row['pin']: row for row in json.loads((base / 'wheels/verified.json').read_text())}
paths = []
for pin in pins:
    row = receipts[pin]
    path = (base / 'wheels' / row['file']).resolve()
    if not path.is_relative_to(base / 'wheels') or path.stat().st_size != row['bytes']:
        raise ValueError('Invalid local dependency: ' + pin)
    with path.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != row['sha256']:
            raise ValueError('Dependency checksum mismatch: ' + pin)
    paths.append(str(path))
(base / 'incoming/requirements-local.txt').write_text('\n'.join(paths) + '\n')
PY
"$base/env/bin/python" -m pip install --find-links "$base/wheels" --index-url https://mirrors.aliyun.com/pypi/simple -r "$base/incoming/requirements-local.txt"
"$base/env/bin/python" -m pip install --no-index --find-links "$base/wheels" --no-deps rtmlib==0.0.16 ultralytics==8.2.103
"$base/env/bin/python" -m pip freeze > "$base/logs/pip-freeze.txt"
"$base/env/bin/python" - <<'PY'
import json
from pathlib import Path
import torch, torchvision
import cv2, numpy, onnxruntime
onnxruntime.preload_dlls()
report = dict(torch=torch.__version__, torchvision=torchvision.__version__,
              cuda=torch.version.cuda, gpu=torch.cuda.get_device_name(0),
              numpy=numpy.__version__, opencv=cv2.__version__,
              onnxruntime=onnxruntime.__version__, providers=onnxruntime.get_available_providers(),
              base_torch_reused=True)
assert torch.cuda.is_available()
assert torch.__version__ == '2.8.0+cu128'
assert torch.version.cuda == '12.8'
assert torch.cuda.get_device_capability() == (12, 0)
assert 'CUDAExecutionProvider' in report['providers']
assert numpy.__version__ == '1.26.4'
Path('/root/autodl-tmp/shuttl-5090-20261008/logs/environment.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
PY
