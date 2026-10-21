# Scientific protocol: crop information under source shift

**Status: planned, not measured; version `crop-conditioning-source-shift-v1-planned`.** This version specifies a controlled crop-conditioning experiment under a fully held-out image source. It does not replace the working historical EfficientNet application baseline (`b65ec30`), retrain it, change its metrics or activate a new diagnostic model. The machine-readable configuration is [scientific_experiment_config.yaml](scientific_experiment_config.yaml); it uses JSON syntax, a YAML 1.2 subset, so its consistency checker needs no new parser dependency.

## Question, hypothesis and scope

Does conditioning intermediate visual features on an already known crop add cross-source classification benefit beyond giving the same crop to the loss and decision mask? The primary contrast is **C1 minus C0 crop-balanced macro-F1 on a completely held-out image source**. A positive effect is a hypothesis, not an expected result to be manufactured. The practical-effect reference is **0.02 absolute F1 (2 percentage points)**, recorded before final evaluation; it is a project decision, not a universal agronomic safety threshold.

The initial scientific core has exactly four source-aligned labels: `potato.early_blight`, `potato.late_blight`, `tomato.early_blight`, `tomato.late_blight`. Healthy appearance, wheat and other diseases are excluded from this confirmatory core. Their admission needs separate compatible source coverage, rights/group audit and a protocol revision before their test is opened. These scientific IDs do not change the existing application's catalogue.

The study is leaf-level classification with known crop, not automatic crop identification, leaf detection or the complete phone-photo pipeline. PlantVillage contributes audited original color images of individual leaves, without invented boxes. PlantDoc contributes **all eligible annotated leaf boxes from original images**, retaining their parents. Web-source transfer is not automatically a Kazakhstan field test.

## Controlled arms

All arms use the same TorchVision ResNet18 ImageNet V1 initialization, four-logit head, FiLM module, parameter shapes, source images, sample ordering, augmentation, optimizer budget and validation rule within each paired seed.

| Arm | FiLM input | Training denominator | Primary decoding |
|---|---|---|---|
| G0 | Learnable constant token | All four logits: global cross-entropy | Known-crop class mask, then argmax |
| C0 | The same constant token | Only the two classes of the true known crop | The same known-crop mask, then argmax |
| C1 | True known crop token | The same within-crop cross-entropy as C0 | The same known-crop mask, then argmax |

For logits z, target y and known crop c, global loss is `-z_y + logsumexp(z_all)`. Within-crop loss is `-z_y + logsumexp(z_classes_of_c)`. The class mask, target labels and eligible rows are identical for C0/C1; wrong crop labels are not used during primary training. All arms receive the same crop at primary decoding. Thus C1−C0 isolates the feature-conditioning addition; C0−G0 separately studies the loss. G0's global unmasked argmax is an additional evaluation of the same trained checkpoint, without another training run.

**FiLM location:** `layer3` produces `N×256×14×14` at 224 px; apply `(1+Δγ(token))*features+β(token)` before the common nonlinear **layer4**, then shared average pooling and linear classification. Token embedding dimension 16, MLP 16→64→512 outputs 256 Δγ and 256 β coefficients, broadcast spatially. Last FiLM projection is zero-initialized, making every arm initially identity-modulated. All three token embeddings and identical module shapes exist in every arm; only the routed token differs. The complete initial state dictionary, including head/FiLM, is cloned across arms per seed and hashed. Crop FiLM directly before the final linear head is prohibited: it could reduce to a head reparameterization and does not answer this question.

## Data admission and source separation

[Scientific data requirements](../docs/data/SCIENTIFIC_DATA_REQUIREMENTS.md) defines the strict gates. Current admission is **NO-GO pending the image-level rights, mapping, parent and duplicate audits**; primary metadata establishes candidate class availability only. No main scientific training has run.

The candidate direction is PlantVillage development → wholly held-out PlantDoc. No PlantDoc image, target label prediction or statistic is used for training, augmentation design, checkpoint/threshold selection, batch normalization adaptation or hyperparameter choice. Source metadata may establish labels, provenance and predeclared eligibility; that is not a license to tune on target predictions. No image-level result from PlantDoc has been generated in this audit.

Before training, connect all known parent images, leaf/plant/session IDs and exact/near-duplicate links into groups. All crops/derived images from one source image remain together. Quarantine entire components that connect development and external sources. Audit web URLs/reposts as well as hashes; a new filename is not a new plant. Unknown biological IDs remain unknown; source-image groups are not represented as proven independent plants/farms.

Freeze ontology, inclusion/exclusion decisions, licenses, byte hashes and group/split manifests before training. Source groups are split 70/15/5/10 into train, model-selection validation, calibration-only validation and internal test, preserving groups over exact fractions. Historical pilot photos already examined are not a fresh internal final test; they may enter development with that history recorded, while fresh source groups are reserved for internal final reporting. No crop sibling, augmentation or duplicate can cross roles. PlantDoc remains wholly external; its provider TRAIN/TEST names do not authorize using any part for adaptation in this primary protocol.

A model-independent eligibility review may remove invalid/ambiguous boxes or unresolved labels **before** the test manifest freezes, recording reasons. Do not discard later errors, low scores or inconvenient crops. All valid annotated core boxes are retained, including multiple boxes from one parent. If a class or sufficient groups is absent, stop the four-class core rather than rename labels, switch to another test or silently shrink the question.

## Paired training budget

Use paired seeds **17, 41, 73**, preserving all seed results. Source sample order and augmentation are keyed by `(seed, epoch, image_id)`, independent of arm, so model-specific RNG calls do not change the data stream. Crop tokens are never inferred from the test image.

