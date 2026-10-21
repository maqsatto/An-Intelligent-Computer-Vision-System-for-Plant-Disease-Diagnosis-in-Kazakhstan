"""Relational invariants shared across functional service boundaries."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return str(uuid4())


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    client_observation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    body_hash: Mapped[str] = mapped_column(String(64))
    crop_id: Mapped[str] = mapped_column(String(64))
    organ: Mapped[str] = mapped_column(String(32))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("owner_id", "client_observation_id"),
        UniqueConstraint("id", "owner_id"),
        CheckConstraint("organ = 'leaf'"),
        CheckConstraint("crop_id in ('wheat','potato','tomato','maize')"),
    )


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    observation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    client_photo_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    purpose: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    blob_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upload_token: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    upload_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_sha256: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(128), unique=True)
    media_type: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("owner_id", "client_photo_id"),
        UniqueConstraint("id", "observation_id", "owner_id"),
        ForeignKeyConstraint(["observation_id", "owner_id"], ["observations.id", "observations.owner_id"]),
        CheckConstraint("status in ('pending','ready','failed')"),
        CheckConstraint("purpose in ('primary','context')"),
        CheckConstraint("width > 0 and height > 0"),
    )


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    observation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    primary_photo_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    crop_id: Mapped[str] = mapped_column(String(64))
    organ: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    model: Mapped[dict] = mapped_column(JSON)
    bundle_manifest: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    model_mode: Mapped[str] = mapped_column(String(16), default="validated")
    bundle_path: Mapped[str | None] = mapped_column(String(1024))
    result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    error: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["primary_photo_id", "observation_id", "owner_id"],
            ["photos.id", "photos.observation_id", "photos.owner_id"],
        ),
        CheckConstraint("status in ('queued','running','completed','failed')"),
        CheckConstraint(
            "(status in ('queued','running') AND result IS NULL AND error IS NULL "
            "AND finished_at IS NULL) OR (status='completed' AND result IS NOT NULL "
            "AND error IS NULL AND finished_at IS NOT NULL) OR (status='failed' "
            "AND result IS NULL AND error IS NOT NULL AND finished_at IS NOT NULL)"
        ),
    )


class Job(Base):
    __tablename__ = "assessment_jobs"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), unique=True)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_token: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint("state in ('queued','running','completed','failed','cancelled')"),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts"),
        Index("ix_jobs_eligible", "state", "available_at", "lease_until"),
    )


class Idempotency(Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    operation: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    body_hash: Mapped[str] = mapped_column(String(64))
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"))
    __table_args__ = (UniqueConstraint("owner_id", "operation", "key"),)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"))
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    helpful: Mapped[bool | None]
    suspected_error: Mapped[bool]
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
