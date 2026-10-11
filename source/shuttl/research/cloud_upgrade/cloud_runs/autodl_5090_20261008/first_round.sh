#!/usr/bin/env bash
# This only bounds experiments. The user manages rental renewal; never shut down.
set -euo pipefail
base=/root/autodl-tmp/shuttl-5090-20261008
exec 9>"$base/first-round.lock"
flock -n 9
export PYTHONUNBUFFERED=1 NVIDIA_TF32_OVERRIDE=0
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
py="$base/env/bin/python"
runtime="$base/shuttl-runtime"
training="$base/shuttl-cloud"
pose="$base/pose-eval/research/cloud_upgrade/pose_benchmark/cloud_eval.py"
stage() {
  local name="$1"
  shift
  echo "$name" > "$base/logs/current-stage.txt"
  date -Is >> "$base/logs/stages.log"
  echo "START $name" >> "$base/logs/stages.log"
  if "$@" > "$base/logs/$name.log" 2>&1; then
    echo "PASS $name" >> "$base/logs/stages.log"
  else
    local code=$?
    echo "FAILED $name exit=$code" >> "$base/logs/stages.log"
    exit "$code"
  fi
}
if [[ "${1:-}" != continue ]]; then
stage detector-preflight timeout 300 "$py" "$training/research/cloud_upgrade/cloud/run_detector.py" preflight --device cuda
stage pose-preflight timeout 300 "$py" "$pose" preflight --device cuda --report "$base/logs/pose-preflight.json" --reference-image "$base/incoming/pose-reference-image.npy"
stage bst-train "$py" "$runtime/research/cloud_upgrade/cloud/run_bst.py" train \
  --data "$runtime/research/cloud_upgrade/data/bst_fixed30/manifest.json" \
  --init "$runtime/research/cloud_upgrade/artifacts/bst_seq30/bst_CG_AP_JnB_bone_merged.pt" \
  --out "$base/bst-first" --device cuda --steps 2000 --batch 32 --eval-every 100 --hours .25
stage bst-comparison timeout 300 "$py" "$base/incoming/compare_bst.py" \
  --root "$runtime" --candidate "$base/bst-first/best.pt" --out "$base/bst-comparison" --device cuda
fi
# Resuming after manually repaired preflight requires the actual success reports.
"$py" - "$base" <<'VERIFY'
import json,sys
from pathlib import Path
base=Path(sys.argv[1])
for name in ['runtime-preflight-fp32.json','bst-resume-smoke.json','pose-preflight.json']:
    report=json.loads((base/'logs'/name).read_text())
    assert report['device']=='cuda'
assert (base/'bst-comparison/report.json').is_file()
VERIFY
for model in rtmpose_m rtmpose_x vitpose_plus_base; do
  stage "pose-full-$model" timeout 1200 "$py" "$pose" run --panel full --model "$model" --device cuda --threads 4
done
stage pose-comparison timeout 300 "$py" "$pose" compare --panel full --device cuda
for arch in tracknetv3 wasb; do
  stage "train-$arch" "$py" "$training/research/cloud_upgrade/cloud/run_detector.py" train --arch "$arch" --device cuda --hours .5
done
echo COMPLETE > "$base/logs/current-stage.txt"
date -Is >> "$base/logs/stages.log"
