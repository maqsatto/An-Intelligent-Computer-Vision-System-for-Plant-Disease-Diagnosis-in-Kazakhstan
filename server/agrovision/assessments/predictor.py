"""Predictor boundary and a persistent, supervised subprocess (hard bounded execution)."""

import hashlib
import json
import multiprocessing as mp
from pathlib import Path
from typing import Protocol

from agrovision.photos.storage import LocalImageStore


class Predictor(Protocol):
    def predict(self, image_bytes: bytes, crop_id: str, organ: str = "leaf") -> dict: ...


class PredictorFailure(Exception):
    def __init__(self, code, retryable):
        self.code, self.retryable = code, retryable


def _serve(connection, settings):
    cache = {}
    while True:
        try:
            claim = connection.recv()
        except EOFError:
            break
        if claim is None:
            break
        try:
            content = LocalImageStore(settings.storage_dir).read(claim.object_key)
            if hashlib.sha256(content).hexdigest() != claim.photo_sha256:
                connection.send(("error", "invalid_input", False))
                continue
            if claim.model_mode == "synthetic":
                if settings.environment == "production" or not settings.dev_predictor:
                    raise ValueError("Synthetic predictor is disabled")
                result = {
                    "outcome": "inconclusive",
                    "reason_codes": ["insufficient_evidence", "development_demo"],
                    "prediction": None,
                    "candidates": [],
                    "quality": {"status": "not_assessed", "flags": []},
                    "next_action": "consult_expert",
                }
            else:
                from agrovision_runtime import (
                    OnnxPredictor,
                    ResearchOnnxPredictor,
                    validate_bundle,
                    validate_research_bundle,
                )

                if claim.model_mode == "research" and settings.environment == "production":
                    raise ValueError("Research predictor is disabled")
                validate = validate_research_bundle if claim.model_mode == "research" else validate_bundle
                manifest_digest = hashlib.sha256(
                    json.dumps(claim.bundle_manifest, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                cache_key = (claim.model["artifact_sha256"], claim.model_mode, manifest_digest)
                # The cached model is pinned; changed manifests/policy at the same path cannot alter it.
                if cache_key not in cache:
                    bundle = validate(Path(claim.bundle_path))
                    if bundle.snapshot() != claim.model or bundle.manifest != claim.bundle_manifest:
                        connection.send(("error", "bundle_mismatch", False))
                        continue
                    predictor_type = (
                        ResearchOnnxPredictor if claim.model_mode == "research" else OnnxPredictor
                    )
                    cache[cache_key] = predictor_type(bundle)
                predictor = cache[cache_key]
                if predictor.bundle.manifest != claim.bundle_manifest:
                    connection.send(("error", "bundle_mismatch", False))
                    continue
                result = predictor.predict(content, claim.crop_id, claim.organ)
            connection.send(("ok", result))
        except FileNotFoundError:
            connection.send(("error", "storage_unavailable", True))
        except ValueError as exc:
            from agrovision_runtime import InputImageError

            code = "invalid_input" if isinstance(exc, InputImageError) else "bundle_mismatch"
            connection.send(("error", code, False))
        except Exception:
            connection.send(("error", "model_execution_failed", True))
    connection.close()


class SupervisedPredictor:
    def __init__(self, settings):
        self.settings, self.process, self.connection = settings, None, None

    def _start(self):
        context = mp.get_context("spawn")
        parent, child = context.Pipe()
        self.connection = parent
        self.process = context.Process(target=_serve, args=(child, self.settings), daemon=True)
        self.process.start()
        child.close()

    def run(self, claim):
        if self.process is None or not self.process.is_alive():
            self.close()
            self._start()
        try:
            self.connection.send(claim)
            if not self.connection.poll(self.settings.inference_timeout_seconds):
                self.close()
                raise PredictorFailure("assessment_timeout", True)
            response = self.connection.recv()
        except (EOFError, BrokenPipeError, OSError):
            self.close()
            raise PredictorFailure("model_execution_failed", True) from None
        if response[0] == "error":
            raise PredictorFailure(response[1], response[2])
        return response[1]

    def close(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
            self.process = None
        if self.connection:
            self.connection.close()
            self.connection = None
