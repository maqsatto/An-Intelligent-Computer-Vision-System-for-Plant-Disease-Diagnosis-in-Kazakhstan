"""Tiny deterministic evaluation checks; no local data/models, DB or GPU needed."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

spec = importlib.util.spec_from_file_location(
    "model_cases", Path(__file__).parents[2] / "ml/evaluation/evaluate_cases.py"
)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def row(digest, split="test", label="potato__early_blight"):
    return dict(sha256=digest, split=split, class_id=label, crop_id=label.split("__")[0])


def test_paired_selection_requires_same_test_bytes_in_both_models():
    a = [row("a"), row("b"), row("c", "train")]
    b = [row("a"), row("b", "validation"), row("d")]
    assert evaluation.test_intersection(a, b) == ["a"]
    assert evaluation.test_intersection([row("a")], [row("different")]) == []


def test_pair_rejects_reference_conflict_or_non_test_duplicate():
    with pytest.raises(ValueError, match="Conflicting"):
        evaluation.test_intersection([row("a")], [row("a", label="potato__late_blight")])
    with pytest.raises(ValueError, match="non-test"):
        evaluation.test_intersection([row("a"), row("a", "train")], [row("a")])


def test_common_macro_keeps_extra_class_prediction_as_error():
    records = [
        dict(expected_class_id="a", predicted_class_id="a", split_group_id="1"),
        dict(expected_class_id="b", predicted_class_id="extra", split_group_id="2"),
    ]
    report = evaluation.metrics(records, ["a", "b", "extra"], ["a", "b"])
    assert report["accuracy"] == 0.5
    assert report["macro_f1"] == 0.5
    assert report["macro_f1_class_ids"] == ["a", "b"]
    assert report["confusion_matrix"][1][2] == 1


def test_case_selection_is_predeclared_hash_order_not_correctness():
    class Model:
        labels = [{"class_id": "a"}, {"class_id": "b"}]
        records = [
            dict(expected_class_id="a", sha256="z", correct=True),
            dict(expected_class_id="a", sha256="a", correct=False),
            dict(expected_class_id="b", sha256="b", correct=True),
        ]

    chosen = evaluation.case_selection(Model())
    assert [r["sha256"] for r in chosen] == ["a", "b"]
    assert all(r["selection"] == "predeclared_min_sha_per_class" for r in chosen)


@pytest.mark.parametrize("name", evaluation.TRANSFORMS)
def test_transform_is_deterministic(name):
    image = Image.fromarray(np.random.default_rng(17).integers(0, 256, (32, 48, 3), dtype=np.uint8))
    data = evaluation.jpeg(image)
    assert evaluation.transform(data, name) == evaluation.transform(data, name)
    if name == "clean":
        assert evaluation.transform(data, name) == data


def test_synthetic_noise_is_fixed_seed_and_not_reference_labelled():
    a = evaluation.control_images()
    b = evaluation.control_images()
    assert set(a) == {"uniform_gray", "uniform_green", "checkerboard", "seed17_noise"}
    np.testing.assert_array_equal(np.asarray(a["seed17_noise"]), np.asarray(b["seed17_noise"]))
