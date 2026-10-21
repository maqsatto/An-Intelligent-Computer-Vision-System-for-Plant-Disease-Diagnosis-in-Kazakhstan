"""Meaningful real-PostgreSQL tests; API never runs inference in request."""

from io import BytesIO
from uuid import uuid4

from PIL import Image


def image_bytes(color="green"):
    buf = BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="JPEG")
    return buf.getvalue()


def test_observation_upload_assessment_and_immutable_result(client, headers, worker):
    observation = client.post(
        "/v1/observations",
        headers=headers,
        json={
            "client_observation_id": str(uuid4()),
            "crop_id": "wheat",
            "organ": "leaf",
            "captured_at": "2026-10-21T19:00:00+05:00",
        },
    )
    assert observation.status_code == 201, observation.text
    oid = observation.json()["id"]
    photo = client.post(
        f"/v1/observations/{oid}/photos",
        headers=headers,
        data={"client_photo_id": str(uuid4()), "purpose": "primary"},
        files={"file": ("leaf.jpg", image_bytes(), "image/jpeg")},
    )
    assert photo.status_code == 201, photo.text
    body = {"observation_id": oid, "primary_photo_id": photo.json()["id"]}
    key_headers = {**headers, "Idempotency-Key": str(uuid4())}
    queued = client.post("/v1/assessments", headers=key_headers, json=body)
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "queued"
    assert worker.run_once()
    read = client.get("/v1/assessments/" + queued.json()["id"], headers=headers)
    assert read.json()["status"] == "completed", read.text
    assert read.json()["result"]["outcome"] == "inconclusive"
    assert read.json()["result"]["prediction"] is None
    replay = client.post("/v1/assessments", headers=key_headers, json=body)
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == read.json()
    assert not worker.run_once()
