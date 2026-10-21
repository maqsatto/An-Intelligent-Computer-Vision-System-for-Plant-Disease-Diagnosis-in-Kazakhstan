from datetime import UTC, datetime, timedelta
from uuid import uuid4

from agrovision.assessments.queue import Queue
from agrovision.models import Assessment, Job
from sqlalchemy import select


def enqueue(client, headers):
    from test_vertical import image_bytes

    obs = client.post(
        "/v1/observations",
        headers=headers,
        json={
            "client_observation_id": str(uuid4()),
            "crop_id": "wheat",
            "organ": "leaf",
            "captured_at": "2026-10-21T19:00:00+05:00",
        },
    ).json()
    photo = client.post(
        f"/v1/observations/{obs['id']}/photos",
        headers=headers,
        data={"client_photo_id": str(uuid4()), "purpose": "primary"},
        files={"file": ("leaf.jpg", image_bytes(), "image/jpeg")},
    ).json()
    response = client.post(
        "/v1/assessments",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"observation_id": obs["id"], "primary_photo_id": photo["id"]},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def expire(app, job_id):
    with app.state.sessions.begin() as db:
        job = db.get(Job, job_id)
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)


def test_reclaim_fences_stale_worker(client, headers, app, settings):
    aid = enqueue(client, headers)
    queue = Queue(settings, app.state.sessions)
    first = queue.claim()
    expire(app, first.job_id)
    second = queue.claim()
    assert second.token != first.token
    result = {
        "outcome": "inconclusive",
        "reason_codes": ["insufficient_evidence"],
        "prediction": None,
        "candidates": [],
        "quality": {"status": "not_assessed", "flags": []},
        "next_action": "consult_expert",
    }
    assert queue.complete(first, result) is False
    assert queue.fail(first, "model_execution_failed", True) is False
    assert queue.complete(second, result) is True
    assert queue.complete(first, result) is False
    with app.state.sessions() as db:
        assert db.get(Assessment, aid).status == "completed"
        assert db.scalar(select(Job).where(Job.assessment_id == aid)).attempts == 2


def test_death_on_last_attempt_eventually_terminalizes(client, headers, app, settings):
    aid = enqueue(client, headers)
    queue = Queue(settings, app.state.sessions)
    for attempt in range(1, settings.max_attempts + 1):
        claim = queue.claim()
        assert claim is not None
        assert claim.attempt == attempt
        expire(app, claim.job_id)
    assert queue.claim() is None
    with app.state.sessions() as db:
        item = db.get(Assessment, aid)
        assert item.status == "failed"
        assert item.error["code"] == "assessment_timeout"
        assert item.finished_at is not None
