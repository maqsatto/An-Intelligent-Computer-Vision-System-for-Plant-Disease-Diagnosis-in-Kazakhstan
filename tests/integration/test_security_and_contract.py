from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from agrovision.models import Assessment, Idempotency, Job
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_vertical import image_bytes


def observation(client, headers, crop="wheat", client_id=None, **extra):
    return client.post(
        "/v1/observations",
        headers=headers,
        json={
            "client_observation_id": client_id or str(uuid4()),
            "crop_id": crop,
            "organ": "leaf",
            "captured_at": "2026-10-21T19:00:00+05:00",
            **extra,
        },
    )


def upload(client, headers, oid, payload=None, client_id=None, purpose="primary"):
    return client.post(
        f"/v1/observations/{oid}/photos",
        headers=headers,
        data={"client_photo_id": client_id or str(uuid4()), "purpose": purpose},
        files={"file": ("leaf.jpg", image_bytes() if payload is None else payload, "image/jpeg")},
    )


def ready_pair(client, headers, crop="wheat"):
    obs = observation(client, headers, crop=crop)
    assert obs.status_code == 201, obs.text
    photo = upload(client, headers, obs.json()["id"])
    assert photo.status_code == 201, photo.text
    return obs.json(), photo.json()


def assess(client, headers, obs, photo, key=None):
    return client.post(
        "/v1/assessments",
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
        json={"observation_id": obs["id"], "primary_photo_id": photo["id"]},
    )


def test_all_personal_ids_are_owner_scoped(client, headers, other_headers):
    obs, photo = ready_pair(client, headers)
    assessment = assess(client, headers, obs, photo).json()
    signed = client.get(f"/v1/photos/{photo['id']}/content-url", headers=headers).json()["url"]
    assert client.get(signed, headers=headers).status_code == 200
    for path in [
        f"/v1/observations/{obs['id']}",
        f"/v1/photos/{photo['id']}/content-url",
        signed,
        f"/v1/assessments/{assessment['id']}",
    ]:
        assert client.get(path, headers=other_headers).status_code == 404, path
        assert client.get(path).status_code == 401, path
    assert client.get("/v1/observations", headers=other_headers).json()["items"] == []
    assert client.delete(f"/v1/observations/{obs['id']}", headers=other_headers).status_code == 404
    assert upload(client, other_headers, obs["id"]).status_code == 404
    own = observation(client, other_headers).json()
    assert assess(client, other_headers, own, photo).status_code == 404
    assert (
        client.post(
            f"/v1/assessments/{assessment['id']}/feedback", headers=other_headers, json={"helpful": True}
        ).status_code
        == 404
    )


def test_observation_replay_semantic_timezone_and_conflict(client, headers):
    key = str(uuid4())
    first = observation(client, headers, client_id=key)
    replay = observation(client, headers, client_id=key, captured_at="2026-10-21T14:00:00Z")
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert observation(client, headers, client_id=key, notes="changed").status_code == 409
    assert observation(client, headers, crop="unknown").json()["code"] == "invalid_crop"
    assert observation(client, headers, organ="fruit").json()["code"] == "invalid_organ"
    assert observation(client, headers, field_season_id=str(uuid4())).status_code == 422
    assert observation(client, headers, captured_at="2026-10-21T14:00:00").status_code == 422


def test_assessment_key_body_conflict_and_replay_before_model_availability(client, headers, settings, app):
    obs, photo = ready_pair(client, headers)
    key = str(uuid4())
    original = assess(client, headers, obs, photo, key=key)
    app.state.settings.dev_predictor = False
    replay = assess(client, headers, obs, photo, key=key)
    assert replay.status_code == 200
    assert replay.json()["id"] == original.json()["id"]
    assert replay.json()["model"] == original.json()["model"]
    other = observation(client, headers).json()
    assert assess(client, headers, other, photo, key=key).status_code == 409
    assert assess(client, headers, obs, photo).status_code == 503
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Assessment)) == 1
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.scalar(select(func.count()).select_from(Idempotency)) == 1


def test_simultaneous_submission_creates_one_effect(client, headers, app):
    obs, photo = ready_pair(client, headers)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=6) as pool:
        replies = list(pool.map(lambda _: assess(client, headers, obs, photo, key=key), range(6)))
    assert sorted(r.status_code for r in replies) == [200] * 5 + [202]
    assert len({r.json()["id"] for r in replies}) == 1
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Assessment)) == 1
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.scalar(select(func.count()).select_from(Idempotency)) == 1


def test_photo_id_replay_and_changed_bytes_conflict(client, headers):
    obs = observation(client, headers).json()
    key = str(uuid4())
    first = upload(client, headers, obs["id"], client_id=key)
    replay = upload(client, headers, obs["id"], client_id=key)
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert upload(client, headers, obs["id"], client_id=key, payload=image_bytes("red")).status_code == 409
    assert upload(client, headers, obs["id"], client_id=key, purpose="context").status_code == 409


def test_bad_decode_real_format_byte_and_pixel_limits(client, headers, app):
    obs = observation(client, headers).json()
    assert upload(client, headers, obs["id"], b"not an image").json()["code"] == "image_decode_failed"
    assert upload(client, headers, obs["id"], image_bytes()[:100]).status_code == 422
    gif = BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    assert upload(client, headers, obs["id"], gif.getvalue()).status_code == 415
    app.state.settings.max_image_bytes = 100
    assert upload(client, headers, obs["id"]).status_code == 413
    app.state.settings.max_image_bytes = 10 * 1024 * 1024
    app.state.settings.max_image_pixels = 1000
    assert upload(client, headers, obs["id"]).status_code == 413


