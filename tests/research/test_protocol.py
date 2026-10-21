import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("protocol_checks", ROOT / "ml/research/protocol_checks.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
spec_audit = importlib.util.spec_from_file_location(
    "metadata_audit", ROOT / "ml/research/audit_plantdoc_metadata.py"
)
audit = importlib.util.module_from_spec(spec_audit)
spec_audit.loader.exec_module(audit)


def config():
    return json.loads((ROOT / "ml/scientific_experiment_config.yaml").read_text())


def test_planned_configuration_is_consistent_and_not_admitted():
    assert checks.validate(config())["experiment_admission"] == "no_go_pending_data_audit"


@pytest.mark.parametrize(
    "change",
    [
        "film_head",
        "conditional_global",
        "different_loss",
        "target_tuning",
        "abstention",
        "two_seeds",
        "seed_ci",
        "runtime_adapter",
        "practical_threshold",
    ],
)
def test_scientific_confounders_are_rejected(change):
    value = copy.deepcopy(config())
    if change == "film_head":
        value["architecture"]["film_position"] = "before_linear_head"
    if change == "conditional_global":
        value["arms"]["C1"]["score_space"] = "global_joint"
    if change == "different_loss":
        value["arms"]["C0"]["loss"] = "global_cross_entropy"
    if change == "target_tuning":
        value["training"]["target_source_used_for_tuning_or_adaptation"] = True
    if change == "abstention":
        value["evaluation"]["primary_abstention"] = True
    if change == "two_seeds":
        value["training"]["paired_seeds"] = [17, 41]
    if change == "seed_ci":
        value["evaluation"]["bootstrap"]["resample_training_seeds"] = True
    if change == "runtime_adapter":
        value["application_boundary"]["change_existing_runtime"] = True
    if change == "practical_threshold":
        value["evaluation"]["practical_effect_threshold_absolute"] = 0.01
    with pytest.raises(ValueError):
        checks.validate(value)


def test_conditional_loss_ignores_other_crop_logits_but_global_does_not():
    original = [2.0, 1.0, 0.0, 0.0]
    wrong_crop_large = [2.0, 1.0, 100.0, 100.0]
    assert checks.cross_entropy(original, 0, [0, 1]) == checks.cross_entropy(wrong_crop_large, 0, [0, 1])
    assert checks.cross_entropy(wrong_crop_large, 0) > checks.cross_entropy(original, 0)
    with pytest.raises(ValueError):
        checks.cross_entropy(original, 2, [0, 1])


def test_equal_crop_weight_differs_from_flat_class_mean_when_class_counts_differ():
    mapping = {"a": "potato", "b": "tomato", "c": "tomato"}
    # Potato F1=1, tomato classes mutually confused: crop-balanced=.5, flatmacro=1/3.
    assert checks.crop_balanced_macro_f1(["a", "b", "c"], ["a", "c", "b"], mapping) == 0.5
    with pytest.raises(ValueError):
        checks.crop_balanced_macro_f1(["a"], ["a"], mapping)


@pytest.mark.parametrize(
    "coordinates,expected",
    [((0, 0, 10, 10), True), ((-1, 0, 10, 10), False), ((0, 0, 11, 10), False), ((2, 2, 2, 8), False)],
)
def test_metadata_geometry_does_not_clip_invalid_boxes_into_the_test(coordinates, expected):
    row = dict(
        zip(("xmin", "ymin", "xmax", "ymax"), map(str, coordinates), strict=True), width="10", height="10"
    )
    assert audit.valid_box(row) is expected


def test_metadata_tree_must_be_bound_to_same_commit():
    commit = dict(sha="commitA", commit={"tree": {"sha": "treeA"}})
    audit.validate_tree_binding(commit, {"sha": "treeA", "truncated": False})
    audit.validate_tree_binding(commit, {"sha": "commitA", "truncated": False})
    with pytest.raises(ValueError, match="pinned commit"):
        audit.validate_tree_binding(commit, {"sha": "treeB", "truncated": False})
    with pytest.raises(ValueError, match="Truncated"):
        audit.validate_tree_binding(commit, {"sha": "treeA", "truncated": True})
