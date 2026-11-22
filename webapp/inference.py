"""ONNX inference for the AgroVision KZ web demo (CPU or CUDA, no PyTorch required)."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

RES, SHORT = 224, 256
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageError(ValueError):
    pass


def load_image(data: bytes) -> tuple[np.ndarray, dict]:
    """Return (1,3,224,224) float32 in [0,1] plus quality statistics."""
    try:
        probe = Image.open(io.BytesIO(data))
        width, height = probe.size
        if width * height > MAX_PIXELS:
            raise ImageError("too_large")
        im = ImageOps.exif_transpose(probe).convert("RGB")
    except ImageError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageError("not_an_image") from exc
    width, height = im.size
    if min(width, height) < 64:
        raise ImageError("too_small")
    scale = SHORT / min(width, height)
    resized = im.resize((max(SHORT, round(width * scale)), max(SHORT, round(height * scale))), Image.BILINEAR)
    w, h = resized.size
    left, top = (w - RES) // 2, (h - RES) // 2
    crop = resized.crop((left, top, left + RES, top + RES))
    arr = np.asarray(crop, dtype=np.float32) / 255.0
    gray = arr.mean(axis=2)
    lap = (
        gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * gray[1:-1, 1:-1]
    )
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    vegetation = float(((g > r * 0.95) & (g > b * 1.05)).mean())
    stats = {
        "sharpness": float(lap.var()),
        "brightness": float(gray.mean()),
        "vegetation": vegetation,
        "min_side": int(min(width, height)),
    }
    return arr.transpose(2, 0, 1)[None], stats


def quality_flags(stats: dict) -> list[str]:
    flags = []
    if stats["sharpness"] < 4e-4:
        flags.append("blurry")
    if stats["brightness"] < 0.18:
        flags.append("dark")
    if stats["brightness"] > 0.88:
        flags.append("overexposed")
    if stats["min_side"] < 224:
        flags.append("low_resolution")
    if stats["vegetation"] < 0.08:
        flags.append("no_vegetation")
    return flags


def softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)


class Classifier:
    def __init__(self, directory: Path, providers: list[str] | None = None):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        self.classes: list[str] = self.manifest["classes"]
        self.crops = [c.split("__")[0] for c in self.classes]
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        available = ort.get_available_providers()
        providers = providers or [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in available]
        self.members = []
        for member in self.manifest["models"]:
            session = ort.InferenceSession(str(self.directory / member["file"]), options, providers=providers)
            self.members.append((session, session.get_inputs()[0].name, member.get("temperature", 1.0), member.get("weight", 1.0)))
        self.thresholds = self.manifest["thresholds"]
        self.can_explain = any(len(s.get_outputs()) > 1 for s, *_ in self.members)
        self.warm()

    def warm(self):
        x = np.zeros((1, 3, RES, RES), dtype=np.float32)
        for session, name, _, _ in self.members:
            session.run(None, {name: x})

    def probabilities(self, x: np.ndarray, tta: bool = True) -> np.ndarray:
        batch = np.concatenate([x, x[..., ::-1]], axis=0) if tta else x
        batch = np.ascontiguousarray(batch, dtype=np.float32)
        total, weight = 0.0, 0.0
        for session, name, temperature, w in self.members:
            logits = session.run(None, {name: batch})[0]
            total = total + w * softmax(logits / temperature).mean(axis=0)
            weight += w
        return total / weight

    def predict(self, data: bytes, crop: str | None = None, top_k: int = 3) -> dict:
        started = time.perf_counter()
        x, stats = load_image(data)
        full = self.probabilities(x)
        t = self.thresholds
        other = t.get("other_class", -1)
        p_other = float(full[other]) if other >= 0 else 0.0
        diagnosable = np.array([i != other for i in range(len(self.classes))])
        diag = np.where(diagnosable, full, 0.0)
        global_top = int(diag.argmax())
        mismatch = None
        if crop:
            mask = np.array([c == crop for c in self.crops]) & diagnosable
            if not mask.any():
                raise ImageError("unknown_crop")
            crop_mass = float(full[mask].sum())
            probs = np.where(mask, diag, 0.0)
            probs = probs / max(probs.sum(), 1e-9)
            if self.crops[global_top] != crop and diag[global_top] >= 0.6:
                mismatch = {"crop": self.crops[global_top], "probability": float(diag[global_top])}
            evidence = crop_mass
        else:
            probs = diag
            evidence = 1.0 - p_other
        order = np.argsort(-probs)[:top_k]
        top = [{"label": self.classes[i], "probability": float(probs[i])} for i in order]
        p1 = float(probs[order[0]])
        p2 = float(probs[order[1]]) if len(order) > 1 else 0.0
        if p_other >= t.get("other_threshold", 0.5) or evidence < t["evidence_low"]:
            status = "unrecognized"
        elif p1 >= t["confident"] and (p1 - p2) >= t["margin"] and evidence >= t["evidence"]:
            status = "confident"
        elif p1 >= t["uncertain"]:
            status = "uncertain"
        else:
            status = "unrecognized"
        return {
            "status": status,
            "top": top,
            "crop_hint": crop,
            "crop_mismatch": mismatch,
            "evidence": evidence,
            "other_probability": p_other,
            "quality_flags": quality_flags(stats),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    def explain(self, data: bytes, label: str) -> dict:
        """Class activation map from the first ensemble member that exports one (CNN heads)."""
        x, _ = load_image(data)
        target = self.classes.index(label)
        for session, name, _, _ in self.members:
            if len(session.get_outputs()) > 1:
                cam = session.run(None, {name: np.ascontiguousarray(x, dtype=np.float32)})[1][0, target]
                break
        else:
            raise ImageError("explain_unavailable")
        cam = np.maximum(cam, 0)
        cam = cam / max(float(cam.max()), 1e-6)
        heat = np.asarray(Image.fromarray((cam * 255).astype(np.uint8)).resize((RES, RES), Image.BICUBIC), dtype=np.float32) / 255
        heat = np.clip((heat - 0.25) / 0.75, 0, 1)
        rgb = (x[0].transpose(1, 2, 0) * 255).astype(np.uint8).astype(np.float32)
        color = np.stack([255 * np.clip(heat * 2, 0, 1), 255 * np.clip(2 - heat * 2, 0, 1) * np.clip(heat * 3, 0, 1), 30 * np.ones_like(heat)], axis=2)
        alpha = (np.clip(heat * 1.2, 0, 0.7))[..., None]
        overlay = (rgb * (1 - alpha) + color * alpha).clip(0, 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(overlay).save(buffer, "JPEG", quality=88)
        return {"image": buffer.getvalue()}
