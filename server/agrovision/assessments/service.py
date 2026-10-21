from agrovision.catalog.service import select_model
from agrovision.errors import APIError
from agrovision.models import Assessment, Feedback, Idempotency, Job, Photo
from agrovision.observations.service import owned as owned_observation
from agrovision.observations.service import semantic_hash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def owned(db, assessment_id, owner_id):
    item = db.scalar(
        select(Assessment).where(Assessment.id == assessment_id, Assessment.owner_id == owner_id)
    )
    if item is None:
        raise APIError(404, "not_found", "Оценка не найдена.")
    owned_observation(db, item.observation_id, owner_id)
    return item


def create(db, settings, owner_id, key, body):
    body_hash = semantic_hash(body.model_dump(mode="json"))

    def replay():
        record = db.scalar(
            select(Idempotency).where(
                Idempotency.owner_id == owner_id,
                Idempotency.operation == "assessment",
                Idempotency.key == key,
            )
        )
        if record is None:
            return None
        if record.body_hash != body_hash:
            raise APIError(409, "idempotency_conflict", "Этот ключ уже использован для другого запроса.")
        assessment = db.get(Assessment, record.assessment_id)
        observation = owned_observation(db, assessment.observation_id, owner_id, include_deleted=True)
        if observation.deleted_at:
            raise APIError(409, "resource_deleted", "Наблюдение удалено.")
        return assessment

    previous = replay()
    if previous:
        return previous, True
    observation = owned_observation(db, str(body.observation_id), owner_id)
    initial_photo = db.scalar(
        select(Photo).where(
            Photo.id == str(body.primary_photo_id),
            Photo.owner_id == owner_id,
            Photo.observation_id == observation.id,
        )
    )
    if initial_photo is None:
        raise APIError(404, "not_found", "Фотография не найдена.")
    if initial_photo.status != "ready":
        raise APIError(409, "photo_not_ready", "Дождитесь завершения загрузки.")
    crop_id, organ = observation.crop_id, observation.organ
    # Ensure model loading/manifest IO is outside database transaction and row locks.
    db.commit()
    snapshot, bundle_path, mode, manifest = select_model(settings, crop_id, organ)
    observation = owned_observation(db, str(body.observation_id), owner_id, lock=True)
    photo = db.scalar(
        select(Photo)
        .where(
            Photo.id == str(body.primary_photo_id),
            Photo.owner_id == owner_id,
            Photo.observation_id == observation.id,
        )
        .with_for_update()
    )
    if photo is None:
        raise APIError(404, "not_found", "Фотография не найдена.")
    if photo.status != "ready":
        raise APIError(409, "photo_not_ready", "Дождитесь завершения загрузки.")
    assessment = Assessment(
        owner_id=owner_id,
        observation_id=observation.id,
        primary_photo_id=photo.id,
        crop_id=crop_id,
        organ=organ,
        status="queued",
        model=snapshot,
        bundle_path=bundle_path,
        model_mode=mode,
        bundle_manifest=manifest,
    )
    db.add(assessment)
    db.flush()
    db.add(Job(assessment_id=assessment.id, max_attempts=settings.max_attempts))
    db.add(
        Idempotency(
            owner_id=owner_id,
            operation="assessment",
            key=key,
            body_hash=body_hash,
            assessment_id=assessment.id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = replay()
        if previous:
            return previous, True
        raise
    return assessment, False


def feedback(db, assessment_id, owner_id, body):
    assessment = owned(db, assessment_id, owner_id)
    if assessment.status not in {"completed", "failed"}:
        raise APIError(409, "assessment_not_finished", "Сначала дождитесь завершения оценки.")
    record = Feedback(assessment_id=assessment_id, owner_id=owner_id, **body.model_dump())
    db.add(record)
    db.commit()
    return record
