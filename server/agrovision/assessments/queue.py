"""One-purpose durable queue: short transactions, global lock order and fenced commits."""

import random
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from agrovision.models import Assessment, Job, Observation, Photo
from agrovision.schemas import AssessmentResult
from sqlalchemy import and_, func, or_, select


@dataclass(frozen=True)
class Claim:
    job_id: str
    assessment_id: str
    observation_id: str
    token: str
    attempt: int
    object_key: str
    photo_sha256: str
    crop_id: str
    organ: str
    model: dict
    model_mode: str
    bundle_path: str | None
    bundle_manifest: dict | None


class Queue:
    def __init__(self, settings, sessions):
        self.settings, self.sessions = settings, sessions

    @staticmethod
    def now(db):
        return db.scalar(select(func.clock_timestamp()))

    def claim(self):
        with self.sessions() as db:
            now = self.now(db)
            candidates = list(
                db.execute(
                    select(Job.id, Assessment.id, Assessment.observation_id)
                    .join(Assessment, Assessment.id == Job.assessment_id)
                    .where(
                        or_(
                            and_(Job.state == "queued", Job.available_at <= now),
                            and_(Job.state == "running", Job.lease_until <= now),
                        )
                    )
                    .order_by(Job.available_at, Job.id)
                    .limit(100)
                )
            )
        for job_id, assessment_id, observation_id in candidates:
            with self.sessions.begin() as db:
                # Every mutation follows observation -> assessment -> job, no locks held during inference.
                observation = db.scalar(
                    select(Observation)
                    .where(Observation.id == observation_id)
                    .with_for_update(skip_locked=True)
                )
                if observation is None:
                    continue
                assessment = db.scalar(
                    select(Assessment).where(Assessment.id == assessment_id).with_for_update(skip_locked=True)
                )
                if assessment is None:
                    continue
                job = db.scalar(select(Job).where(Job.id == job_id).with_for_update(skip_locked=True))
                if job is None:
                    continue
                now = self.now(db)
                eligible = (job.state == "queued" and job.available_at <= now) or (
                    job.state == "running" and job.lease_until and job.lease_until <= now
                )
                if not eligible:
                    continue
                if observation.deleted_at or assessment.status in {"completed", "failed"}:
                    job.state, job.lease_token, job.lease_until = "cancelled", None, None
                    continue
                if job.attempts >= job.max_attempts:
                    self._terminal_failure(assessment, job, now, "assessment_timeout", True)
                    continue
                photo = db.get(Photo, assessment.primary_photo_id)
                if photo.status != "ready":
                    self._terminal_failure(assessment, job, now, "invalid_input", False)
                    continue
                job.attempts += 1
                job.state = "running"
                job.lease_token = str(uuid4())
                job.lease_until = now + timedelta(seconds=self.settings.lease_seconds)
                assessment.status = "running"
                assessment.started_at = assessment.started_at or now
                claim = Claim(
                    job.id,
                    assessment.id,
                    observation.id,
                    job.lease_token,
                    job.attempts,
                    photo.object_key,
                    photo.sha256,
                    assessment.crop_id,
                    assessment.organ,
                    assessment.model,
                    assessment.model_mode,
                    assessment.bundle_path,
                    assessment.bundle_manifest,
                )
            return claim
        return None

    def _locked(self, db, claim):
        observation = db.scalar(
            select(Observation).where(Observation.id == claim.observation_id).with_for_update()
        )
        assessment = db.scalar(
            select(Assessment).where(Assessment.id == claim.assessment_id).with_for_update()
        )
        job = db.scalar(select(Job).where(Job.id == claim.job_id).with_for_update())
        now = self.now(db)
        if (
            not observation
            or observation.deleted_at
            or not assessment
            or assessment.status != "running"
            or not job
            or job.state != "running"
            or job.lease_token != claim.token
            or not job.lease_until
            or job.lease_until <= now
        ):
            return None
        return assessment, job, now

    def complete(self, claim, result):
        result = AssessmentResult.model_validate(result).model_dump(mode="json")
        with self.sessions.begin() as db:
            locked = self._locked(db, claim)
            if locked is None:
                return False
            assessment, job, now = locked
            assessment.status, assessment.result, assessment.finished_at = "completed", result, now
            job.state, job.lease_token, job.lease_until = "completed", None, None
        return True

    @staticmethod
    def _terminal_failure(assessment, job, now, code, retryable):
        messages = {
            "assessment_timeout": "Не удалось завершить обработку за отведенное время.",
            "model_execution_failed": "Обработка завершилась технической ошибкой.",
            "storage_unavailable": "Не удалось прочитать сохраненную фотографию.",
            "bundle_mismatch": "Закрепленная версия модели недоступна или несовместима.",
            "invalid_input": "Сохраненная фотография не готова к обработке.",
        }
        assessment.status = "failed"
        assessment.result = None
        assessment.error = {
            "code": code,
            "message": messages.get(code, messages["model_execution_failed"]),
            "retryable": retryable,
        }
        assessment.finished_at = now
        job.state, job.last_error, job.lease_token, job.lease_until = "failed", code, None, None

    def fail(self, claim, code, retryable):
        with self.sessions.begin() as db:
            locked = self._locked(db, claim)
            if locked is None:
                return False
            assessment, job, now = locked
            if retryable and job.attempts < job.max_attempts:
                delay = self.settings.retry_base_seconds * 2 ** (job.attempts - 1)
                delay *= random.uniform(0.8, 1.2)
                job.state, job.available_at = "queued", now + timedelta(seconds=delay)
                job.last_error, job.lease_token, job.lease_until = code, None, None
                assessment.status = "queued"
            else:
                self._terminal_failure(assessment, job, now, code, retryable)
        return True
