import hashlib
import json

import onnx
import pytest
from agrovision_runtime import BundleValidationError, OnnxPredictor, validate_bundle
from onnx import TensorProto, helper


def fixture_bundle(tmp_path):
    labels = [
        dict(class_id="wheat_rust", crop_id="wheat", condition_id="stripe_rust", organ="leaf"),
        dict(class_id="tomato_healthy", crop_id="tomato", condition_id="healthy_appearance", organ="leaf"),
    ]
    digest = hashlib.sha256(json.dumps(labels, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    graph = helper.make_graph(
        [
            helper.make_node(
                "Constant",
                [],
                ["scores"],
                value=helper.make_tensor("v", TensorProto.FLOAT, [1, 2], [2.0, 1.0]),
            )
        ],
        "test",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 224, 224])],
        [helper.make_tensor_value_info("scores", TensorProto.FLOAT, [1, 2])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=10)
    helper.set_model_props(model, {"labels_sha256": digest, "preprocessing_version": "rgb224-v1"})
    onnx.save(model, tmp_path / "model.onnx")
    m = dict(
        version="test-v1",
        artifact={
            "file": "model.onnx",
            "sha256": hashlib.sha256((tmp_path / "model.onnx").read_bytes()).hexdigest(),
        },
        labels=labels,
        labels_sha256=digest,
        input={"name": "images", "shape": [1, 3, 224, 224], "dtype": "float32"},
        output={"name": "scores", "shape": [1, 2], "semantics": "logits"},
        preprocessing={
            "version": "rgb224-v1",
            "resize_shorter_side": 256,
            "center_crop": 224,
            "interpolation": "bilinear",
            "color_mode": "RGB",
            "apply_exif_orientation": True,
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
        score_space="global_joint",
        policy={
            "version": "p1",
            "status": "validated",
            "joint_score_threshold": 0.8,
            "selected_crop_mass_threshold": 0.8,
        },
        calibration={"kind": "none"},
        provenance={
            "dataset_manifest_sha256": "a" * 64,
            "split_manifest_sha256": "b" * 64,
            "code_commit": "a" * 40,
            "evaluation_report": "evaluation.json",
        },
        release_status="validated",
    )
    m["preprocessing_sha256"] = hashlib.sha256(
        json.dumps(m["preprocessing"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    helper.set_model_props(
        model,
        {
            "labels_sha256": digest,
            "preprocessing_version": "rgb224-v1",
            "preprocessing_sha256": m["preprocessing_sha256"],
        },
    )
    onnx.save(model, tmp_path / "model.onnx")
    m["artifact"]["sha256"] = hashlib.sha256((tmp_path / "model.onnx").read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    return m


def test_bundle_snapshot_and_capabilities(tmp_path):
    fixture_bundle(tmp_path)
    b = validate_bundle(tmp_path)
    assert b.supports("wheat") and not b.supports("wheat", "fruit")
    assert set(b.snapshot()) == {
        "version",
        "artifact_sha256",
        "preprocessing_version",
        "decision_policy_version",
    }


@pytest.mark.parametrize(
    "mutation", ["hash", "labels", "preprocessing", "preprocessing_config", "null_policy", "research"]
)
def test_corrupt_or_unvalidated_bundle_rejected(tmp_path, mutation):
    m = fixture_bundle(tmp_path)
    if mutation == "hash":
        m["artifact"]["sha256"] = "0" * 64
    if mutation == "labels":
        m["labels"].reverse()
    if mutation == "preprocessing":
        m["preprocessing"]["version"] = "wrong"
    if mutation == "preprocessing_config":
        m["preprocessing"]["mean"][0] = 0.1
    if mutation == "null_policy":
        m["policy"]["joint_score_threshold"] = None
    if mutation == "research":
        m["release_status"] = "research"
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(BundleValidationError):
        validate_bundle(tmp_path)


def test_global_scores_not_crop_renormalized(tmp_path):
    import io

    from PIL import Image

    fixture_bundle(tmp_path)
    stream = io.BytesIO()
    Image.new("RGB", (300, 300), "green").save(stream, format="JPEG")
    result = OnnxPredictor(validate_bundle(tmp_path)).predict(stream.getvalue(), "wheat")
    assert result["outcome"] == "inconclusive"
    assert result["prediction"] is None
    assert result["candidates"][0]["score"] == pytest.approx(0.7310586)
    assert result["quality"]["status"] == "not_assessed"


def test_artifact_path_cannot_escape_bundle(tmp_path):
    m = fixture_bundle(tmp_path)
    outside = tmp_path.parent / "external-model.onnx"
    outside.write_bytes((tmp_path / "model.onnx").read_bytes())
    m["artifact"]["file"] = "../external-model.onnx"
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(BundleValidationError, match="escapes"):
        validate_bundle(tmp_path)


def test_unsupported_organ_never_runs_model(tmp_path):
    fixture_bundle(tmp_path)
    predictor = OnnxPredictor(validate_bundle(tmp_path))
    result = predictor.predict(b"not an image", "wheat", "fruit")
    assert result["outcome"] == "unsupported_input"
    assert result["prediction"] is None


def test_preprocessing_produces_fixed_rgb_chw_and_respects_mean_std():
    import io

    import numpy as np
    from agrovision_runtime import preprocess
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (400, 200), (255, 0, 0)).save(stream, format="PNG")
    config = dict(resize_shorter_side=256, center_crop=224, mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
    values = preprocess(stream.getvalue(), config)
    assert values.shape == (1, 3, 224, 224)
    assert values.dtype == np.float32
    np.testing.assert_array_equal(values[0, 0], 1.0)
    np.testing.assert_array_equal(values[0, 1:], -1.0)


def test_research_bundle_does_not_relax_production(tmp_path):
    from agrovision_runtime import validate_research_bundle

    m = fixture_bundle(tmp_path)
    m["release_status"] = "research"
    m["policy"].update(status="unvalidated", joint_score_threshold=None, selected_crop_mass_threshold=None)
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    research = validate_research_bundle(tmp_path)
    assert research.supports("wheat")
    with pytest.raises(BundleValidationError):
        validate_bundle(tmp_path)
    with pytest.raises(BundleValidationError):
        OnnxPredictor(research)


def test_research_never_predicts_even_high_healthy_score(tmp_path):
    import io

    from agrovision_runtime import ResearchOnnxPredictor, validate_research_bundle
    from PIL import Image

    m = fixture_bundle(tmp_path)
    model = onnx.load(tmp_path / "model.onnx")
    model.graph.node[0].attribute[0].t.float_data[:] = [-20.0, 20.0]
    onnx.save(model, tmp_path / "model.onnx")
    m["artifact"]["sha256"] = hashlib.sha256((tmp_path / "model.onnx").read_bytes()).hexdigest()
    m["release_status"] = "research"
    m["policy"].update(status="unvalidated", joint_score_threshold=None, selected_crop_mass_threshold=None)
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    stream = io.BytesIO()
    Image.new("RGB", (224, 224), "green").save(stream, format="PNG")
    result = ResearchOnnxPredictor(validate_research_bundle(tmp_path)).predict(stream.getvalue(), "tomato")
    assert result["candidates"][0]["score"] > 0.999
    assert result["outcome"] == "inconclusive"
    assert result["prediction"] is None
    assert result["reason_codes"] == ["research_model_unvalidated"]


@pytest.mark.parametrize("value", [None, 0.0, -1.0, 1.1, True, "0.9", float("nan"), float("inf")])
def test_production_never_guesses_invalid_threshold(tmp_path, value):
    m = fixture_bundle(tmp_path)
    m["policy"]["selected_crop_mass_threshold"] = value
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(BundleValidationError, match="threshold"):
        validate_bundle(tmp_path)


def test_full_preprocessing_onnx_binding_catches_reused_version(tmp_path):
    m = fixture_bundle(tmp_path)
    m["preprocessing"]["mean"][0] = 0.1
    m["preprocessing_sha256"] = hashlib.sha256(
        json.dumps(m["preprocessing"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(BundleValidationError, match="ONNX preprocessing digest"):
        validate_bundle(tmp_path)


def test_runtime_caps_onnx_cpu_threads(tmp_path):
    fixture_bundle(tmp_path)
    predictor = OnnxPredictor(validate_bundle(tmp_path))
    options = predictor.session.get_session_options()
    assert options.intra_op_num_threads == 4
    assert options.inter_op_num_threads == 1
    assert predictor.session.get_providers() == ["CPUExecutionProvider"]


def test_session_uses_exact_checked_bytes_despite_artifact_path_change(tmp_path, monkeypatch):
    import agrovision_runtime as runtime
    import numpy as np

    m = fixture_bundle(tmp_path)
    alternate = onnx.load(tmp_path / "model.onnx")
    alternate.graph.node[0].attribute[0].t.float_data[:] = [-50.0, 50.0]
    alternate_bytes = alternate.SerializeToString()
    original_session = runtime._session
    seen = []

    def swap_path_after_checksum(artifact):
        seen.append(artifact)
        (tmp_path / "model.onnx").write_bytes(alternate_bytes)
        return original_session(artifact)

    monkeypatch.setattr(runtime, "_session", swap_path_after_checksum)
    predictor = runtime.OnnxPredictor(runtime.Bundle(tmp_path, m))
    assert all(isinstance(artifact, bytes) for artifact in seen)
    scores = predictor.session.run(["scores"], {"images": np.zeros((1, 3, 224, 224), dtype=np.float32)})[0]
    np.testing.assert_array_equal(scores, [[2.0, 1.0]])


def test_validated_bundle_is_pinned_when_directory_changes(tmp_path):
    import numpy as np

    m = fixture_bundle(tmp_path)
    bundle = validate_bundle(tmp_path)
    (tmp_path / "model.onnx").write_bytes(b"replaced after admission")
    (tmp_path / "manifest.json").write_text("{}")
    predictor = OnnxPredictor(bundle)
    assert predictor.bundle.snapshot()["version"] == m["version"]
    scores = predictor.session.run(["scores"], {"images": np.zeros((1, 3, 224, 224), dtype=np.float32)})[0]
    np.testing.assert_array_equal(scores, [[2.0, 1.0]])


def test_mutation_of_validated_bundle_manifest_is_rejected(tmp_path):
    fixture_bundle(tmp_path)
    bundle = validate_bundle(tmp_path)
    bundle.manifest["policy"]["joint_score_threshold"] = 0.01
    with pytest.raises(BundleValidationError, match="manifest changed"):
        OnnxPredictor(bundle)
