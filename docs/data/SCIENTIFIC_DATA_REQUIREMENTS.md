# Scientific data requirements

**Planned protocol, not an admitted scientific dataset.** The canonical tracked document is here because root `data/` is Git-ignored. Source files, photos and working manifests remain under ignored `data/`; aggregate audit facts may be tracked. Read with [scientific protocol](../../ml/SCIENTIFIC_PROTOCOL.md) and [metadata-only audit](SCIENTIFIC_SOURCE_AUDIT.md).

## Four-class core and views

The initial eligible labels are exactly potato early blight, potato late blight, tomato early blight and tomato late blight. Preserve raw strings in addition to canonical IDs. PlantVillage single-leaf color images require original-byte/leaf links, not fabricated bounding boxes. For PlantDoc use every eligible annotated leaf box from the companion original-image detector source, not a convenient subset of pre-cropped files. Maintain original filename, box coordinates, original-byte hash and source-image parent for each derived crop. All crops and transformations of a parent belong to one group.

A box is eligible only after matching the real decoded image dimensions, a nonempty in-bounds region, core crop/condition mapping and label review. Mixed or unresolved references remain labeled unresolved/quarantined; they are not forced into one of the four classes. Images without defensible leaf/context labels are excluded before the primary manifest freezes, with a reason. Keep the source photograph and annotation rather than mistaking lesion area or crop area for disease severity.

## Required fields and linkage

Each record must retain `image_id`, `source_dataset`, exact `source_version`, source URL/filename, byte SHA256, original `raw_label`, canonical crop/condition, organ, reference-evidence level, annotation coordinates/version, `parent_image_id`, `parent_sha256`, known `leaf_id`/`plant_id`/`session_id`, `dedup_cluster_id`, final `split_group_id`, role, rights/license evidence and admission decision. Unknown biological identifiers remain null with an explicit reason. A filename/hash identifies a file; it does not prove an independent plant.

Connect parent-child, known leaf/session and exact/near-duplicate relations transitively **before** splitting. Audit original images and derived crops, including web URL reposts, perceptual candidates and cross-source mirrors. Candidate near duplicates require review rather than assuming the threshold proves equivalence. Entire cross-source connected components are quarantined from the primary comparison. Freeze all relation decisions, exclusions and hashes; a later correction creates a new dataset/protocol version, never a silent test rewrite.

Repository-level CC BY declarations are recorded but do not erase third-party web-image rights uncertainty. The data reviewer must record the permitted academic storage/training/transformation and display/redistribution purposes, attribution, and evidence/limitations for this exact source version. Unknown/unapproved rights prohibit admission for that operation. Public download access is not approval. Local participants require appropriate consent and access controls; user uploads never automatically become training data.

## Strict go/no-go gates

The four-class scientific experiment starts only when **all** of these hold:

1. Every core class has a reviewed semantic mapping in both development and source-held-out data, with no substitution of generic `leaf`, `fungi`, healthy or unresolved categories.
2. Rights for the intended research operations are accepted and recorded for actual files/version.
3. Real image decoding, annotation/image geometry and symptom-retention checks pass; original-parent and available leaf/session links are audited.
4. Exact and reviewed near-duplicate audits across sources and roles are complete; no linked group overlaps roles or contaminates the held-out source.
5. After exclusions, each class has at least **50 source training groups**, **10 source model-selection groups** and **20 external parent/dedup groups**. These are predeclared feasibility floors, **not a power guarantee or proof of biological independence**. Report calibration/internal counts too; source validation cannot be borrowed from the external source to fill a shortage.
6. All class/group counts, source/rights/mapping decisions and dataset/split manifests are frozen and hashed before training; the external source is absent from all model tuning and adaptation.

Missing even one gate means **NO-GO for the four-class confirmatory comparison**. Do not quietly merge early/late blight, drop a difficult culture, use per-image random splits, reuse an examined historical test as fresh evidence or include target data in normalization/adaptation. A changed question requires a documented protocol revision before testing. Metadata presence alone cannot satisfy these gates.

Current decision: **NO-GO pending image-level audit**. The metadata-only PlantDoc audit confirms all four raw class names and plausible parent/box counts, but no PlantDoc images have been downloaded/decoded by this audit, no per-image rights/labels/duplicates admitted, and no independent biological group counts established. Historical EfficientNet pilot files are not the newly admitted scientific dataset.

## Source and local split roles

PlantVillage is the candidate development source: group splits train/selection-validation/calibration-validation/internal-test = 70/15/5/10, preserving groups over exact proportions. Historical pilot images already examined are development-history data, not fresh internal final tests. PlantDoc is entirely held out, including its provider TRAIN and TEST folders; both can supply eligible external boxes, neither can supply training or adaptation in this protocol. No automatic target calibration or feature-statistic fitting is permitted.

For Kazakhstan, plan 10–20 independent cases per core class in a pilot, then 50–100 **new** cases per class for local final assessment. Case/plant/session/farm clusters, capture conditions, consent, reviewer/evidence levels and disagreement rules must be explicit. Pilot and final groups are disjoint. Revisit sample planning after pilot variability and clustering, before final collection; ranges do not establish statistical sufficiency. If local reference data are unavailable, limit the evaluation scope and conclusions to public-source transfer.

## Conditional extensions

Wheat needs at least two source-compatible states per wheat experiment, defensible biological/parent grouping, rights and an independent source/local test. The existing Ethiopian three-label D05 pilot and its dedup proxies alone do not qualify it for this core. Healthy and other conditions likewise require shared-source reference coverage; no field-wide healthy or unknown-disease detector is inferred from adding a class. Extensions are secondary and separately preregistered, not changes to the four-class primary endpoint after results.