The planned common recipe is 20 epochs: 3 epochs train FiLM/head with the backbone frozen; 17 epochs also train layer4, while conv1–layer3 remain frozen. AdamW, weight decay 1e−4; FiLM/head LR 1e−3, layer4 LR 1e−4, cosine schedule per stage. Freeze BN running statistics and affine parameters identically; reapply this after model.train(). Physical batch 8, accumulation 4, effective batch 32, FP16 AMP; partial final accumulation windows use their actual size. All arms run the same full epoch/update budget, with no arm-specific early stopping. Select each checkpoint by source-selection-validation crop-balanced macro-F1; ties choose the earliest epoch. No external or internal final test decides epochs, seeds or hyperparameters.

One fixed hyperparameter recipe is planned, not unequal per-arm searches. If source-only sanity checks require a revision, record the decision and re-freeze the common recipe before the external test. Nonfinite/OOM failure is reported; batch changes apply to all arms, not the failing arm alone. Heavy jobs are serialized under the repository's memory guard (≥3 GiB available, bounded training scope). Actual scientific training remains unimplemented.

## Primary metric, uncertainty and interpretation

For each crop, compute ordinary class F1 on **all** eligible forced-choice predictions, average states equally within crop, then average crops equally. In this balanced four-class core this equals macro-F1 over four classes; the crop-first definition remains explicit for future unequal class counts. No abstention, confidence threshold, selective coverage or OOD filter enters the primary endpoint. Report per-class support/precision/recall/F1 and confusion matrices, including failures rather than hiding them.

For seed s, let `Δ_s = F1_C1,s − F1_C0,s`. The primary point estimate is the mean of the three paired Δ values. The **paired grouped 95% percentile interval** resamples whole external parent/leaf/dedup groups 10,000 times (RNG seed 20261021), stratified by each group's crop composition (potato-only, tomato-only, mixed). Keep every annotation of a sampled group with its multiplicity; use the same group draw for all arms **and all fixed training seeds**. Compute each seed's contrast on that draw, then average contrasts; take percentiles 2.5 and 97.5. Do not bootstrap individual crops or resample seeds inside this interval. If a replicate loses a core class, redraw and report the invalid fraction; above 5% invalid draws, mark interval estimation unstable instead of silently reporting it.

Separately publish every arm/seed metric, the three paired deltas, mean, sample SD, range and any run failures. The grouped interval is conditional on these trained seeds and the sampled source-group framework; it is not a confidence interval for all retrainings, farms or Kazakhstan. Where biological identities are unavailable, state that grouped resampling uses known parent/dedup proxies and cannot prove biological independence.

Interpret an interval crossing zero as inconclusive about the effect, not evidence of benefit. An interval wholly positive but below 0.02 does not establish practical benefit; compare the estimate and interval with the predeclared threshold without moving it after testing. Negative effects and wide intervals remain valid results. C0−G0 and G0 unmasked decoding are secondary analyses, not substitutes if the primary contrast fails. Calibration, rejection, wrong-crop and unknown/OOD tests are additional studies and cannot rescue the primary F1 through selective abstention.

## Local applicability and release boundary

A separate local pilot targets 10–20 independent cases per core class (40–80 total), with photographer/location/session/case IDs, consent and reviewed reference labels. A later independent local final test targets 50–100 **new** cases per class (200–400 total); pilot cases do not enter final test. These are collection planning ranges, not guaranteed statistical power. Refine sample planning after the pilot, accounting for clustering, attainable CI width and class difficulty before final enrollment. Without real local data and reference evidence, conclusions remain public-source transfer only; a supervisor discussion must record any scope reduction.

C0/C1's loss identifies `p(condition | image, crop)`, not a globally calibrated probability of the selected crop. Summing conditional scores cannot recover original crop mass, detect wrong crops or establish unseen-disease rejection. The existing application `global_joint` runtime, abstaining research behavior and release checks are unchanged. A future conditional model needs an explicitly versioned score contract/adapter/policy and its own validation before application integration. A research checkpoint is never automatically a diagnostic release.

## Sources checked and deliverables

[Primary-source feasibility audit](../docs/data/SCIENTIFIC_SOURCE_AUDIT.md) verifies the PlantDoc candidate and distinguishes metadata from admitted images. Picon et al. (2019), DOI [10.1016/j.compag.2019.105093](https://doi.org/10.1016/j.compag.2019.105093), already study crop-conditioned CNNs. Lee et al. (2021), DOI [10.1109/ICPR48806.2021.9412643](https://doi.org/10.1109/ICPR48806.2021.9412643), include conditional FiLM in plant-disease work; their [official ICPR poster](https://ailb-web.ing.unimore.it/icpr/media/slides/11251.pdf) does not establish a universal winning conditional method. Xiang, Shi and Zhu (2026), DOI [10.3389/fpls.2026.1826962](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2026.1826962/full), examine controlled-to-field reliability and calibration/selection limits; this is not evidence for a new FiLM architecture or a reproduction by AgroVision. No numerical result from these papers is relabeled as our own.

This version provides a protocol, machine-readable configuration, source feasibility audit and consistency checks, not a new training runner or completed comparison. The nine controlled runs, local collection, expert review, confidence intervals and release evaluation remain uncompleted. Required run outputs are config/code/dirty snapshots, source/class/split/initial-state hashes, seed and sampler/augmentation traces, per-image raw logits/reference/crop/group IDs, all per-seed results, grouped intervals, exclusions and failure logs.
