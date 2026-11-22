import io
import json

import numpy as np
import onnx
import pytest
from fastapi.testclient import TestClient
from onnx import TensorProto, helper
from PIL import Image

CLASSES = ["wheat__healthy", "wheat__stripe_rust", "potato__late_blight", "other__non_target"]


def tiny_model(path):
    """Mean-RGB -> linear logits: green-ish images look healthy wheat, red-ish stripe rust."""
    weights = np.array(
        [[8, 0, -4, 0], [0, 8, -2, 0], [0, 0, 8, 0]], dtype=np.float32
    ).T  # (4,3)
    x = helper.make_tensor_value_info("image", TensorProto.FLOAT, ["batch", 3, 224, 224])
    y = helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", 4])
    nodes = [
        helper.make_node("GlobalAveragePool", ["image"], ["pooled"]),
        helper.make_node("Flatten", ["pooled"], ["flat"], axis=1),
        helper.make_node("Gemm", ["flat", "w", "b"], ["logits"], transB=1),
    ]
    graph = helper.make_graph(
        nodes, "tiny", [x], [y],
        [
            helper.make_tensor("w", TensorProto.FLOAT, [4, 3], weights.flatten().tolist()),
            helper.make_tensor("b", TensorProto.FLOAT, [4], [0, 0, 0, 2.0]),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    tiny_model(tmp_path / "m.onnx")
    manifest = {
        "name": "tiny", "version": "t", "architecture": "tiny", "classes": CLASSES,
        "models": [{"file": "m.onnx", "temperature": 1.0, "weight": 1.0}],
        "thresholds": {"confident": 0.6, "uncertain": 0.35, "margin": 0.1, "evidence": 0.0,
                       "evidence_low": 0.0, "other_class": 3},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setenv("AGRO_WEB_MODEL", str(tmp_path))
    import importlib

    from webapp import app as module

    importlib.reload(module)
    with TestClient(module.app) as c:
        yield c


def png(color, size=(300, 260)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def test_health_and_model(client):
    assert client.get("/api/health").json()["model_loaded"] is True
    info = client.get("/api/model").json()
    assert info["crops"][0]["id"] == "wheat"
    assert all(c["id"] != "other" for c in info["crops"])


def test_diagnose_returns_ranked_candidates(client):
    r = client.post("/api/diagnose", files={"file": ("a.png", png((0, 255, 0)), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["top"][0]["label"] in CLASSES
    assert len(body["top"]) == 3
    assert body["top"][0]["probability"] >= body["top"][1]["probability"]
    assert body["advice"] is not None


def test_crop_hint_restricts_to_crop(client):
    r = client.post(
        "/api/diagnose",
        data={"crop": "potato"},
        files={"file": ("a.png", png((255, 0, 0)), "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["top"][0]["crop"] == "potato"


def test_rejects_non_image_and_tiny_image(client):
    bad = client.post("/api/diagnose", files={"file": ("a.txt", b"hello", "text/plain")})
    assert bad.status_code == 422 and bad.json()["error"] == "not_an_image"
    small = client.post("/api/diagnose", files={"file": ("a.png", png((0, 255, 0), (30, 30)), "image/png")})
    assert small.status_code == 422 and small.json()["error"] == "too_small"


def test_flat_image_gets_quality_flags(client):
    r = client.post("/api/diagnose", files={"file": ("a.png", png((5, 5, 5)), "image/png")})
    flags = r.json()["quality_flags"]
    assert "dark" in flags and "blurry" in flags


def test_index_served(client):
    assert client.get("/").status_code == 200
    assert "AgroVision" in client.get("/").text
