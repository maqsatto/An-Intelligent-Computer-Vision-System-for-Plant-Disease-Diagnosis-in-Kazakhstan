"""AgroVision KZ web demo: FastAPI + static single-page UI. Stateless (no database).

Run:  uv run uvicorn webapp.app:app --host 0.0.0.0 --port 8080
Model bundle directory: AGRO_WEB_MODEL (default webapp/models/active).
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .inference import Classifier, ImageError

HERE = Path(__file__).parent
MODEL_DIR = Path(os.environ.get("AGRO_WEB_MODEL", HERE / "models" / "active"))
MAX_BYTES = 15 * 1024 * 1024
KNOWLEDGE = json.loads((HERE / "knowledge.json").read_text(encoding="utf-8"))

ERRORS = {
    "not_an_image": "Файл не похож на изображение. Загрузите фото в формате JPG, PNG или WebP.",
    "too_large": "Изображение слишком большое. Уменьшите его и попробуйте снова.",
    "too_small": "Изображение слишком маленькое. Нужна фотография от 224 пикселей по короткой стороне.",
    "unknown_crop": "Эта культура пока не поддерживается.",
    "explain_unavailable": "Карта внимания недоступна для этой модели.",
}

classifier: Classifier | None = None


@asynccontextmanager
async def lifespan(_app):
    if (MODEL_DIR / "manifest.json").is_file():
        get_classifier()
    yield


app = FastAPI(
    title="AgroVision KZ", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan
)


def get_classifier() -> Classifier:
    global classifier
    if classifier is None:
        if not (MODEL_DIR / "manifest.json").is_file():
            raise HTTPException(503, "Модель не установлена.")
        classifier = Classifier(MODEL_DIR)
    return classifier


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-cache" if not request.url.path.startswith("/api") else "no-store"
    return response


def describe(label: str) -> dict:
    crop, condition = label.split("__")
    info = KNOWLEDGE["conditions"].get(condition, {"name": condition.replace("_", " ")})
    return {
        "label": label,
        "crop": crop,
        "crop_name": KNOWLEDGE["crops"].get(crop, crop),
        "condition": condition,
        "condition_name": info["name"],
        "healthy": bool(info.get("healthy")),
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": classifier is not None}


@app.get("/api/model")
def model_info():
    c = get_classifier()
    m = c.manifest
    return {
        "name": m["name"],
        "version": m["version"],
        "architecture": m["architecture"],
        "trained_on": m.get("trained_on"),
        "metrics": m.get("metrics"),
        "benchmark": m.get("benchmark"),
        "thresholds": m["thresholds"],
        "limitations": m.get("limitations", []),
        "can_explain": c.can_explain,
        "crops": [
            {
                "id": crop,
                "name": name,
                "conditions": [describe(x) for x in c.classes if x.startswith(crop + "__")],
            }
            for crop, name in KNOWLEDGE["crops"].items()
            if any(x.startswith(crop + "__") for x in c.classes)
        ],
    }


@app.post("/api/diagnose")
async def diagnose(file: UploadFile = File(...), crop: str | None = Form(None)):
    c = get_classifier()
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return JSONResponse({"error": "too_large", "message": ERRORS["too_large"]}, status_code=413)
    crop = crop if crop and crop != "auto" else None
    try:
        result = await run_in_threadpool(c.predict, data, crop)
    except ImageError as exc:
        code = str(exc)
        return JSONResponse({"error": code, "message": ERRORS.get(code, ERRORS["not_an_image"])}, status_code=422)
    top = [{**describe(x["label"]), "probability": x["probability"]} for x in result["top"]]
    best = top[0]
    info = KNOWLEDGE["conditions"].get(best["condition"], {})
    mismatch = result["crop_mismatch"]
    if mismatch:
        mismatch["crop_name"] = KNOWLEDGE["crops"].get(mismatch["crop"], mismatch["crop"])
    return {
        **result,
        "top": top,
        "advice": {
            "summary": info.get("summary"),
            "symptoms": info.get("symptoms"),
            "actions": info.get("actions", []),
        },
        "crop_mismatch": mismatch,
        "model": {"name": c.manifest["name"], "version": c.manifest["version"]},
    }


@app.post("/api/explain")
async def explain(file: UploadFile = File(...), label: str = Form(...)):
    import base64

    c = get_classifier()
    if label not in c.classes:
        return JSONResponse({"error": "unknown_label", "message": "Неизвестный класс."}, status_code=422)
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return JSONResponse({"error": "too_large", "message": ERRORS["too_large"]}, status_code=413)
    try:
        result = await run_in_threadpool(c.explain, data, label)
    except ImageError as exc:
        return JSONResponse({"error": str(exc), "message": ERRORS.get(str(exc), ERRORS["not_an_image"])}, status_code=422)
    return {"image": "data:image/jpeg;base64," + base64.b64encode(result["image"]).decode()}


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
