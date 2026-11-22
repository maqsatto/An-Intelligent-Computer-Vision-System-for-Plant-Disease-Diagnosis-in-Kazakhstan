#!/usr/bin/env bash
# Stage 2: best backbones retrained with augmentation v2 (leaf background replacement + blur/noise/erasing).
# usage: run_v2.sh <gpu> <wait-for-pattern|-> <model> [<model> ...]
set -u
cd "$(dirname "$0")/../.."
gpu=$1; wait_for=$2; shift 2
EPOCHS=${EPOCHS:-12}
STEPS=${STEPS:-500}
if [ "$wait_for" != "-" ]; then
  while pgrep -f "$wait_for" > /dev/null; do sleep 15; done
fi
for m in "$@"; do
  name="v2_$(echo "$m" | tr '/.' '__')"
  [ -f "runs/$name/report.json" ] && continue
  echo "[gpu$gpu] $name $(date +%T)"
  CUDA_VISIBLE_DEVICES=$gpu OMP_NUM_THREADS=4 .venv/bin/python ml/kz/train.py --model "$m" --run "$name" \
    --aug v2 --epochs "$EPOCHS" --steps-per-epoch "$STEPS" > "logs/$name.log" 2>&1 || echo "FAILED $name"
done
echo "v2 lane gpu$gpu finished $(date +%T)"
