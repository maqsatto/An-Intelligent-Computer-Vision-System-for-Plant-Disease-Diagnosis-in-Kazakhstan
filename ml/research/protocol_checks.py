"""Stdlib-only consistency checks and reference formulas for a PLANNED protocol.

This is not a model trainer or evidence of completed scientific runs. Config is
JSON syntax within YAML1.2, deliberately readable without a new dependency.
"""

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = {"potato.early_blight", "potato.late_blight", "tomato.early_blight", "tomato.late_blight"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(config):
    require(config["status"] == "planned_not_measured", "Unmeasured protocol must stay planned")
    require(not config["training_runner_implemented"], "No new trainer has been implemented")
    require(
        config["experiment_admission"] == "no_go_pending_data_audit",
        "Pending gates cannot be treated as admitted",
    )
    require(
        set(config["core_classes"]) == CORE and len(config["core_classes"]) == 4, "Four-class core mismatch"
    )
    require(not config["extension_classes"], "Extensions require a separate revision")
    architecture = config["architecture"]
    arms = config["arms"]
    evaluation = config["evaluation"]
    data = config["data"]
    training = config["training"]
    require(architecture["backbone"] == "torchvision.resnet18", "Controlled backbone must be ResNet18")
    require(
        architecture["film_position"] == "after_layer3_before_layer4"
        and architecture["nonlinear_block_after_film"] == "layer4",
        "FiLM must precede nonlinear layer4, not the head",
    )
    require(
        architecture["head_outputs"] == 4 and architecture["feature_shape"] == [256, 14, 14],
        "Core tensor/label shapes mismatch",
    )
    require(
        architecture["shared_initial_state_per_seed"] and architecture["same_parameter_shapes_all_arms"],
        "Arms must share initialization and shapes",
    )
    require(architecture["film_final_linear_zero_initialized"], "Paired identity initialization required")
    require(set(arms) == {"G0", "C0", "C1"}, "Exactly three controlled arms required")
    require(
        arms["G0"]["film_input"] == arms["C0"]["film_input"] == "constant",
        "G0/C0 must receive the constant token",
    )
    require(arms["C1"]["film_input"] == "true_crop", "C1 must receive the known crop token")
    require(arms["G0"]["loss"] == "global_cross_entropy", "G0 global loss required")
    require(
        arms["C0"]["loss"] == arms["C1"]["loss"] == "within_crop_cross_entropy",
        "C0 and C1 must have the same conditional loss",
    )
    require(
        arms["C0"]["score_space"] == arms["C1"]["score_space"] == "crop_conditional",
        "Conditional scores must not be global_joint",
    )
    require(
        config["known_crop_supplied_to_all_arms"]
        and all(a["primary_decoder"] == "known_crop_masked_argmax" for a in arms.values()),
        "Known-crop decoding must be identical",
    )
    seeds = training["paired_seeds"]
    require(
        len(seeds) >= 3 and len(set(seeds)) == len(seeds), "At least three distinct paired seeds required"
    )
    require(
        not training["target_source_used_for_tuning_or_adaptation"],
        "Held-out target cannot be used for adaptation/tuning",
    )
    require(
        not training["early_stopping"] and sum(s["epochs"] for s in training["stages"]) == 20,
        "Common full20epoch budget required",
    )
    require(
        training["physical_batch"] * training["gradient_accumulation"] == training["effective_batch"],
        "Effective batch mismatch",
    )
    require(
        data["development_source"] != data["fully_held_out_source"], "Development and test source must differ"
    )
    require(
        data["historical_pilot_images_are_not_fresh_internal_test"]
        and data["local_pilot_and_final_disjoint"],
        "Fresh final test isolation required",
    )
    require(
        math.isclose(sum(data["development_group_fractions"].values()), 1), "Split fractions must sum to1"
    )
    require(
        len(data["core_gate_requirements"]) >= 7 and not data["gate_results"],
        "Pending actual data gates must remain uncompleted",
    )
    require(
        evaluation["primary_contrast"] == "C1-C0"
        and evaluation["primary_metric"] == "crop_balanced_macro_f1",
        "Primary estimand mismatch",
    )
    require(not evaluation["primary_abstention"], "Primary endpoint cannot selectively abstain")
    require(
        evaluation["practical_effect_threshold_absolute"] == 0.02
        and evaluation["threshold_fixed_before_final_test"],
        "Pre-test practical reference must stay2pp",
    )
    bootstrap = evaluation["bootstrap"]
    require(
        bootstrap["paired"] and bootstrap["reuse_same_group_draw_all_arms_and_seeds"],
        "Interval must pair group draws",
    )
    require(
        bootstrap["unit"] == "whole_parent_leaf_dedup_group" and bootstrap["confidence"] == 0.95,
        "95% grouped interval required",
    )
    require(
        not bootstrap["resample_training_seeds"] and evaluation["seed_spread_separate_from_group_ci"],
        "Seed spread must remain distinct from group CI",
    )
    require(
        not config["application_boundary"]["change_existing_runtime"]
        and config["application_boundary"]["existing_score_space"] == "global_joint",
        "Historical runtime cannot silently change semantics",
    )
    return config


def cross_entropy(logits, target, allowed_indices=None):
    allowed = list(range(len(logits))) if allowed_indices is None else list(allowed_indices)
    require(
        target in allowed and len(allowed) == len(set(allowed)),
        "Target must belong to a unique allowed class set",
    )
    require(
        all(0 <= i < len(logits) and math.isfinite(logits[i]) for i in allowed),
        "Invalid logits/class indices",
    )
    maximum = max(logits[i] for i in allowed)
    return -logits[target] + maximum + math.log(sum(math.exp(logits[i] - maximum) for i in allowed))


def crop_balanced_macro_f1(truth, prediction, class_to_crop):
    require(len(truth) == len(prediction) and bool(truth), "Paired nonempty observations required")
    require(all(label in class_to_crop for label in list(truth) + list(prediction)), "Unknown class")
    by_crop = {crop: [] for crop in set(class_to_crop.values())}
    for label, crop in class_to_crop.items():
        require(label in truth, "Every core class must have reference support")
        tp = sum(t == label and p == label for t, p in zip(truth, prediction, strict=True))
        fp = sum(t != label and p == label for t, p in zip(truth, prediction, strict=True))
        fn = sum(t == label and p != label for t, p in zip(truth, prediction, strict=True))
        by_crop[crop].append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return sum(sum(values) / len(values) for values in by_crop.values()) / len(by_crop)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="ml/scientific_experiment_config.yaml")
    args = parser.parse_args()
    config = validate(json.loads((ROOT / args.config).read_text()))
    print(f"PASS {config['protocol_version']}: planned only; data admission remains NO-GO")
