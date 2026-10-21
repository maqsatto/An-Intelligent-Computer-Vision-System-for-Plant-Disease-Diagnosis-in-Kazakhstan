# AgroVision ML

The runtime and training environments are deliberately separate. API/worker installs only NumPy, Pillow and CPU ONNX Runtime from the root project; PyTorch/CUDA belongs to the locked `ml/training` environment.

## Reproduce the admitted research pilot

Run from the repository root:

```bash
uv sync --project ml/training
uv run --project ml/training python ml/training/acquire.py plantvillage --per-class 120
uv run --project ml/training python ml/training/acquire.py wheat --workers 6
uv run --project ml/training python ml/training/extract_wheat.py
uv run --project ml/training python ml/training/prepare.py
systemd-run --user --scope -p MemoryMax=3G -p MemoryHigh=2500M -p MemorySwapMax=1G \
  env OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 \
  uv run --project ml/training python ml/training/train.py \
  --run pilot-joint-efficientnet-b0-seed17 --epochs 30 --min-available-gib 3
```

Run one heavy ML/native-build job at a time. Training uses zero dataloader workers and checks that MemAvailable remains at least 3 GiB before feature batches, epochs and parity. The Linux systemd scope above adds the 3 GiB hard cap.

`extract_wheat.py` needs `bsdtar` (libarchive). Downloads stay in ignored `data/`; model/checkpoint/manifests/evaluation stay in ignored `artifacts/<run>/`. Each model folder snapshots the exact data/split/label manifests. Use a fresh run name for new data or implementation changes. Do not modify a folder already pinned by worker jobs.

This recipe is a short frozen ImageNet-backbone research baseline, not the full Foundation finetuning study. See [measured results and source audit](../docs/development/DATA_AND_MODEL.md) for data rights, grouping, quarantine and evaluation limitations.

## Runtime modes

`validate_bundle()` / `OnnxPredictor` require a validated release and finite, non-null validated policy. The supplied research artifacts do not meet that admission.

`validate_research_bundle()` / `ResearchOnnxPredictor` require explicit research admission and always return `inconclusive` with null prediction. They show exploratory global joint scores without crop renormalization. The backend must restrict this mode to explicit development/test configuration. Production never silently falls back.

```bash
uv run pytest tests/runtime -q
uv run ruff check ml tests/runtime
```
