# Scientific feasibility audit — 21 October 2026

**Actual work: primary-source/metadata audit only. No PlantDoc image downloads, no training and no new model results.** Metadata are retained under ignored `data/evidence/scientific-protocol/`; [machine-readable facts and SHA256](PLANTDOC_METADATA_AUDIT.json) are tracked. This audit does not replace the historical EfficientNet results.

## PlantDoc candidate

Primary author sources: [Cropped-PlantDoc repository](https://github.com/pratikkayal/PlantDoc-Dataset), pinned commit `5467f6012d78d1c446145d5f582da6096f852ae8`; [companion object-detection repository](https://github.com/pratikkayal/PlantDoc-Object-Detection-Dataset), pinned commit `4730a233a555b30ee98e0879c63ad25d82407455`. Both declare **CC BY 4.0** in their repository license. The paper describes internet-sourced images, multiple annotated leaves and derived crops; source attribution/individual web-image rights and labeling remain admission risks. [Primary paper](https://arxiv.org/html/1911.10317v1), DOI 10.1145/3371158.3371196.

The metadata endpoints were read completely (`truncated=false`). No image URLs were fetched. The current classification tree contains the four intended folder names; the detection CSV provides parent filenames, dimensions, classes and boxes:

| Canonical core label | Exact PlantDoc raw label | Classification file entries train/test | Detector annotation rows train/test | Distinct valid box rows | Distinct parent filename proxies |
|---|---|---:|---:|---:|---:|
| potato.early_blight | Potato leaf early blight | 109 / 8 | 316 / 17 | 333 | 120 |
| potato.late_blight | Potato leaf late blight | 97 / 8 | 240 / 10 | 250 | 106 |
| tomato.early_blight | Tomato Early blight leaf | 79 / 9 | 195 / 19 | 214 | 90 |
| tomato.late_blight | Tomato leaf late blight | 101 / 10 | 207 / 14 | 221 | 112 |

These are **metadata counts, not decoded leaves, accepted samples or independent plants**. All 1,018 core box rows satisfy declared CSV geometry; image dimensions have not been verified against actual bytes. The classification tree has 421 core image entries, not all 1,018 detector boxes. The two complete detection CSVs contain **8,469 + 452 = 8,921 annotation rows**; the paper's **9,216** reported crop/box count belongs to its described release. Those numbers are not silently equated or summed. Reconstruct all eligible core leaf crops from the companion original/box linkage rather than assuming a class-folder filename is a complete independently grouped leaf corpus. Generic `Tomato leaf` and `Potato leaf` are not substitutes for early/late blight.

**Feasibility:** the four-class candidate has primary metadata support and enough nominal parents to justify the planned audit. **Scientific admission: NO-GO now**, until actual file rights/label mapping, image/bbox checks, parent/leaf/session links, cross-source duplicates and post-exclusion group/split counts pass the [data gates](SCIENTIFIC_DATA_REQUIREMENTS.md). Unknown original plant/farm identities remain unknown. Using all provider TRAIN/TEST annotations for external evaluation does not authorize target tuning. File names and declared licenses do not prove absence of source overlap or third-party rights issues.

Reproduce metadata facts (stdlib only, small files):

```bash
uv run python ml/research/audit_plantdoc_metadata.py --fetch
uv run python ml/research/audit_plantdoc_metadata.py
```

The first command fetches only allowlisted GitHub JSON, README/LICENSE and annotation CSV files. Images are never requested. The stored evidence and output retain commit, license/metadata hashes and exact raw/canonical mapping. No contact/request was sent to source authors.

## Literature identity and scope checks

| Work | Primary evidence actually checked | Safe claim for this protocol | Limit |
|---|---|---|---|
| Picon et al., 2019 | [Author institution repository](https://dsp.tecnalia.com/items/28bc0f81-e25b-4957-9a00-cae5e37f0c8b), DOI **10.1016/j.compag.2019.105093**, *Crop conditional Convolutional Neural Networks for massive multi-crop plant disease classification over cell phone acquired images taken on real field conditions* | Crop-conditioned CNNs for plant disease already exist. | Institutional metadata/abstract verifies identity and broad scope; no AgroVision replication or Kazakhstan result is implied. |
| Lee, Goëau, Bonnet, Joly, 2021 | [Author university bibliography](https://www.swinburne.edu.my/staff/lee-sue-han/), [DOI registration metadata](https://api.crossref.org/works/10.1109/ICPR48806.2021.9412643), [official ICPR poster](https://ailb-web.ing.unimore.it/icpr/media/slides/11251.pdf); DOI **10.1109/ICPR48806.2021.9412643**, *Conditional Multi-Task learning for Plant Disease Identification* | DOI metadata identifies Sue Han Lee (the poster text has a name typo); published plant-disease conditional feature fusion includes FiLM; universal novelty of FiLM is not a valid thesis claim. | Poster compares approaches across sources and explicitly avoids one universally best CMTL approach. This does not establish our C1−C0 result. |
| **Kun Xiang, Danxi Shi, Xiangbo Zhu, 2026** | [Publisher full article](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2026.1826962/full), **22 May 2026**, DOI **10.3389/fpls.2026.1826962**, *Quantifying the reliability gap in cross-domain plant disease classification: benchmarking the limited efficacy of standard mitigation techniques under controlled-to-field shift* | Verified real article on PlantVillage→PlantDoc reliability, parent-image-aware evaluation, calibration and rejection limitations. | Main case is ResNet-50; it is not a novel crop-FiLM paper, our ResNet18 ablation, or a Kazakhstan validation. Calibration/selection analyses remain secondary here. |

The contribution proposed by AgroVision is the controlled **incremental C1−C0 effect under fully held-out source**, with equal known-crop loss/mask access, paired seeds, group uncertainty and explicit local-data limits. No global claim of first crop conditioning, first FiLM application or guaranteed gain is made. Existing historical metrics do not answer this new scientific contrast.

## Technical feasibility decision

The protocol/configuration, this source audit and consistency checks are available as technical prerequisites. A complete new experiment, local pilot/final collection and diagnostic admission are not reported as completed. Candidate class availability is supported by metadata, while image-level admission remains pending the strict gates. There are no new source-held-out predictions or model-training measurements in this audit.
