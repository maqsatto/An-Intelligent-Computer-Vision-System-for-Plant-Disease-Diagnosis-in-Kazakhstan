import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "kz"))

import build_dataset as B  # noqa: E402

KNOWLEDGE = json.loads((ROOT / "webapp" / "knowledge.json").read_text(encoding="utf-8"))


def training_labels():
    labels = {(c, k) for c in B.PV_CROPS.values() for k in B.PV_COND.values()}
    for _, mapping, _, _ in B.HF_SOURCES.values():
        labels |= set(mapping.values())
    labels |= {("wheat", k) for k in ("healthy", "septoria", "stripe_rust", "brown_rust", "powdery_mildew")}
    # wild-only conditions (PlantWild) used by the "wild" model
    labels |= {("cucumber", "powdery_mildew"), ("cucumber", "angular_leaf_spot"), ("grape", "downy_mildew"),
               ("maize", "smut"), ("apple", "mosaic_virus"),
               ("wheat", "stem_rust"), ("wheat", "head_scab"), ("wheat", "loose_smut")}
    return {x for x in labels if x[0] != "other"}


def test_every_supported_condition_has_russian_guidance():
    missing = [(c, k) for c, k in training_labels() if k not in KNOWLEDGE["conditions"]]
    assert not missing


def test_every_supported_crop_has_a_name():
    assert {c for c, _ in training_labels()} <= set(KNOWLEDGE["crops"])


def test_guidance_is_complete_and_defers_to_experts():
    for key, info in KNOWLEDGE["conditions"].items():
        assert info["name"] and info["summary"], key
        assert info["actions"], key
        if not info.get("healthy"):
            text = " ".join(info["actions"]).lower()
            assert "агроном" in text or "специалист" in text or "причин" in text, key
