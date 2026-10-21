# Data and model: measured MVP research baseline

On 21 October 2026 a real pretrained **EfficientNet-B0** model was trained for wheat, potato and tomato, exported to ONNX and checked through the public runtime. The current local bundle is `artifacts/pilot-joint-efficientnet-b0-seed17` (9 crop–condition classes). It is **research only**: production admission rejects it; the explicit research runtime always returns inconclusive with exploratory candidates. No Kazakhstan diagnostic accuracy is claimed.

## Sources, rights and actual files

| Foundation ID | Primary evidence | Actual admission/acquisition |
|---|---|---|
| D01 PlantVillage | [Author repository](https://github.com/spMohanty/PlantVillage-Dataset), [author dataset card](https://huggingface.co/datasets/mohanty/PlantVillage) | Card explicitly states CC BY-SA 3.0. Admitted for attributed academic research storage, preprocessing and model experiments; images are not redistributed in Git. Downloaded 720 original **color** images, 120/class for potato/tomato early blight, late blight and healthy appearance. No grayscale/segmented copies counted. |
| D05 Wheat Leaf Dataset v1 | [Original provider](https://data.mendeley.com/datasets/wgd66f8n6h/1), DOI 10.17632/wgd66f8n6h.1, Hawi Getachew | Provider explicitly states CC BY 4.0; admitted for attributed academic research. Downloaded and decoded all **407** originals: 102 Healthy, 97 Septoria, 208 stripe_rust. Provider describes Holeta, Ethiopia, Canon EOS 5D Mark III and source pathologist assistance; these are provider claims, not independently verified capture metadata. |
| Other Foundation candidates | Existing Foundation catalog preserved | Not automatically admitted/downloaded. Rights ambiguity, NC/ND restrictions, uncertain source labels and version differences still require individual decisions. |

PlantVillage originals and physical-leaf map are pinned to author Git commit `7f7ecc7e1eaca78107e3affe7cb5abd9427e139a`. Map SHA256: `3b4b253683c6911744959a3870a92509b1faa1ee34e9f8585e21d0fe6337a25b`. Original wheat RAR is **1,511,923,897 bytes**, and matches the provider's SHA256 `23653dd88f9f900315a9a0c88a163c891b3bdd00cc89b36d98cc5b3fcc1d7e94`. A slow initial ZIP-wrapper download was replaced by exact HTTP byte ranges for the same provider RAR; final hash verification passed before extraction. The incomplete redundant ZIP was removed. Extraction selected image members only and checked paths/symlinks; no dataset code was executed.

Source pages, license card, immutable source listings, source-map and acquisition checks are retained under ignored `data/evidence/`; their hashes are recorded in the audit. Each image manifest row retains SHA256, source version/filename, download timestamp, original label, dimensions, license evidence, unknown context and split. Source Septoria is mapped to **`septoria_source_label`**, preserving its broad original granularity instead of inventing a laboratory-confirmed species.

Attribution: Sharada P. Mohanty, David P. Hughes and Marcel Salathé, *Using Deep Learning for Image-Based Plant Disease Detection* (2016), PlantVillage; Hawi Getachew, *Wheat Leaf Dataset*, v1 (2021). These public sources do not establish local Kazakhstan applicability.

## Grouping, quarantine and splits

`prepare.py` unions author physical-leaf IDs, identical SHA256 and conservative 64-bit dHash distance ≤4 **before** deterministic group-hash splitting (seed 17; intended proportions 70/10/5/15 train/selection-validation/calibration/test). Group membership is checked again by the trainer. Exact duplicates are excluded after grouping; conflicting-label groups are quarantined. Selection of 120 PlantVillage files/class follows filename SHA256 ordering, without inspecting model outcomes.

All **1,127** acquired files decoded. **103** tomato files lack matching author leaf-map entries and are quarantined, without invented biological identities. **1** wheat exact duplicate is excluded. Three near-duplicate pairs were unioned. Final admitted set: **1,023 images / 868 available groups**, split **721 train / 115 validation / 34 calibration / 153 test**. Group counts are 607/97/32/132 respectively. Unknown plant/session IDs remain null with a reason.

PlantVillage groups use supplied physical-leaf IDs. **D05 groups are dedup proxies: biological plant/session independence is unverified.** Consequently, even this grouped test does not prove independent plant/farm generalization. dHash screening is not an exhaustive near-duplicate proof. Wheat images visibly include repeated soil, denim/hand and paper contexts, creating potential background/label confounding. These limitations are material to interpreting the internal numbers.

Test labels did not select the head/checkpoint/threshold. Calibration images were counted/evaluated but **not used to fit a calibration or policy**. `healthy_appearance` means visible source-labeled appearance within the source scheme, not absence of all diseases.

## Actual training and results

[Full measured joint report](model_reports/joint-efficientnet-b0-seed17.json); [earlier potato/tomato-only pilot](model_reports/plantvillage-efficientnet-b0-seed17.json). The two label spaces and test sets differ; their metrics are not a controlled architecture comparison.

| Measure | Joint wheat + potato + tomato |
|---|---|
| Architecture | TorchVision EfficientNet-B0, `IMAGENET1K_V1` frozen backbone, trained classification head |
| Training | Seed 17, AdamW, head batch 32, 30 epochs, **690 actual optimizer updates**; image feature batch 8; no augmentation or partial finetuning |
| Train / validation macro-F1 | 0.98477 / 0.96376 |
| Held-out internal test | **153 images / 132 available groups**, macro-F1 **0.89559**, accuracy **0.92810** |
| Test image accuracy by source crop | Wheat 63/65; potato 52/55; tomato 27/33; small internal counts, not accepted crop-level diagnostic performance |
| Raw classification errors of concern | 1 disease→healthy-appearance, 3 healthy-appearance→disease, 4 cross-crop errors; some categories can overlap |
| ONNX | FP32, opset 17, **16,066,520 bytes**; legacy Torch exporter |
| PyTorch/ONNX parity | **100 real images** distributed across file order/classes, rtol 0.001 / atol 0.0001; max absolute logit difference **1.502e-5**, **0** top-1 changes |
| CPU model-only | Intel i5-10400F, ORT CPU 1.21.1, 4 intra-op / 1 inter-op threads; 20 warmups + 200 measured: p50 **6.29 ms**, p95 **7.53 ms** |
| Decode+preprocess+model | 200 measured on a specified **256×256 / 19,289-byte PlantVillage JPEG**: p50 **7.93 ms**, p95 **9.26 ms**; does not characterize full-resolution wheat uploads |
| Session cold start | **64.09 ms** |
| Training resource measurement | RTX 2060 6 GiB; peak CUDA allocated **99.83 MiB** for frozen-feature/head recipe; whole training/export process peak RSS **2,003 MiB**, not isolated inference RSS |
| Bounded successful run | **82.64 s** total, including 73.02 s feature extraction; system MemAvailable never below **7.96 GiB** at guard checks |

Preprocessing is shared directly with the serving runtime: EXIF transpose, RGB, resize shorter side 256 with bilinear interpolation, center crop 224, ImageNet mean/std. A 12-image original PlantVillage grid, 12-image original wheat grid and 9 wheat center crops were visually inspected; selected crops retained visible leaf regions/symptoms. This was a pipeline check, not expert verification of the entire corpus.

The report contains full per-class precision/recall/support, confusion matrices, history, pretrained-weight SHA256, dependency/lockfile hashes, hardware and code-file snapshot hashes. The run explicitly records **`code_dirty: true`**: it ran before the ML source commit, and does not pretend its base Git commit already contained uncommitted code. Individual code hashes preserve the actual development snapshot. Model folders snapshot data/split/label manifests. No raw image, model or checkpoint is staged in Git.

## Resource interruption and safe execution

An earlier joint feature-extraction run was interrupted during a system-wide resource incident before it produced a checkpoint or model. It supplied no joint metrics. The successful run above resumed after checking existing artifacts, as the **only heavy job**, under a systemd user scope with `MemoryMax=3G`, `MemoryHigh=2500M`, `MemorySwapMax=1G`, OMP/MKL/OpenBLAS threads 4, Torch inter-op 1 and **0 dataloader workers**. A `MemAvailable ≥3 GiB` guard runs before feature batches, epochs and parity examples. Observed scope peak during extraction was about 2.44 GiB. The scope exited successfully and the heavy execution slot was released before mobile native build work.

Persistent training log: ignored `runs/joint-training.log`. Main owns the user-authorized system swap configuration; this pipeline does not alter swap.

## Runtime integrity and mode isolation

`ml/runtime/agrovision_runtime` imports no FastAPI, ORM or training library. Strict `validate_bundle()` requires a validated release and finite non-null validated thresholds. It rejects checksum/path escape, class-order mismatch, full preprocessing digest mismatch and ONNX metadata/tensor-schema mismatches. Ordered-label and full-preprocessing SHA256 are embedded in ONNX. Explicit exceptions remain effective under optimized Python.

The validator hashes and inspects **the same immutable ONNX bytes**. An admitted Bundle privately binds those bytes and a canonical manifest digest; predictor copies the admitted manifest and loads the pinned bytes without reopening the path. Path replacement cannot swap weights/policy after admission, and mutation of a validated manifest is rejected. CPU sessions use 4 intra-op / 1 inter-op threads.

`validate_research_bundle()` admits only integrity-checked research/unvalidated artifacts. `ResearchOnnxPredictor` preserves global joint `model_score` values without crop renormalization and **always returns inconclusive/null prediction** with `research_model_unvalidated`. Even a >0.999 healthy candidate cannot become a healthy conclusion. Backend activation is explicit and limited to development/test; production never silently falls back.

Runtime verification: **26 tests passed**, including invalid thresholds (null/NaN/inf/bool), immutable class/preprocessing binding, artifact traversal, research/production isolation, CPU thread bounds and model/manifest replacement regressions. The actual joint bundle was loaded through the public runtime and inferred real photos for **all three crops**, returning inconclusive with real candidates; production independently rejected the same artifact.

## Reproduction and remaining limits

See [ML commands](../../ml/README.md). Commands actually used include locked `uv sync --project ml/training`, immutable PlantVillage acquisition, verified D05 range acquisition/extraction, `prepare.py`, a bounded 30-epoch joint run, public-runtime smoke checks and `pytest tests/runtime -q`. Keep the immutable manifests/evidence and training `uv.lock`; use a fresh model version after data/code changes and never overwrite a bundle pinned by jobs.

One seed; small sample; no group confidence intervals/seed variation; no source-held-out, Kazakhstan, smartphone-domain, unseen-condition, negative/OOD or mixed-condition evaluation; no calibrated probabilities, validated rejection/quality rules or agronomic acceptance criteria. No severity, segmentation or heatmap claim. CPU timings exclude upload, queue, DB/client latency and large-photo preprocessing. This short frozen-backbone experiment demonstrates a reproducible implemented research pipeline; it does not fulfill the Foundation's final diagnostic-release acceptance protocol.

## Post-run allocation admission fix

Fresh review identified that a tiny but extremely elongated source could expand dramatically when its shorter side was resized to 256. A subsequent compatibility guard now rejects source geometry above 20,000,000 pixels and any projected intermediate above 4,000,000 pixels or 16,384 pixels on either axis **before decode/EXIF copy/resize**. This changes input admission, not accepted-image pixel operations or the preprocessing version. Offline training explicitly admits up to 50,000,000 source pixels for the historical 24 MP D05 originals, while keeping the same mandatory 4 MP intermediate budget; serving never uses this override.

Historical model metrics, report hashes and original run provenance above are preserved, rather than relabeled as a new run. Every historical ML Python source hash in the frozen joint report was checked against Git commit `73d25da`; it matches that content baseline. The later admission-guard/runtime and explicit offline-override sources intentionally have new hashes, without rewriting the original run snapshot. Post-fix runtime verification: **33 tests passed**, including a compressed 10×60,000 JPEG rejected before any resize/EXIF allocation, source/intermediate budget boundaries and legacy pixel compatibility. Three real admitted photos (one per crop) produced tensors exactly equal to the pre-guard implementation. No retraining or heavy validation job was run for this fix.
