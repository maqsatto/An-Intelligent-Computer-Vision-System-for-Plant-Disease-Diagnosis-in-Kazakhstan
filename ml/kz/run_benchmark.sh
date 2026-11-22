#!/usr/bin/env bash
# Transfer-learning benchmark: every backbone gets the same data, schedule and seed.
# Two GPU lanes run in parallel (one process per GPU, memmap shared through page cache).
set -u
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
EPOCHS=${EPOCHS:-10}
STEPS=${STEPS:-500}

lane() {
  gpu=$1; shift
  for m in "$@"; do
    name=$(echo "$m" | tr '/.' '__')
    if [ -f "runs/$name/report.json" ]; then continue; fi
    echo "[gpu$gpu] $m $(date +%T)"
    CUDA_VISIBLE_DEVICES=$gpu OMP_NUM_THREADS=4 $PY ml/kz/train.py --model "$m" --run "$name" \
      --epochs "$EPOCHS" --steps-per-epoch "$STEPS" > "logs/$name.log" 2>&1 || echo "FAILED $m"
  done
}
mkdir -p logs runs
lane 0 efficientnet_b0.ra_in1k tf_efficientnetv2_s.in21k_ft_in1k convnext_tiny.fb_in22k_ft_in1k vit_base_patch16_224.augreg2_in21k_ft_in1k regnety_040.ra3_in1k eva02_small_patch14_224.mim_in22k &
lane 1 mobilenetv3_large_100.ra_in1k convnextv2_tiny.fcmae_ft_in22k_in1k convnext_small.fb_in22k_ft_in1k swin_tiny_patch4_window7_224.ms_in22k_ft_in1k vit_small_patch14_dinov2.lvd142m maxvit_tiny_tf_224.in1k &
wait
echo "benchmark finished $(date +%T)"
