from uuid import uuid4

from agrovision.models import Assessment, Job, Photo
from agrovision.photos.storage import LocalImageStore
from sqlalchemy import select
from test_security_and_contract import assess, observation, ready_pair, upload


def test_deleted_during_model_selection_cannot_enqueue(client, headers, app, monkeypatch):
    from agrovision.assessments import service
    from agrovision.observations.service import delete

    original_select = service.select_model
    obs, photo = ready_pair(client, headers)

    def select_and_delete(settings, crop, organ):
        with app.state.sessions() as db:
            row = db.get(Photo, photo["id"])
            delete(db, obs["id"], row.owner_id)
        return original_select(settings, crop, organ)

    monkeypatch.setattr(service, "select_model", select_and_delete)
    response = assess(client, headers, obs, photo)
    assert response.status_code in {404, 409}, response.text
    with app.state.sessions() as db:
        assert list(db.scalars(select(Assessment))) == []
        assert list(db.scalars(select(Job))) == []


def test_transient_upload_error_same_client_id_can_recover(client, headers, app, monkeypatch):
    obs = observation(client, headers).json()
    original_put = LocalImageStore.put
    key = str(uuid4())
    calls = 0

    def fail_once(self, object_key, content):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("temporary unavailable")
        return original_put(self, object_key, content)

    monkeypatch.setattr(LocalImageStore, "put", fail_once)
    assert upload(client, headers, obs["id"], client_id=key).status_code == 503
    recovered = upload(client, headers, obs["id"], client_id=key)
    assert recovered.status_code in {200, 201}, recovered.text
    assert recovered.json()["status"] == "ready"
    assert upload(client, headers, obs["id"], client_id=key).json()["id"] == recovered.json()["id"]
    with app.state.sessions() as db:
        assert len(list(db.scalars(select(Photo)))) == 1


def test_cleanup_removes_deleted_blobs_without_reopening_read(client, headers, app, settings):
    from agrovision.photos.cleanup import cleanup_once

    obs, photo = ready_pair(client, headers)
    with app.state.sessions() as db:
        key = db.get(Photo, photo["id"]).object_key
    path = settings.storage_dir / key
    assert path.exists()
    assert client.delete("/v1/observations/" + obs["id"], headers=headers).status_code == 202
    assert cleanup_once(settings, app.state.sessions, grace_seconds=0) >= 1
    assert not path.exists()
    assert cleanup_once(settings, app.state.sessions, grace_seconds=0) == 0


def test_orphan_scan_advances_past_old_live_files(client, headers, app, settings):
    import os

    from agrovision.photos.cleanup import cleanup_once

    for _ in range(3):
        ready_pair(client, headers)
    for path in settings.storage_dir.iterdir():
        os.utime(path, (1000, 1000))
    orphan = settings.storage_dir / "orphan-unreferenced.jpg"
    orphan.write_bytes(b"abandoned bytes")
    os.utime(orphan, (2000, 2000))
    for _ in range(10):
        cleanup_once(settings, app.state.sessions, grace_seconds=0, limit=2)
    assert not orphan.exists()
    with app.state.sessions() as db:
        assert all((settings.storage_dir / p.object_key).exists() for p in db.scalars(select(Photo)))


def test_late_blob_after_cleanup_is_still_eventually_removed(client, headers, app, settings):
    from agrovision.photos.cleanup import cleanup_once

    obs, photo = ready_pair(client, headers)
    with app.state.sessions() as db:
        key = db.get(Photo, photo["id"]).object_key
    client.delete("/v1/observations/" + obs["id"], headers=headers)
    cleanup_once(settings, app.state.sessions, grace_seconds=0)
    # Models a suspended old uploader writing then dying after cleanup recorded the missing blob.
    LocalImageStore(settings.storage_dir).put(key, b"late abandoned upload")
    for _ in range(3):
        cleanup_once(settings, app.state.sessions, grace_seconds=0)
    assert not (settings.storage_dir / key).exists()
