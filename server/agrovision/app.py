import logging
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

import jwt
from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException

from . import schemas as S
from .config import Settings, get_settings
from .db import make_engine, make_sessions
from .deps import session
from .errors import APIError, error_response
from .identity.auth import Actor, current_actor

ActorDep = Annotated[Actor, Depends(current_actor)]
SessionDep = Annotated[object, Depends(session)]


def create_app(settings: Settings | None = None):
    settings = settings or get_settings()
    app = FastAPI(
        title="AgroVision API",
        version="0.1.0",
        description="Plant observation and durable assessment API. Predictions are hypotheses.",
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.sessions = make_sessions(app.state.engine)
    app.state.jwks = jwt.PyJWKClient(settings.oidc_jwks_url, timeout=5) if settings.oidc_jwks_url else None

    @app.middleware("http")
    async def trace_and_limit(request: Request, call_next):
        request.state.request_id = str(uuid4())
        # Parser has bounded max file count/part size; bound total HTTP body too, including chunked requests.
        if request.method in {"POST", "PUT", "PATCH"}:
            max_body = (
                settings.max_image_bytes + 128 * 1024 if request.url.path.endswith("/photos") else 64 * 1024
            )
            received = 0
            original_receive = request._receive

            async def bounded_receive():
                nonlocal received
                message = await original_receive()
                received += len(message.get("body", b""))
                if received > max_body:
                    raise APIError(413, "image_too_large", "Превышен допустимый размер запроса.")
                return message

            request._receive = bounded_receive
            length = request.headers.get("content-length")
            if length:
                try:
                    if int(length) > max_body:
                        return error_response(request, 413, "image_too_large", "Превышен размер запроса.")
                except ValueError:
                    return error_response(request, 400, "invalid_request", "Неверная длина запроса.")
        try:
            response = await call_next(request)
        except APIError as exc:
            response = error_response(request, exc.status, exc.code, exc.message, exc.details)
        if response.status_code == 429:
            response.headers["Retry-After"] = "3"
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Avoid echoing input (including credentials, notes or arbitrary request content).
        details = [{"loc": list(e["loc"]), "type": e["type"], "msg": e["msg"]} for e in exc.errors()]
        return error_response(request, 422, "invalid_request", "Проверьте поля запроса.", details)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code, "invalid_request", "Запрос не может быть обработан.")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logging.getLogger("agrovision.api").error(
            "request_failed request_id=%s", getattr(request.state, "request_id", "unknown")
        )
        return error_response(
            request, 500, "internal_error", "Временная техническая ошибка. Повторите позже."
        )

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready(db: SessionDep):
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "runtime_mode": "development"
            if settings.dev_predictor or settings.research_bundle_dir
            else "production",
        }

    errors = {s: {"model": S.ErrorRead} for s in [401, 404, 409, 413, 415, 422, 429, 503]}

    @app.get("/v1/catalog", response_model=S.CatalogRead, tags=["catalog"])
    def catalog():
        from .catalog.service import get_catalog

        return get_catalog(settings)

    @app.get("/v1/me", response_model=S.MeRead, responses=errors, tags=["identity"])
    def me(actor: ActorDep):
        return {"id": actor.id, "display_name": actor.display_name}

    @app.post(
        "/v1/observations",
        response_model=S.ObservationRead,
        status_code=201,
        responses={200: {"model": S.ObservationRead}, **errors},
        tags=["observations"],
    )
    def create_observation(body: S.ObservationCreate, actor: ActorDep, db: SessionDep, response: Response):
        from .observations.service import create, read

        item, replay = create(db, actor.id, body)
        if replay:
            response.status_code = 200
        return read(db, item)

    @app.get("/v1/observations", response_model=S.ObservationPage, responses=errors, tags=["observations"])
    def history(
        actor: ActorDep,
        db: SessionDep,
        cursor: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        crop_id: str | None = None,
        from_: datetime | None = Query(None, alias="from"),
        to: datetime | None = None,
    ):
        from .observations.service import history as get_history

        return get_history(db, actor.id, cursor, limit, crop_id, from_, to)

    @app.get(
        "/v1/observations/{observation_id}",
        response_model=S.ObservationRead,
        responses=errors,
        tags=["observations"],
    )
    def observation(observation_id: UUID, actor: ActorDep, db: SessionDep):
        from .observations.service import owned, read

        return read(db, owned(db, str(observation_id), actor.id))

    @app.delete(
        "/v1/observations/{observation_id}",
        response_model=S.DeleteRead,
        status_code=202,
        responses=errors,
        tags=["observations"],
    )
    def delete_observation(observation_id: UUID, actor: ActorDep, db: SessionDep):
        from .observations.service import delete

        delete(db, str(observation_id), actor.id)
        return {"status": "deletion_pending"}

    @app.post(
        "/v1/observations/{observation_id}/photos",
        response_model=S.PhotoRead,
        status_code=201,
        responses={200: {"model": S.PhotoRead}, **errors},
        tags=["photos"],
    )
    def upload(
        observation_id: UUID,
        actor: ActorDep,
        db: SessionDep,
        response: Response,
        client_photo_id: Annotated[UUID, Form()],
        purpose: Annotated[Literal["primary", "context"], Form()],
        file: Annotated[UploadFile, File()],
    ):
        from .photos.service import upload_photo

        photo, replay = upload_photo(
            db, settings, actor.id, str(observation_id), str(client_photo_id), purpose, file.file
        )
        if replay:
            response.status_code = 200
        return photo

    @app.get(
        "/v1/photos/{photo_id}/content-url", response_model=S.ContentURL, responses=errors, tags=["photos"]
    )
    def content_url(photo_id: UUID, actor: ActorDep, db: SessionDep):
        from .photos.service import get_content_url

        return get_content_url(db, settings, actor.id, str(photo_id))

    @app.get("/v1/photos/{photo_id}/content", responses=errors, tags=["photos"], response_class=FileResponse)
    def content(photo_id: UUID, actor: ActorDep, db: SessionDep, expires: int, signature: str):
        from .photos.service import content_path

        return FileResponse(
            content_path(db, settings, actor.id, str(photo_id), expires, signature),
            media_type="image/jpeg",
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post(
        "/v1/assessments",
        response_model=S.AssessmentRead,
        status_code=202,
        responses={200: {"model": S.AssessmentRead}, **errors},
        tags=["assessments"],
    )
    def create_assessment(
        body: S.AssessmentCreate,
        actor: ActorDep,
        db: SessionDep,
        response: Response,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ):
        from .assessments.service import create

        item, replay = create(db, settings, actor.id, str(idempotency_key), body)
        if replay:
            response.status_code = 200
            response.headers["Idempotency-Replayed"] = "true"
        return item

    @app.get(
        "/v1/assessments/{assessment_id}",
        response_model=S.AssessmentRead,
        responses=errors,
        tags=["assessments"],
    )
    def assessment(assessment_id: UUID, actor: ActorDep, db: SessionDep):
        from .assessments.service import owned

        return owned(db, str(assessment_id), actor.id)

    @app.post(
        "/v1/assessments/{assessment_id}/feedback",
        response_model=S.FeedbackRead,
        status_code=201,
        responses=errors,
        tags=["assessments"],
    )
    def feedback(assessment_id: UUID, body: S.FeedbackCreate, actor: ActorDep, db: SessionDep):
        from .assessments.service import feedback as save_feedback

        return save_feedback(db, str(assessment_id), actor.id, body)

    return app