def test_exif_rgb_private_content_normalization(client, headers):
    obs = observation(client, headers).json()
    data = BytesIO()
    image = Image.new("L", (60, 40), 128)
    exif = image.getexif()
    exif[274] = 6
    exif[270] = "private metadata"
    image.save(data, format="JPEG", exif=exif)
    photo = upload(client, headers, obs["id"], payload=data.getvalue()).json()
    assert (photo["width"], photo["height"]) == (40, 60)
    signed = client.get(f"/v1/photos/{photo['id']}/content-url", headers=headers).json()["url"]
    result = client.get(signed, headers=headers)
    assert result.status_code == 200
    with Image.open(BytesIO(result.content)) as image:
        assert image.mode == "RGB"
        assert not image.getexif()
    assert client.get(signed.replace("signature=", "signature=bad"), headers=headers).status_code == 404


def test_delete_blocks_read_download_replay_and_finalize(client, headers, app, worker):
    obs, photo = ready_pair(client, headers)
    key = str(uuid4())
    assessment = assess(client, headers, obs, photo, key=key).json()
    claim = worker.queue.claim()
    assert claim
    signed = client.get(f"/v1/photos/{photo['id']}/content-url", headers=headers).json()["url"]
    assert client.delete(f"/v1/observations/{obs['id']}", headers=headers).status_code == 202
    assert client.get(signed, headers=headers).status_code == 404
    assert client.get("/v1/assessments/" + assessment["id"], headers=headers).status_code == 404
    assert assess(client, headers, obs, photo, key=key).json()["code"] == "resource_deleted"
    assert client.get("/v1/observations", headers=headers).json()["items"] == []
    result = {
        "outcome": "inconclusive",
        "reason_codes": [],
        "prediction": None,
        "candidates": [],
        "quality": {"status": "not_assessed", "flags": []},
        "next_action": "consult_expert",
    }
    assert worker.queue.complete(claim, result) is False
    with app.state.sessions() as db:
        assert db.get(Assessment, assessment["id"]).result is None


def test_ready_photo_and_terminal_assessment_are_db_immutable(client, headers, app, worker):
    obs, photo = ready_pair(client, headers)
    assessment = assess(client, headers, obs, photo).json()
    assert worker.run_once()
    with app.state.engine.begin() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE photos SET sha256=:value WHERE id=:id"), {"value": "0" * 64, "id": photo["id"]}
            )
    with app.state.engine.begin() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE assessments SET status='queued',result=NULL,finished_at=NULL WHERE id=:id"),
                {"id": assessment["id"]},
            )
    before = client.get("/v1/assessments/" + assessment["id"], headers=headers).json()
    feedback = client.post(
        f"/v1/assessments/{assessment['id']}/feedback",
        headers=headers,
        json={"helpful": False, "suspected_error": True, "note": "user opinion"},
    )
    assert feedback.status_code == 201
    assert client.get("/v1/assessments/" + assessment["id"], headers=headers).json() == before


def test_catalog_is_capabilities_not_pilot_names(client, headers, app):
    app.state.settings.dev_predictor = False
    catalog = client.get("/v1/catalog").json()
    assert all(not item["can_assess"] for item in catalog["crops"])
    assert catalog["runtime_mode"] == "production"
    assert (
        next(x for x in catalog["crops"] if x["id"] == "wheat")["availability_reason"] == "model_unavailable"
    )
    obs, photo = ready_pair(client, headers, crop="maize")
    reply = assess(client, headers, obs, photo)
    assert reply.status_code == 422 and reply.json()["code"] == "unsupported_crop"
    obs2, photo2 = ready_pair(client, headers)
    reply = assess(client, headers, obs2, photo2)
    assert reply.status_code == 503 and reply.json()["code"] == "model_unavailable"


def test_history_pagination_filters_and_no_duplicate_rows(client, headers):
    ids = {observation(client, headers, crop=crop).json()["id"] for crop in ["wheat", "wheat", "tomato"]}
    first = client.get("/v1/observations?limit=2", headers=headers).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = client.get(
        "/v1/observations", params={"limit": 2, "cursor": first["next_cursor"]}, headers=headers
    ).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert {i["id"] for i in first["items"] + second["items"]} == ids
    assert len(client.get("/v1/observations?crop_id=wheat", headers=headers).json()["items"]) == 2
    assert client.get("/v1/observations?cursor=malformed", headers=headers).status_code == 422
    assert client.get("/v1/observations?from=2026-10-21T14:00:00", headers=headers).status_code == 422


def test_expired_or_untrusted_token_is_rejected(client, settings):
    import jwt

    token = jwt.encode(
        {
            "sub": "user-a",
            "iss": "agrovision-development",
            "aud": "agrovision-mobile",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        settings.dev_token_secret,
        algorithm="HS256",
    )
    assert (
        client.get("/v1/me", headers={"Authorization": "Bearer " + token}).json()["code"] == "session_expired"
    )
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + str(uuid4())}).status_code == 401


def test_configured_oidc_can_be_used_in_development_without_accepting_wrong_audience(client, app):
    from types import SimpleNamespace

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app.state.settings.oidc_issuer = "https://identity.example.test/realms/agrovision"
    app.state.settings.oidc_audience = "agrovision-mobile"
    app.state.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    payload = {
        "sub": "external-user",
        "iss": app.state.settings.oidc_issuer,
        "aud": "agrovision-mobile",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, private, algorithm="RS256")
    read = client.get("/v1/me", headers={"Authorization": "Bearer " + token})
    assert read.status_code == 200, read.text
    changed = jwt.encode({**payload, "aud": "another-app"}, private, algorithm="RS256")
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + changed}).status_code == 401
    forged = jwt.encode(payload, "wrong-signing-secret", algorithm="HS256")
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + forged}).status_code == 401
