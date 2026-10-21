# Shared runtime integration interface (owned by main agent)

Runtime code location: `ml/runtime/agrovision_runtime/`; Python import `agrovision_runtime`. Root uv project installs it with API; runtime code must not import FastAPI, SQLAlchemy or training.

Required public exports in `__init__.py`:

```python
from pathlib import Path
from dataclasses import dataclass

class BundleValidationError(ValueError): ...
@dataclass(frozen=True)
class Bundle:
    directory: Path
    manifest: dict
    def snapshot(self) -> dict: ...
    def supports(self, crop_id: str, organ: str = 'leaf') -> bool: ...

def validate_bundle(directory: Path) -> Bundle: ...
class OnnxPredictor:
    def __init__(self, bundle: Bundle): ...
    def predict(self, image_bytes: bytes, crop_id: str, organ: str = 'leaf') -> dict: ...
```

`snapshot()` returns exactly model fields: `version`, `artifact_sha256`, `preprocessing_version`, `decision_policy_version`, strings. Backend stores full manifest and bundle directory in immutable model records, keyed by version and hash; job pins snapshot. `supports` returns true only for actually admitted manifest crop/organ capabilities. Backend never infers support from classes in illustrative docs.

`predict()` returns Foundation AssessmentResult dict: outcome, reason_codes, prediction, candidates, quality {status,flags}, next_action. Candidate: class_id,crop_id,condition_id,score,score_kind,score_space. Preserve global scores; no crop renormalization. Quality default not_assessed if no validated rules. Never healthy by default.

Minimum manifest proposed shape (ML agent may extend, but coordinate breaking changes):
- version; artifact {file,sha256}; ordered labels [{class_id,crop_id,condition_id,organ}]; labels_sha256 (canonical JSON list, sort_keys=True,separators=(',',':'), utf8); metadata in ONNX records same digest/preprocessing_version.
- input {name,shape:[1,3,224,224],dtype:'float32'}; output {name,shape:[1,N],semantics:'logits'}
- preprocessing {version,resize_shorter_side:256,center_crop:224,interpolation:'bilinear',color_mode:'RGB',apply_exif_orientation:true,mean:[...],std:[...]}
- score_space:'global_joint'; policy {version,status:'validated',joint_score_threshold:float,selected_crop_mass_threshold:float}; calibration {kind:'none'} or validated artifact.
- provenance {dataset_manifest_sha256,split_manifest_sha256,code_commit,evaluation_report}; release_status ('validated' only for production; research artifacts remain non-active without validation).

No actual trained verified artifact exists initially. Root default has no model and production must return 503. Dev synthetic is handled explicitly by backend (version dev-synthetic-v1) and returns inconclusive only; ML agent need not implement stub.

Model artifact folders, datasets and runs at repository root `artifacts/`, `data/`, `runs/` are Git-ignored. Small reports/manifests without private photos may be committed under docs/development. Training project `ml/training` has its own uv lock and torch dependencies; do not change root backend deps/locks concurrently. Main agent integrates runtime dependency requirements (onnxruntime,numpy,Pillow).

## Research-only extension (2026-10-21)

Additional public exports:

```python
def validate_research_bundle(directory: Path) -> Bundle: ...
class ResearchOnnxPredictor:
    def __init__(self, bundle: Bundle): ...
    def predict(self, image_bytes: bytes, crop_id: str, organ: str = 'leaf') -> dict: ...
```

Both validators require `preprocessing_sha256`, the SHA256 of canonical full preprocessing JSON (`sort_keys=True,separators=(',',':')`, UTF-8), in the manifest **and** ONNX metadata. This catches normalization/config edits that reuse a version string. Existing `snapshot()` remains unchanged.

Research admission requires `release_status: research`, `policy.status: unvalidated`, a nonempty policy version and otherwise the same integrity, labels, tensor, preprocessing and provenance checks. Research thresholds may be `null`; this is never permitted by production admission. Research does not admit a `validated` release implicitly, and production does not admit a research bundle.

`ResearchOnnxPredictor` always returns `outcome: inconclusive`, `prediction: null`, `reason_codes` including `research_model_unvalidated`; real crop-filtered candidates preserve **global** model scores (`score_kind: model_score`). Even a near-1 healthy candidate never becomes a healthy conclusion. Unsupported crop/organ remains inconclusive with an additional reason and selection action. No threshold guessing, implicit activation or production fallback is provided.

The backend must explicitly gate this separate mode to development/test plus a configured research bundle path. Research candidate display must be visibly distinguished from a validated diagnosis. The current joint research bundle `artifacts/pilot-joint-efficientnet-b0-seed17` supports potato and tomato early blight, late blight and healthy appearance, plus wheat healthy appearance, stripe rust and the broad original `septoria_source_label`. Wheat biological/session independence remains unverified; its available groups are dedup proxies.

Runtime integrity/resource notes: validated `Bundle` objects internally pin the exact immutable ONNX bytes that were hashed and inspected; predictor sessions load those checked bytes rather than reopening the artifact path. The public two-argument `Bundle(directory, manifest)` construction remains accepted, and predictor constructors validate such input before use. Artifact path replacement during ORT session creation cannot switch model weights under an older checksum. Every CPU session explicitly uses 4 intra-op and 1 inter-op threads; higher-level API caches may avoid repeated validation, but the runtime itself does not hide file changes behind a path-only cache.
