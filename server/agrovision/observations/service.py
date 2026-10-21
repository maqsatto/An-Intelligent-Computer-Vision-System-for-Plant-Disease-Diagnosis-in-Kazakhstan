import base64
import hashlib
import json
from datetime import UTC, datetime

from agrovision import schemas as S
from agrovision.catalog.service import CROPS
from agrovision.errors import APIError
from agrovision.models import Assessment, Job, Observation, Photo
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError


def semantic_hash(body):
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def owned(db, observation_id, owner_id, *, lock=False, include_deleted=False):
    stmt = select(Observation).where(Observation.id == observation_id, Observation.owner_id == owner_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(stmt)
    if item is None or (item.deleted_at is not None and not include_deleted):
        raise APIError(404, "not_found", "Наблюдение не найдено.")
    return item


def create(db, owner_id, body):
    if body.crop_id not in CROPS:
        raise APIError(422, "invalid_crop", "Выберите культуру из каталога.")
    if body.organ != "leaf":
        raise APIError(422, "invalid_organ", "Сейчас можно сохранить фотографию листа.")
    if body.field_season_id is not None:
        raise APIError(422, "invalid_field_season", "Привязка к участку будет доступна позднее.")
    canonical = body.model_dump(mode="json")
    canonical["captured_at"] = body.captured_at.astimezone(UTC).isoformat()
    digest = semantic_hash(canonical)

    def replay():
        item = db.scalar(
            select(Observation).where(
                Observation.owner_id == owner_id,
                Observation.client_observation_id == str(body.client_observation_id),
            )
        )
        if item is not None:
            if item.deleted_at:
                raise APIError(409, "resource_deleted", "Наблюдение удалено.")
            if item.body_hash != digest:
                raise APIError(
                    409, "idempotency_conflict", "Этот идентификатор уже использован для другого наблюдения."
                )
        return item

    existing = replay()
    if existing:
        return existing, True
    item = Observation(
        owner_id=owner_id,
        client_observation_id=str(body.client_observation_id),
        body_hash=digest,
        crop_id=body.crop_id,
        organ=body.organ,
        captured_at=body.captured_at.astimezone(UTC),
        notes=body.notes,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = replay()
        if existing:
            return existing, True
        raise
    return item, False


def read(db, item):
    photos = db.scalars(
        select(Photo).where(Photo.observation_id == item.id).order_by(Photo.created_at, Photo.id)
    ).all()
    assessments = db.scalars(
        select(Assessment)
        .where(Assessment.observation_id == item.id)
        .order_by(Assessment.created_at, Assessment.id)
    ).all()
    return S.ObservationRead(
        **{
            k: getattr(item, k)
            for k in ["id", "client_observation_id", "crop_id", "organ", "captured_at", "notes", "created_at"]
        },
        photos=[S.PhotoRead.model_validate(x) for x in photos],
        assessments=[S.AssessmentRead.model_validate(x) for x in assessments],
    )


def history(db, owner_id, cursor, limit, crop_id, from_, to):
    stmt = select(Observation).where(Observation.owner_id == owner_id, Observation.deleted_at.is_(None))
    if crop_id:
        if crop_id not in CROPS:
            raise APIError(422, "invalid_crop", "Неизвестная культура.")
        stmt = stmt.where(Observation.crop_id == crop_id)
    for value in [from_, to]:
        if value is not None and value.tzinfo is None:
            raise APIError(422, "invalid_request", "Фильтр даты должен содержать часовой пояс.")
    if from_:
        stmt = stmt.where(Observation.captured_at >= from_)
    if to:
        stmt = stmt.where(Observation.captured_at <= to)
    if cursor:
        try:
            stamp, item_id = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            stamp = datetime.fromisoformat(stamp)
            from uuid import UUID

            item_id = str(UUID(item_id))
            if stamp.tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise APIError(422, "invalid_cursor", "Недействительный указатель страницы.") from None
        stmt = stmt.where(
            or_(
                Observation.created_at < stamp,
                and_(Observation.created_at == stamp, Observation.id < item_id),
            )
        )
    items = list(
        db.scalars(stmt.order_by(Observation.created_at.desc(), Observation.id.desc()).limit(limit + 1))
    )
    more = len(items) > limit
    items = items[:limit]
    next_cursor = None
    if more:
        next_cursor = base64.urlsafe_b64encode(
            json.dumps([items[-1].created_at.isoformat(), items[-1].id]).encode()
        ).decode()
    return {"items": [read(db, item) for item in items], "next_cursor": next_cursor}


def delete(db, observation_id, owner_id):
    item = owned(db, observation_id, owner_id, lock=True, include_deleted=True)
    if not item.deleted_at:
        item.deleted_at = datetime.now(UTC)
        assessments = db.scalars(
            select(Assessment)
            .where(Assessment.observation_id == item.id)
            .order_by(Assessment.id)
            .with_for_update()
        ).all()
        for assessment in assessments:
            job = db.scalar(select(Job).where(Job.assessment_id == assessment.id).with_for_update())
            if assessment.status in {"queued", "running"}:
                assessment.status = "failed"
                assessment.error = {
                    "code": "resource_deleted",
                    "message": "Наблюдение удалено.",
                    "retryable": False,
                }
                assessment.finished_at = datetime.now(UTC)
            if job and job.state in {"queued", "running"}:
                job.state, job.lease_token, job.lease_until = "cancelled", None, None
    db.commit()
