from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ErrorRead(DTO):
    code: str
    message: str
    details: dict | list | None = None
    request_id: str


class MeRead(DTO):
    id: UUID
    display_name: str | None = None


class ModelRead(DTO):
    version: str
    artifact_sha256: str
    preprocessing_version: str
    decision_policy_version: str


class Candidate(DTO):
    class_id: str
    crop_id: str
    condition_id: str
    score: float | None = Field(ge=0, le=1)
    score_kind: Literal["model_score", "calibrated_probability"]
    score_space: Literal["global_joint", "crop_conditional"]


class Quality(DTO):
    status: Literal["passed", "warning", "unusable", "not_assessed"]
    flags: list[str]


class AssessmentResult(DTO):
    outcome: Literal["predicted", "inconclusive", "unsupported_input", "retake_photo"]
    reason_codes: list[str]
    prediction: Candidate | None
    candidates: list[Candidate] = Field(max_length=3)
    quality: Quality
    next_action: Literal["view_guidance", "retake_photo", "select_supported_crop", "consult_expert"]

    @model_validator(mode="after")
    def prediction_matches_outcome(self):
        if (self.outcome == "predicted") != (self.prediction is not None):
            raise ValueError("Only predicted outcome has a prediction")
        return self


class ProcessingError(DTO):
    code: str
    message: str
    retryable: bool


class AssessmentBase(DTO):
    id: UUID
    observation_id: UUID
    primary_photo_id: UUID
    crop_id: str
    model: ModelRead
    created_at: datetime
    started_at: datetime | None


class AssessmentPending(AssessmentBase):
    status: Literal["queued", "running"]
    result: None = None
    error: None = None
    finished_at: None = None


class AssessmentCompleted(AssessmentBase):
    status: Literal["completed"]
    result: AssessmentResult
    error: None = None
    finished_at: datetime


class AssessmentFailed(AssessmentBase):
    status: Literal["failed"]
    result: None = None
    error: ProcessingError
    finished_at: datetime


AssessmentVariant = Annotated[
    AssessmentPending | AssessmentCompleted | AssessmentFailed, Field(discriminator="status")
]


class AssessmentRead(RootModel[AssessmentVariant]):
    pass


class AssessmentCreate(DTO):
    observation_id: UUID
    primary_photo_id: UUID


class ObservationCreate(DTO):
    client_observation_id: UUID
    crop_id: str = Field(max_length=64)
    organ: str = Field(max_length=32)
    captured_at: datetime
    field_season_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def offset_required(self):
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include timezone offset")
        return self


class PhotoRead(DTO):
    id: UUID
    observation_id: UUID
    purpose: Literal["primary", "context"]
    status: Literal["pending", "ready", "failed"]
    media_type: str
    width: int
    height: int
    sha256: str
    created_at: datetime


class ObservationRead(DTO):
    id: UUID
    client_observation_id: UUID
    crop_id: str
    organ: str
    captured_at: datetime
    field_season_id: None = None
    notes: str | None
    created_at: datetime
    photos: list[PhotoRead]
    assessments: list[AssessmentRead]


class ObservationPage(DTO):
    items: list[ObservationRead]
    next_cursor: str | None


class ClassRead(DTO):
    class_id: str
    condition_id: str


class CropRead(DTO):
    id: str
    name_ru: str
    support_status: Literal["unavailable", "development", "validated"]
    can_assess: bool
    supported_organs: list[str]
    model_version: str | None
    availability_reason: str | None
    classes: list[ClassRead]


class CatalogRead(DTO):
    catalog_version: str
    runtime_mode: Literal["production", "development"]
    crops: list[CropRead]


class ContentURL(DTO):
    url: str
    expires_at: datetime


class FeedbackCreate(DTO):
    helpful: bool | None = None
    suspected_error: bool = False
    note: str | None = Field(default=None, max_length=1000)


class FeedbackRead(FeedbackCreate):
    id: UUID
    assessment_id: UUID
    created_at: datetime


class DeleteRead(DTO):
    status: Literal["deletion_pending"] = "deletion_pending"
