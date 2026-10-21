import hashlib
from pathlib import Path
from threading import Lock

from agrovision.errors import APIError

CROPS = {"wheat": "Пшеница", "potato": "Картофель", "tomato": "Томат", "maize": "Кукуруза"}
PILOT_CROPS = {"wheat", "potato", "tomato"}
DEV_MODEL = {
    "version": "dev-synthetic-v1",
    "artifact_sha256": hashlib.sha256(b"agrovision-explicit-development-predictor-v1").hexdigest(),
    "preprocessing_version": "normalized-jpeg-rgb-v1",
    "decision_policy_version": "dev-always-inconclusive-v1",
}


_validation_lock = Lock()


def active_bundle(settings):
    # Manifest/ORT validation is serialized to bound transient native session memory.
    with _validation_lock:
        return _load_active_bundle(settings)


def _load_active_bundle(settings):
    # Validation is fail-closed. No filename/manifest may silently activate a research artifact.
    from agrovision_runtime import BundleValidationError, validate_bundle, validate_research_bundle

    try:
        research_dir = getattr(settings, "research_bundle_dir", None)
        if research_dir and settings.environment != "production":
            return validate_research_bundle(Path(research_dir)), "research"
        if (settings.bundle_dir / "manifest.json").is_file():
            return validate_bundle(settings.bundle_dir), "validated"
    except BundleValidationError:
        return None, None
    return None, None


def select_model(settings, crop_id, organ):
    if crop_id not in PILOT_CROPS:
        raise APIError(422, "unsupported_crop", "Для этой культуры анализ пока не поддерживается.")
    if organ != "leaf":
        raise APIError(422, "invalid_organ", "Поддерживается только фотография листа.")
    bundle, mode = active_bundle(settings)
    if bundle is not None and bundle.supports(crop_id, organ):
        return bundle.snapshot(), str(bundle.directory), mode, bundle.manifest
    if settings.dev_predictor and settings.environment != "production":
        return dict(DEV_MODEL), None, "synthetic", None
    raise APIError(503, "model_unavailable", "Проверенная модель недоступна. Наблюдение сохранено.")


def get_catalog(settings):
    bundle, mode = active_bundle(settings)
    synthetic = settings.dev_predictor and settings.environment != "production"
    entries = []
    for crop, name in CROPS.items():
        supported = bool(crop in PILOT_CROPS and bundle and bundle.supports(crop, "leaf"))
        dev = synthetic and crop in PILOT_CROPS
        can_assess = supported or dev
        entries.append(
            {
                "id": crop,
                "name_ru": name,
                "support_status": ("validated" if mode == "validated" else "development")
                if supported
                else ("development" if dev else "unavailable"),
                "can_assess": can_assess,
                "supported_organs": ["leaf"] if can_assess else [],
                "model_version": bundle.manifest["version"]
                if supported
                else DEV_MODEL["version"]
                if dev
                else None,
                "availability_reason": None
                if can_assess
                else "model_unavailable"
                if crop in PILOT_CROPS
                else "unsupported_crop",
                "classes": [
                    {"class_id": x["class_id"], "condition_id": x["condition_id"]}
                    for x in bundle.manifest["labels"]
                    if x["crop_id"] == crop
                ]
                if supported
                else [],
            }
        )
    return {
        "catalog_version": "catalog-v1",
        "runtime_mode": "development" if synthetic or mode == "research" else "production",
        "crops": entries,
    }
