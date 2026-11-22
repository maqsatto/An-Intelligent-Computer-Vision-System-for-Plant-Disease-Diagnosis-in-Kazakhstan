#!/usr/bin/env bash
# Backbones trained on a "wild" pack (base corpus + PlantWild dev half), aug v1.
# usage: [PACK=pack_w PREFIX=w EPOCHS=12] run_wild.sh <gpu> <model> [<model> ...]
set -u
cd "$(dirname "$0")/../.."
gpu=$1; shift
EPOCHS=${EPOCHS:-12}
STEPS=${STEPS:-500}
PACK=${PACK:-pack_w}
PREFIX=${PREFIX:-w}
for m in "$@"; do
  name="${PREFIX}_$(echo "$m" | tr '/.' '__')"
  [ -f "runs/$name/report.json" ] && continue
  echo "[gpu$gpu] $name $(date +%T)"
  CUDA_VISIBLE_DEVICES=$gpu OMP_NUM_THREADS=4 .venv/bin/python ml/kz/train.py --model "$m" --run "$name" --pack "$PACK" \
    --epochs "$EPOCHS" --steps-per-epoch "$STEPS" > "logs/$name.log" 2>&1 || echo "FAILED $name"
done
echo "wild lane gpu$gpu finished $(date +%T)"
