"""Framework-independent, fail-closed ONNX bundle runtime."""

import copy
import hashlib
import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

# Admission guards added after the measured pilot run. Accepted-image pixel
# operations and preprocessing version remain unchanged; these are allocation
# budgets, not a new learned preprocessing transform.
MAX_SOURCE_PIXELS = 20_000_000
MAX_PREPROCESS_PIXELS = 4_000_000
MAX_PREPROCESS_DIMENSION = 16_384


class InputImageError(ValueError):
    """An image cannot be processed within the serving allocation budget."""


class BundleValidationError(ValueError):
    pass


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _require(condition, message):
    if not condition:
        raise BundleValidationError(message)


def _session(artifact: bytes):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    return ort.InferenceSession(artifact, sess_options=options, providers=["CPUExecutionProvider"])


@dataclass(frozen=True)
class Bundle:
    directory: Path
    manifest: dict
    _artifact_bytes: bytes = field(default=b"", init=False, repr=False, compare=False)
    _manifest_sha256: str = field(default="", init=False, repr=False, compare=False)
    _admission: str = field(default="", init=False, repr=False, compare=False)

    def snapshot(self) -> dict:
        m = self.manifest
        return dict(
            version=m["version"],
            artifact_sha256=m["artifact"]["sha256"],
            preprocessing_version=m["preprocessing"]["version"],
            decision_policy_version=m["policy"]["version"],
        )

    def supports(self, crop_id: str, organ: str = "leaf") -> bool:
        return any(x["crop_id"] == crop_id and x["organ"] == organ for x in self.manifest["labels"])


def _validate_bundle(directory: Path, *, research: bool) -> Bundle:
    directory = Path(directory).resolve()
    try:
        m = json.loads((directory / "manifest.json").read_text())
        _require(
            m["release_status"] == ("research" if research else "validated"),
            "release is not admitted for this runtime",
        )
        _require(isinstance(m["version"], str) and m["version"], "bundle contract violation")
        artifact = (directory / m["artifact"]["file"]).resolve()
        _require(artifact.is_relative_to(directory), "artifact path escapes bundle")
        artifact_bytes = artifact.read_bytes()
        _require(_sha(artifact_bytes) == m["artifact"]["sha256"], "artifact checksum mismatch")
        labels = m["labels"]
        _require(
            len(labels) >= 2 and len({x["class_id"] for x in labels}) == len(labels),
            "bundle contract violation",
        )
        _require(
            all(
                all(
                    isinstance(label[key], str) and label[key]
                    for key in ("class_id", "crop_id", "condition_id", "organ")
                )
                for label in labels
            ),
            "labels require nonempty class/crop/condition/organ identifiers",
        )
        digest = _sha(json.dumps(labels, sort_keys=True, separators=(",", ":")).encode())
        _require(digest == m["labels_sha256"], "label order/digest mismatch")
        p = m["preprocessing"]
        preprocessing_digest = _sha(json.dumps(p, sort_keys=True, separators=(",", ":")).encode())
        _require(m["preprocessing_sha256"] == preprocessing_digest, "preprocessing digest mismatch")
        _require(
            p["color_mode"] == "RGB" and p["apply_exif_orientation"] is True, "bundle contract violation"
        )
        _require(
            p["interpolation"] == "bilinear"
            and p["resize_shorter_side"] == 256
            and (p["center_crop"] == 224),
            "bundle contract violation",
        )
        _require(len(p["mean"]) == len(p["std"]) == 3, "bundle contract violation")
        _require(
            all(type(v) in (int, float) and math.isfinite(v) for v in p["mean"] + p["std"]),
            "bundle contract violation",
        )
        _require(all(v > 0 for v in p["std"]), "bundle contract violation")
        _require(
            m["input"]["shape"] == [1, 3, 224, 224] and m["input"]["dtype"] == "float32",
            "bundle contract violation",
        )
        _require(
            m["output"]["shape"] == [1, len(labels)] and m["output"]["semantics"] == "logits",
            "bundle contract violation",
        )
        _require(
            m["score_space"] == "global_joint" and m["calibration"] == {"kind": "none"},
            "bundle contract violation",
        )
        policy = m["policy"]
        _require(
            policy["status"] == ("unvalidated" if research else "validated")
            and isinstance(policy["version"], str)
            and policy["version"],
            "bundle contract violation",
        )
        for key in ("joint_score_threshold", "selected_crop_mass_threshold"):
            value = policy[key]
            if research and value is None:
                continue
            _require(
                type(value) in (float, int) and math.isfinite(value) and (0 < value <= 1),
                "invalid policy threshold",
            )
        for key in ("dataset_manifest_sha256", "split_manifest_sha256", "code_commit", "evaluation_report"):
            _require(isinstance(m["provenance"][key], str) and m["provenance"][key], "missing provenance")
        session = _session(artifact_bytes)
        metadata = session.get_modelmeta().custom_metadata_map
        _require(
            metadata.get("preprocessing_sha256") == preprocessing_digest, "ONNX preprocessing digest mismatch"
        )
        _require(metadata.get("labels_sha256") == digest, "ONNX label order mismatch")
        _require(metadata.get("preprocessing_version") == p["version"], "ONNX preprocessing mismatch")
        i, o = (session.get_inputs(), session.get_outputs())
        _require(len(i) == len(o) == 1, "bundle contract violation")
        _require(
            i[0].name == m["input"]["name"]
            and i[0].shape == m["input"]["shape"]
            and (i[0].type == "tensor(float)"),
            "bundle contract violation",
        )
        _require(
            o[0].name == m["output"]["name"]
            and o[0].shape == m["output"]["shape"]
            and (o[0].type == "tensor(float)"),
            "bundle contract violation",
        )
    except Exception as exc:
        raise BundleValidationError(f"Invalid model bundle: {exc}") from exc
    return _admit(directory, m, artifact_bytes, "research" if research else "validated")


