# KZ-agrosector model: data, transfer-learning benchmark and measured limits

Pipeline code: [`ml/kz/`](../../ml/kz). Web demo: [WEB_DEMO_RU.md](WEB_DEMO_RU.md). All numbers below are measured on the training server (2 × RTX 5070 Ti, PyTorch 2.11 + CUDA 12.8, timm 1.0.31) on 22 Nov 2026. This is a **research prototype**; it does not establish diagnostic accuracy on Kazakhstan fields (see [Limits](#measured-limits)).

## 1. Scope: crops of the Kazakhstan agrosector

The earlier pilot covered wheat/potato/tomato only. The KZ model targets the crops that dominate or are strategically important for Kazakhstan and for which **open, labelled leaf-disease images exist**:

| Crop | Conditions in the model | Main sources |
|---|---|---|
| Wheat (пшеница) | healthy, yellow(stripe) rust, brown rust, septoria, powdery mildew (+ stem rust, head scab, loose smut in the "wild" model) | JIC field photos (Zenodo 7573133), Holeta wheat leaf (Mendeley), PlantWild v2 |
| Sunflower (подсолнечник) | healthy, downy mildew, gray mold, leaf scars | Sunflower disease classification (AgML) |
| Maize (кукуруза) | healthy, gray leaf spot, common rust, northern leaf blight (+ smut in the "wild" model) | PlantVillage, PlantDoc, PlantWild |
| Potato (картофель) | healthy, early blight, late blight | PlantVillage, AgML potato, PlantDoc, PlantWild |
| Tomato (томат) | healthy + 9 diseases/pests | PlantVillage, PlantDoc, PlantWild |
| Cucumber (огурец) | healthy, anthracnose, bacterial wilt, downy mildew, gummy stem blight (+ powdery mildew, angular leaf spot in the "wild" model) | AgML cucumber, PlantWild |
| Apple (яблоня) | healthy, scab, black rot, cedar rust (+ mosaic virus in the "wild" model) | PlantVillage, PlantDoc, PlantWild |
| Grape (виноград) | healthy, black rot, esca, leaf blight (+ downy mildew in the "wild" model) | PlantVillage, PlantDoc, PlantWild |
| *other / not a target leaf* | explicit rejection class | other plants (PlantVillage/PlantDoc/PlantWild), textures (DTD), generic photos (Tiny ImageNet) |

**Not covered** (no suitable open data found): barley, sugar beet, flax, rapeseed, legumes. Claiming them would be fabrication.

## 2. Data, rights and leakage control

* Sources are public and downloaded without executing dataset code; images are not committed to Git. Licences: PlantVillage CC BY-SA 3.0 (CC0 mirror on HF), PlantDoc CC BY-SA 4.0, JIC wheat CC BY 4.0, Holeta wheat CC BY 4.0, AgML sunflower/potato CC BY 4.0, AgML cucumber (licence not stated on the card — research use only), Tiny ImageNet/DTD (research use).
* **PlantWild v1 (CC BY-NC-ND 4.0)** is the only in-the-wild source with enough field images. It is used for **non-commercial research only**; model weights trained on it are not committed or distributed. Two bundles are therefore built: **clean** (no PlantWild; used only as an evaluation set) and **wild** (trained on the PlantWild *dev* half). The *test* half is never used for training, selection or calibration by any model.
* Everything is deduplicated and grouped **before** splitting: exact SHA256, PlantVillage physical-leaf IDs and 64-bit dHash (Hamming ≤ 4, per crop) are unioned into groups; groups are hash-assigned to train/val/test (78/8/14 %). Groups with conflicting labels are quarantined. PlantDoc groups are split 50/50 into train and a held-out **field_test**. PlantWild images that near-duplicate any training image are dropped (529 removed), then its clusters are split 50/50 into dev/test.
* Preprocessing is the serving preprocessing: EXIF transpose, RGB, shorter side → 256 (bilinear), centre crop 224, ImageNet normalisation baked into the ONNX graph.

| Evaluation set | What it measures | Images |
|---|---|---:|
| `val` | model selection (lab-dominated) | 3,428 |
| `test` | grouped held-out test of the training sources (lab + field) | 6,097 |
| `field_test` | PlantDoc field photos never trained on | 1,294 |
| PlantWild `test` half | independent **in-the-wild** web photos (23+ classes in scope, 24 other plants) | 2,723 in scope + ~3,000 other plants |

## 3. Transfer-learning protocol

Every backbone: timm ImageNet(-21k/22k/LVD) pretrained weights, full fine-tuning, AdamW (backbone/head learning rates by family), cosine schedule with warm-up, bf16 autocast, label smoothing 0.1, batch 96, 10 epochs × 500 steps, sqrt-inverse-frequency class sampling with 3× weight for field-domain images, GPU augmentation (random resized crop 0.45–1, rotation ±30°, flips, brightness/contrast/saturation/white balance). Checkpoint selection on `val` macro-F1 only, seed 17. Augmentation **v2** (replace the background of PlantVillage leaves by random textures/scenes using the author's segmented masks + blur/noise/random erasing) was also tested.

## 4. Results

### 4.1 Transfer-model benchmark (same data, schedule, seed)

Columns: *Test* = grouped held-out test of the training sources; *PlantDoc* = held-out field photographs; *PlantWild* = independent in-the-wild web photos, held-out half: "all supported classes" is over the photos of the classes that model knows (clean models 3,013 photos, wild-v1 3,666, wild-v1+v2 3,942 including wheat), "23 shared classes" is the same 2,554 photos of the 23 original classes for every row; "crop given" = restricted to the true crop, i.e. what a user gets by choosing the crop in the UI. *Training data*: `clean` = no PlantWild; `clean+bg-aug` = clean + leaf-background replacement augmentation; `wild-v1` / `wild-v1+v2` = additionally trained on the PlantWild v1 / v1+v2 *dev* half (non-commercial research). `wild-v1+v2` is a harder 47-class problem (adds wheat stem rust, head scab, loose smut and other field-only classes), which is why its accuracy on the 23 shared classes is lower than `wild-v1` although it is the better product.

| Model | Training data | Params, M | Val F1 | Test acc | Test F1 | PlantDoc acc | PlantDoc F1 | PlantWild acc (all supported classes) | PlantWild acc (23 shared classes) | PlantWild crop acc | PlantWild acc, crop given | img/s | Train min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| convnext_small.fb_in22k_ft_in1k | clean | 49.5 | 0.9879 | 0.9923 | 0.9886 | 0.7566 | 0.4411 | 0.4872 | 0.4769 | 0.7006 | 0.6316 | 1736 | 16.5 |
| convnext_tiny.fb_in22k_ft_in1k | clean | 27.9 | 0.9882 | 0.9888 | 0.9827 | 0.7481 | 0.4202 | 0.4666 | 0.4565 | 0.6801 | 0.6276 | 2421 | 9.9 |
| vit_base_patch16_224.augreg2_in21k_ft_in1k | clean | 85.8 | 0.9914 | 0.9918 | 0.9864 | 0.7512 | 0.3997 | 0.4593 | 0.4487 | 0.6628 | 0.6306 | 1693 | 17.4 |
| swin_tiny_patch4_window7_224.ms_in22k_ft_in1k | clean | 27.6 | 0.9865 | 0.9920 | 0.9899 | 0.7519 | 0.4416 | 0.4467 | 0.4405 | 0.6485 | 0.6170 | 2013 | 12.6 |
| eva02_small_patch14_224.mim_in22k | clean | 21.6 | 0.9848 | 0.9893 | 0.9830 | 0.7210 | 0.3652 | 0.4341 | 0.4248 | 0.6323 | 0.6296 | 2325 | 11.7 |
| tf_efficientnetv2_s.in21k_ft_in1k | clean | 20.2 | 0.9927 | 0.9915 | 0.9879 | 0.7318 | 0.4208 | 0.4115 | 0.3990 | 0.6094 | 0.6024 | 2429 | 9.6 |
| efficientnet_b0.ra_in1k | clean | 4.1 | 0.9844 | 0.9890 | 0.9832 | 0.6793 | 0.3502 | 0.3518 | 0.3332 | 0.5270 | 0.5632 | 3219 | 5.5 |
| mobilenetv3_large_100.ra_in1k | clean | 4.3 | 0.9849 | 0.9874 | 0.9826 | 0.6669 | 0.3600 | 0.3525 | 0.3348 | 0.5337 | 0.5592 | 2833 | 4.2 |
| convnext_small.fb_in22k_ft_in1k | clean+bg-aug | 49.5 | 0.9869 | 0.9910 | 0.9867 | 0.7558 | 0.4407 | 0.4959 | 0.4894 | 0.7049 | 0.6329 | 1663 | 19.2 |
| convnext_tiny.fb_in22k_ft_in1k | clean+bg-aug | 27.9 | 0.9866 | 0.9897 | 0.9857 | 0.7427 | 0.4432 | 0.4716 | 0.4612 | 0.6850 | 0.6279 | 2625 | 13.2 |
| convnext_small.fb_in22k_ft_in1k | wild-v1 | 49.5 | 0.9426 | 0.9913 | 0.9873 | 0.7612 | 0.4290 | 0.7229 | 0.7271 | 0.8560 | 0.8159 | 1753 | 19.3 |
| convnext_tiny.fb_in22k_ft_in1k | wild-v1 | 27.9 | 0.9366 | 0.9908 | 0.9889 | 0.7473 | 0.4252 | 0.7220 | 0.7318 | 0.8538 | 0.8110 | 2492 | 13.1 |
| swin_tiny_patch4_window7_224.ms_in22k_ft_in1k | wild-v1 | 27.6 | 0.9367 | 0.9903 | 0.9642 | 0.7442 | 0.4117 | 0.7152 | 0.7240 | 0.8377 | 0.8186 | 2028 | 15.3 |
| vit_small_patch14_dinov2.lvd142m | wild-v1 | 21.6 | 0.9390 | 0.9872 | 0.9577 | 0.7156 | 0.4150 | 0.6999 | 0.6977 | 0.8298 | 0.8088 | 3628 | 12.2 |
| vit_base_patch16_224.augreg2_in21k_ft_in1k | wild-v1+v2 | 85.8 | 0.9310 | 0.9928 | 0.9656 | 0.7674 | 0.4913 | 0.7235 | 0.6691 | 0.8473 | 0.8288 | 1710 | 20.9 |
| convnext_small.fb_in22k_ft_in1k | wild-v1+v2 | 49.5 | 0.9245 | 0.9923 | 0.9881 | 0.7543 | 0.4229 | 0.7321 | 0.6782 | 0.8747 | 0.8130 | 1815 | 18.9 |
| convnext_tiny.fb_in22k_ft_in1k | wild-v1+v2 | 27.9 | 0.9221 | 0.9895 | 0.9868 | 0.7543 | 0.4142 | 0.7265 | 0.6750 | 0.8567 | 0.8234 | 2935 | 11.8 |
| swin_tiny_patch4_window7_224.ms_in22k_ft_in1k | wild-v1+v2 | 27.6 | 0.9238 | 0.9893 | 0.9624 | 0.7442 | 0.3992 | 0.7230 | 0.6676 | 0.8569 | 0.8151 | 2022 | 17.7 |
| vit_small_patch14_dinov2.lvd142m | wild-v1+v2 | 21.6 | 0.9176 | 0.9867 | 0.9555 | 0.7303 | 0.4093 | 0.6857 | 0.6135 | 0.8168 | 0.8133 | 3655 | 12.5 |

Reading the table:

* **In-domain accuracy is saturated (F1 0.98–0.99 for everything) and says almost nothing about field use.** The differences appear only on photographs from another source.
* **Backbone matters in the wild:** ImageNet-21k/22k backbones beat the ImageNet-1k pilot architecture (clean data, 23 shared classes: EfficientNet-B0 / MobileNetV3 33–34 %, versus ConvNeXt-S 48–49 %, ConvNeXt-T 46 %, ViT-B 45 %, Swin-T 44 %). EfficientNetV2-S (40 %) and EVA02-S (42 %) are in between; DINOv2-S was not better than the supervised 22k backbones once PlantWild was added.
* **Background-replacement augmentation** (lab leaves pasted onto random backgrounds) helped only slightly (+0.8–1.2 points on PlantWild).
* **The biggest effect is in-the-wild training data:** on the 23 shared classes, adding the PlantWild v1 dev half lifts ConvNeXt-S from 48 % to 73 % on the held-out PlantWild half; crop identification rises from 70 % to 86 %. Rejection of other plants rises from about 57 % to 92–95 % once the v2 other-plant classes are also in training (wild-v1 alone: about 74 % on the expanded test, because many v2 plants are unseen). With v2 added (47 classes incl. wheat) the same architecture reaches 73 % on all 3,942 photos (68 % on the 23 shared classes). The held-out half is disjoint from everything trained on (dHash clusters).
* Model choice among the `wild-v1+v2` backbones was made on validation macro-F1 only (ViT-B 0.931, ConvNeXt-S 0.925, Swin-T 0.924, ConvNeXt-T 0.922, DINOv2-S 0.918); the three best distinct architectures form the ensemble.

### 4.2 Final model: ensemble of ConvNeXt-S + ViT-B/16 + Swin-T (`webapp/models/active`)

* convnext_small.fb_in22k_ft_in1k + vit_base_patch16_224.augreg2_in21k_ft_in1k + swin_tiny_patch4_window7_224.ms_in22k_ft_in1k; 48 classes (47 diagnoses + the rejection class); probabilities are averaged over members and a horizontal-flip TTA, each member temperature-scaled on the validation set (T = 0.76, 0.74, 0.70).
* Decision policy (thresholds tuned on the field-like **validation part of the PlantWild dev half only**): rejection class if P(non-target) >= 0.48; **confident** if the top probability >= 0.92 with margin >= 0.1; **uncertain** if >= 0.3; otherwise unrecognised.

| Held-out set | Images | Accuracy | Macro-F1 | "Confident": coverage / accuracy |
|---|---:|---:|---:|---:|
| Test (training sources, lab + field) | 6097 | 0.993 | 0.966 | 0.83 / 0.998 |
| PlantDoc field photographs | 1294 | 0.780 | 0.482 | 0.28 / 0.875 |
| **PlantWild in-the-wild, held-out half** | 3942 | 0.750 (end-to-end) | 0.639 | 0.51 / 0.949 |

On the PlantWild held-out half: the crop is identified correctly in 87 % of photos; 94 % of the 5692 photos of *other* plants are rejected, and only 0.7 % of them get a "confident" diagnosis; 9 % of target-crop photos are wrongly rejected; accuracy among accepted photos is 0.822. About half of the photos reach "confident" and those are 95 % correct; the rest are shown as "needs checking".

### PlantWild held-out half (in-the-wild web photos), per crop

| Crop | Images | End-to-end acc | Crop identified | Rejected as non-target |
|---|---:|---:|---:|---:|
| apple | 688 | 0.696 | 0.935 | 0.167 |
| cucumber | 494 | 0.761 | 0.923 | 0.136 |
| grape | 413 | 0.833 | 0.942 | 0.061 |
| maize | 496 | 0.792 | 0.976 | 0.036 |
| potato | 331 | 0.698 | 0.927 | 0.106 |
| tomato | 828 | 0.589 | 0.928 | 0.092 |
| wheat | 692 | 0.935 | 0.987 | 0.010 |

Per condition (wheat):

| Condition | Images | Acc |
|---|---:|---:|
| brown_rust | 75 | 0.720 |
| head_scab | 122 | 1.000 |
| loose_smut | 96 | 0.990 |
| powdery_mildew | 118 | 0.949 |
| septoria | 82 | 0.939 |
| stem_rust | 58 | 0.897 |
| stripe_rust | 141 | 0.957 |

### PlantDoc field_test (real field photographs), per crop

| Crop | Images | Acc |
|---|---:|---:|
| apple | 124 | 0.903 |
| grape | 67 | 0.910 |
| maize | 172 | 0.826 |
| potato | 112 | 0.545 |
| tomato | 395 | 0.638 |

### Held-out test split of the training sources, per crop

| Crop | Images | Acc |
|---|---:|---:|
| apple | 324 | 0.985 |
| cucumber | 693 | 0.993 |
| grape | 583 | 1.000 |
| maize | 492 | 0.988 |
| potato | 360 | 0.978 |
| sunflower | 318 | 1.000 |
| tomato | 2230 | 0.997 |
| wheat | 219 | 0.968 |

Wheat, the main crop of the country, is the best-recognised crop in the wild test (93.5 %). Note that PlantWild's wheat classes include ear diseases (head scab, loose smut) whose photographs are visually very distinct, and that PlantWild has no healthy-wheat class (healthy wheat comes from the JIC and Holeta sets only). Tomato (10 look-alike classes) and potato are the weakest in the wild; early blight, late blight and septoria are frequently confused.

### 4.3 "Clean" fallback bundle (`webapp/models/clean`)

ConvNeXt-S (bg-aug) + ViT-B/16 + EVA02-S, trained **without** PlantWild; selected by PlantWild *dev-half* accuracy, calibrated on it, evaluated on the held-out half: accuracy 0.486 over the classes it supports, crop identified 69 %, other plants rejected 59 %. Honest calibration on field photographs pushes its confident threshold to the maximum, so it reports "needs checking" for almost every photograph. It exists for deployments that cannot use CC BY-NC-ND data. Switch with `AGRO_WEB_MODEL=webapp/models/clean`.

### 4.4 Serving

ONNX FP32, normalisation baked into the graph. PyTorch vs ONNX parity on 64 real validation photographs per member: max |delta logit| about 1e-5, 0 top-1 changes. Median request latency (decode + 3 models x 2 TTA views, CPU, Intel Core i5-10400F): about 0.44 s. Bundle size about 625 MB (not in Git). Class-activation maps (CAM) come from the first CNN member; the other members are used for classification only.

## 5. Measured limits

* **No photographs from Kazakhstan.** All data are public sets from other countries or the web; nothing here shows accuracy on Kazakhstani fields, varieties, cameras or seasons. The first required next step is a locally collected, expert-labelled field set and a re-evaluation.
* Wild accuracy is about 75 % across all conditions (about 82 % among accepted photos), so results must not be presented as a diagnosis. "Confident" results are about 95 % correct on the PlantWild held-out half, but that half comes from the same web distribution as the dev half used for training and for calibration.
* PlantWild labels come from the web and are not expert-verified for every image; PlantDoc and PlantWild partly share source websites (near-duplicates against training were removed with a dHash screen, which is not an exhaustive proof).
* Crops without usable open data (barley, sugar beet, flax, rapeseed, legumes) are not supported. Wheat-ear classes work only for photographs similar to the web images used.
* One seed per configuration and no confidence intervals: differences below about 1–2 points between backbones are not significant. The final ensemble was selected on validation F1 only, but several design decisions (augmentation v2, adding PlantWild) were taken after looking at the PlantWild test half for the *clean* models.
* PlantWild is CC BY-NC-ND 4.0: the "wild" weights are for non-commercial research and are not distributed; the repository contains code only.
* "Healthy" means no target disease visible on the photographed organ, not absence of all problems; the rejection class is a classifier, not proof that a photo is not a plant.

## 6. Reproduce

```bash
# Linux/WSL GPU machine (uv, CUDA 12.8+); paths relative to the repository root
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/bin/python timm huggingface_hub datasets pillow scikit-learn pandas onnx onnxruntime onnxscript tqdm pyyaml requests
git clone --depth 1 --filter=blob:none --sparse https://github.com/spMohanty/PlantVillage-Dataset.git data/pv && (cd data/pv && git sparse-checkout set raw/color raw/segmented leaf_grouping)
.venv/bin/python ml/kz/build_dataset.py fetch      # AgML sources, PlantDoc, DTD/Tiny ImageNet, Holeta wheat
# JIC wheat: Zenodo 7573133 -> data/raw/wheat_jic ; PlantWild v1/v2 (HF uqtwei2/PlantWild) -> data/raw/plantwild (v2 unzipped to plantwild/v2)
.venv/bin/python ml/kz/build_dataset.py pack && (cd ml/kz && ../../.venv/bin/python pack_masks.py)
(cd ml/kz && ../../.venv/bin/python build_external.py && ../../.venv/bin/python build_pack_w.py pack_w2)
ml/kz/run_benchmark.sh                                   # clean benchmark (2 GPU lanes)
PACK=pack_w2 PREFIX=w2 ml/kz/run_wild.sh 0 convnext_small.fb_in22k_ft_in1k vit_base_patch16_224.augreg2_in21k_ft_in1k swin_tiny_patch4_window7_224.ms_in22k_ft_in1k
.venv/bin/python ml/kz/eval_external.py <run names>      # PlantWild held-out half
.venv/bin/python ml/kz/export_bundle.py --runs <w2_...> --calib val --pack pack_w2 --out bundle_final
```

Each backbone trains in 5–21 minutes on one RTX 5070 Ti (10–12 epochs x 500 steps x batch 96, under 16 GB). Seed 17; GPU kernels are not bit-deterministic.
