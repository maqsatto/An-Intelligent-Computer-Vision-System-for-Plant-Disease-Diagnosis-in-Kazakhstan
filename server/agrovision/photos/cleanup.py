"""Bounded, idempotent private blob cleanup; no unbounded directory lists."""

import os
from collections import OrderedDict
from datetime import timedelta
from threading import Lock

from agrovision.models import Observation, Photo
from agrovision.photos.storage import LocalImageStore
from sqlalchemy import func, or_, select

_scanners = OrderedDict()
_scan_lock = Lock()


def _file_batch(root, limit):
    # Keep a bounded streaming cursor across sweeps; old live files cannot starve new orphans.
    # A restart starts a fresh complete pass; no photos or directory listings are buffered in RAM.
    with _scan_lock:
        key = str(root)
        scanner = _scanners.pop(key, None)
        if scanner is None:
            scanner = os.scandir(root)
        batch = []
        exhausted = False
        for _ in range(limit):
            try:
                batch.append(next(scanner))
            except StopIteration:
                exhausted = True
                break
        if exhausted:
            scanner.close()
        else:
            _scanners[key] = scanner
        while len(_scanners) > 16:
            _, evicted = _scanners.popitem(last=False)
            evicted.close()
        return batch


def cleanup_once(settings, sessions, grace_seconds=3600, limit=100):
    store = LocalImageStore(settings.storage_dir)
    deleted = 0
    with sessions() as db:
        now = db.scalar(select(func.clock_timestamp()))
        cutoff = now - timedelta(seconds=grace_seconds)
        rows = list(
            db.execute(
                select(Photo.id, Photo.observation_id)
                .join(Observation, Observation.id == Photo.observation_id)
                .where(
                    Photo.blob_deleted_at.is_(None),
                    or_(
                        Observation.deleted_at.is_not(None),
                        (Photo.status == "failed") & (Photo.created_at <= cutoff),
                        (Photo.status == "pending") & (Photo.upload_lease_until <= cutoff),
                    ),
                )
                .order_by(Photo.created_at, Photo.id)
                .limit(limit)
            )
        )
    for photo_id, observation_id in rows:
        with sessions.begin() as db:
            obs = db.scalar(select(Observation).where(Observation.id == observation_id).with_for_update())
            photo = db.scalar(select(Photo).where(Photo.id == photo_id).with_for_update())
            now = db.scalar(select(func.clock_timestamp()))
            eligible = bool(
                obs.deleted_at
                or photo.status == "failed"
                or (
                    photo.status == "pending" and photo.upload_lease_until and photo.upload_lease_until <= now
                )
            )
            if not eligible or photo.blob_deleted_at:
                continue
            key = photo.object_key
            if photo.status == "pending":
                photo.status, photo.upload_token, photo.upload_lease_until = "failed", None, None
        path = store.path(key)
        try:
            existed = path.exists()
            store.delete(key)
        except OSError:
            continue
        with sessions.begin() as db:
            obs = db.scalar(select(Observation).where(Observation.id == observation_id).with_for_update())
            photo = db.scalar(select(Photo).where(Photo.id == photo_id).with_for_update())
            if photo.object_key == key and (obs.deleted_at or photo.status == "failed"):
                photo.blob_deleted_at = db.scalar(select(func.clock_timestamp()))
        deleted += int(existed)
    # Scan only a bounded batch, advancing across sweeps. A tombstoned/failed referenced key
    # may reappear if an old uploader resumed and died after an earlier cleanup; revisit it.
    for entry in _file_batch(store.root, limit):
        try:
            if entry.name.startswith(".") or not entry.is_file(follow_symlinks=False):
                continue
            stat = entry.stat(follow_symlinks=False)
            with sessions() as db:
                now = db.scalar(select(func.clock_timestamp()))
                if stat.st_mtime > now.timestamp() - grace_seconds:
                    continue
                reference = db.execute(
                    select(Photo.status, Photo.upload_lease_until, Observation.deleted_at)
                    .join(Observation, Observation.id == Photo.observation_id)
                    .where(Photo.object_key == entry.name)
                ).first()
                live = bool(
                    reference
                    and not reference.deleted_at
                    and (
                        reference.status == "ready"
                        or (
                            reference.status == "pending"
                            and reference.upload_lease_until
                            and reference.upload_lease_until > now
                        )
                    )
                )
            if not live:
                store.delete(entry.name)
                deleted += 1
        except (FileNotFoundError, OSError):
            # Another cleanup or upload compensation may remove it between directory entry/stat/unlink.
            continue
    return deleted


def main():
    from agrovision.config import get_settings
    from agrovision.db import make_engine, make_sessions

    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        print(f"Removed {cleanup_once(settings, make_sessions(engine))} private/orphan blobs")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