def _admit(directory: Path, manifest: dict, artifact: bytes, admission: str) -> Bundle:
    bundle = Bundle(directory, manifest)
    object.__setattr__(bundle, "_artifact_bytes", artifact)
    object.__setattr__(
        bundle, "_manifest_sha256", _sha(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    )
    object.__setattr__(bundle, "_admission", admission)
    return bundle


def _pin_bundle(bundle: Bundle, *, research: bool) -> Bundle:
    expected = "research" if research else "validated"
    if not bundle._admission:
        return _validate_bundle(bundle.directory, research=research)
    _require(bundle._admission == expected, "release is not admitted for this runtime")
    manifest = copy.deepcopy(bundle.manifest)
    digest = _sha(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    _require(digest == bundle._manifest_sha256, "validated bundle manifest changed")
    return _admit(bundle.directory, manifest, bundle._artifact_bytes, expected)


def validate_bundle(directory: Path) -> Bundle:
    """Admit only an explicitly validated diagnostic release."""
    return _validate_bundle(directory, research=False)


def validate_research_bundle(directory: Path) -> Bundle:
    """Validate research artifact integrity without admitting diagnostic output."""
    return _validate_bundle(directory, research=True)


def validate_image_geometry(
    width: int, height: int, resize_shorter_side: int = 256, *, max_source_pixels: int = MAX_SOURCE_PIXELS
) -> tuple[int, int]:
    """Check source and projected resize geometry before any image allocation.

    EXIF orientation only swaps dimensions, preserving both budget predicates.
    An explicit research caller may raise the source cap for historical 24 MP
    fixtures; the intermediate budget always remains fixed at 4 MP.
    """
    if width <= 0 or height <= 0 or type(max_source_pixels) is not int or max_source_pixels <= 0:
        raise InputImageError("invalid source image geometry")
    if width * height > max_source_pixels:
        raise InputImageError("source image pixel budget exceeded")
    if type(resize_shorter_side) is not int or resize_shorter_side <= 0:
        raise InputImageError("invalid preprocessing resize geometry")
    scale = resize_shorter_side / min(width, height)
    projected = (int(width * scale), int(height * scale))
    if (
        min(projected) <= 0
        or max(projected) > MAX_PREPROCESS_DIMENSION
        or projected[0] * projected[1] > MAX_PREPROCESS_PIXELS
    ):
        raise InputImageError("preprocessing image allocation budget exceeded")
    return projected


def preprocess(image_bytes: bytes, config: dict, *, max_source_pixels: int = MAX_SOURCE_PIXELS) -> np.ndarray:
    with Image.open(io.BytesIO(image_bytes)) as original:
        validate_image_geometry(
            *original.size, config["resize_shorter_side"], max_source_pixels=max_source_pixels
        )
        image = ImageOps.exif_transpose(original).convert("RGB")
        projected = validate_image_geometry(
            *image.size, config["resize_shorter_side"], max_source_pixels=max_source_pixels
        )
        image = image.resize(projected, Image.Resampling.BILINEAR)
        size = config["center_crop"]
        left, top = (round((image.width - size) / 2), round((image.height - size) / 2))
        image = image.crop((left, top, left + size, top + size))
        values = np.asarray(image, dtype=np.float32) / 255.0
    values = (values - np.asarray(config["mean"], dtype=np.float32)) / np.asarray(
        config["std"], dtype=np.float32
    )
    return values.transpose(2, 0, 1)[None].astype(np.float32)


def _empty_result() -> dict:
    return dict(
        outcome="inconclusive",
        reason_codes=[],
        prediction=None,
        candidates=[],
        quality={"status": "not_assessed", "flags": []},
        next_action="consult_expert",
    )


class OnnxPredictor:
    def __init__(self, bundle: Bundle):
        self.bundle = _pin_bundle(bundle, research=False)
        self._create_session()

    def _create_session(self):
        self.session = _session(self.bundle._artifact_bytes)

    def _infer(self, image_bytes: bytes, crop_id: str, organ: str) -> list[dict]:
        m = self.bundle.manifest
        values = preprocess(image_bytes, m["preprocessing"])
        logits = np.asarray(self.session.run([m["output"]["name"]], {m["input"]["name"]: values})[0])[0]
        if not np.isfinite(logits).all():
            raise ValueError("nonfinite_model_output")
        scores = np.exp(logits.astype(np.float64) - logits.max())
        scores /= scores.sum()
        candidates = [
            dict(
                class_id=x["class_id"],
                crop_id=x["crop_id"],
                condition_id=x["condition_id"],
                score=float(scores[index]),
                score_kind="model_score",
                score_space="global_joint",
            )
            for index, x in enumerate(m["labels"])
            if x["crop_id"] == crop_id and x["organ"] == organ
        ]
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def predict(self, image_bytes: bytes, crop_id: str, organ: str = "leaf") -> dict:
        m = self.bundle.manifest
        result = _empty_result()
        if not self.bundle.supports(crop_id, organ):
            return dict(
                result,
                outcome="unsupported_input",
                reason_codes=["unsupported_crop_or_organ"],
                next_action="select_supported_crop",
            )
        candidates = self._infer(image_bytes, crop_id, organ)
        result["candidates"] = candidates[:3]
        if sum(x["score"] for x in candidates) < m["policy"]["selected_crop_mass_threshold"]:
            result["reason_codes"] = ["crop_mismatch_or_insufficient_evidence"]
        elif candidates[0]["score"] < m["policy"]["joint_score_threshold"]:
            result["reason_codes"] = ["low_confidence"]
        else:
            result.update(outcome="predicted", prediction=candidates[0], next_action="view_guidance")
        return result


class ResearchOnnxPredictor(OnnxPredictor):
    """Explicit research runtime: scores are exploratory; every result abstains."""

    def __init__(self, bundle: Bundle):
        self.bundle = _pin_bundle(bundle, research=True)
        self._create_session()

    def predict(self, image_bytes: bytes, crop_id: str, organ: str = "leaf") -> dict:
        result = _empty_result()
        result["reason_codes"] = ["research_model_unvalidated"]
        if not self.bundle.supports(crop_id, organ):
            result["reason_codes"].append("unsupported_crop_or_organ")
            result["next_action"] = "select_supported_crop"
            return result
        result["candidates"] = self._infer(image_bytes, crop_id, organ)[:3]
        return result
