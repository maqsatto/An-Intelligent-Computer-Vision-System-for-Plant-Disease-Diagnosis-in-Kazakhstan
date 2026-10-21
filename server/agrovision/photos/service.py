import hashlib
import hmac
import time
import warnings
from datetime import UTC, datetime, timedelta
from io import BytesIO
from threading import BoundedSemaphore
from uuid import uuid4

from agrovision.errors import APIError
from agrovision.models import Observation, Photo
from agrovision.observations.service import owned
from agrovision.photos.storage import LocalImageStore
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

# Must match the admitted runtime's allocation guards; limits do not change accepted pixel transforms.
MAX_PREPROCESS_PIXELS = 4_000_000
MAX_PREPROCESS_DIMENSION = 16_384


def normalize_image(content, max_pixels):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise APIError(415, "unsupported_media_type", "Поддерживаются JPEG и PNG.")
                if image.width * image.height > max_pixels:
                    raise APIError(413, "image_too_large", "Фотография превышает допустимое число пикселей.")
                scale = 256 / min(image.width, image.height)
                projected = (int(image.width * scale), int(image.height * scale))
                if (
                    projected[0] * projected[1] > MAX_PREPROCESS_PIXELS
                    or max(projected) > MAX_PREPROCESS_DIMENSION
                ):
                    raise APIError(
                        413, "image_too_large", "Слишком вытянутый кадр. Измените кадрирование листа."
                    )
                if getattr(image, "n_frames", 1) != 1:
                    raise APIError(415, "unsupported_media_type", "Выберите одно неподвижное изображение.")
                image.load()
                converted = ImageOps.exif_transpose(image).convert("RGB")
                output = BytesIO()
                converted.save(output, format="JPEG", quality=95, subsampling=0)
                return output.getvalue(), converted.width, converted.height
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise APIError(413, "image_too_large", "Слишком большое изображение.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise APIError(
            422, "image_decode_failed", "Не удалось прочитать фотографию. Выберите другой файл."
        ) from None


upload_slots = BoundedSemaphore(2)


def upload_photo(db, settings, owner_id, observation_id, client_photo_id, purpose, stream):
    # Bound the whole decoding/upload lifetime, not only decoder calls with retained byte buffers.
    if not upload_slots.acquire(blocking=False):
        raise APIError(
            429, "rate_limited", "Сервер обрабатывает другие фотографии. Повторите через несколько секунд."
        )
    try:
        return _upload_photo(db, settings, owner_id, observation_id, client_photo_id, purpose, stream)
    finally:
        upload_slots.release()


def _upload_photo(db, settings, owner_id, observation_id, client_photo_id, purpose, stream):
    owned(db, observation_id, owner_id)
    db.commit()
    content = stream.read(settings.max_image_bytes + 1)
    if len(content) > settings.max_image_bytes:
        raise APIError(413, "image_too_large", "Файл должен быть не больше 10 MiB.")
    input_hash = hashlib.sha256(content).hexdigest()
    normalized, width, height = normalize_image(content, settings.max_image_pixels)
    owned(db, observation_id, owner_id, lock=True)
    photo = db.scalar(
        select(Photo)
        .where(Photo.owner_id == owner_id, Photo.client_photo_id == client_photo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = db.scalar(select(func.clock_timestamp()))
    replay = photo is not None
    if photo is not None:
        if (photo.observation_id, photo.input_sha256, photo.purpose) != (observation_id, input_hash, purpose):
            raise APIError(409, "idempotency_conflict", "Этот снимок уже загружен с другими данными.")
        if photo.status == "ready":
            db.commit()
            return photo, True
        if photo.status == "pending" and photo.upload_lease_until and photo.upload_lease_until > now:
            raise APIError(409, "photo_not_ready", "Предыдущая загрузка выполняется. Повторите позже.")
    else:
        photo = Photo(
            id=str(uuid4()),
            owner_id=owner_id,
            observation_id=observation_id,
            client_photo_id=client_photo_id,
            purpose=purpose,
            input_sha256=input_hash,
            sha256=hashlib.sha256(normalized).hexdigest(),
            media_type="image/jpeg",
            width=width,
            height=height,
        )
        db.add(photo)
    token, object_key = str(uuid4()), str(uuid4()) + ".jpg"
    photo.status, photo.object_key, photo.blob_deleted_at = "pending", object_key, None
    photo.upload_token, photo.upload_lease_until = token, now + timedelta(seconds=60)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # owner+client UUID races across different observations must not expose or replace a reservation.
        existing = db.scalar(
            select(Photo).where(Photo.owner_id == owner_id, Photo.client_photo_id == client_photo_id)
        )
        if existing and (existing.observation_id, existing.input_sha256, existing.purpose) != (
            observation_id,
            input_hash,
            purpose,
        ):
            raise APIError(
                409, "idempotency_conflict", "Идентификатор снимка занят другими данными."
            ) from None
        raise APIError(409, "photo_not_ready", "Загрузка уже выполняется. Повторите позже.") from None
    photo_id = photo.id
    store = LocalImageStore(settings.storage_dir)
    try:
        store.put(object_key, normalized)
    except OSError:
        db.rollback()
        owned(db, observation_id, owner_id, lock=True, include_deleted=True)
        current = db.scalar(
            select(Photo)
            .where(Photo.id == photo_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current.status == "pending" and current.upload_token == token:
            current.status, current.upload_token, current.upload_lease_until = "failed", None, None
        db.commit()
        store.delete(object_key)
        raise APIError(503, "storage_unavailable", "Хранилище временно недоступно.") from None
    try:
        owned(db, observation_id, owner_id, lock=True)
        current = db.scalar(
            select(Photo)
            .where(Photo.id == photo_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = db.scalar(select(func.clock_timestamp()))
        if (
            current.status != "pending"
            or current.upload_token != token
            or not current.upload_lease_until
            or current.upload_lease_until <= now
        ):
            raise APIError(409, "photo_not_ready", "Предыдущая загрузка устарела. Повторите отправку.")
        current.status, current.upload_token, current.upload_lease_until = "ready", None, None
        db.commit()
        return current, replay
    except Exception:
        db.rollback()
        store.delete(object_key)
        raise


def owned_photo(db, photo_id, owner_id):
    photo = db.scalar(
        select(Photo)
        .join(Observation, Observation.id == Photo.observation_id)
        .where(
            Photo.id == photo_id,
            Photo.owner_id == owner_id,
            Observation.owner_id == owner_id,
            Observation.deleted_at.is_(None),
            Photo.status == "ready",
        )
    )
    if photo is None:
        raise APIError(404, "not_found", "Фотография не найдена.")
    return photo


def sign(settings, owner_id, photo_id, expiry):
    payload = f"{owner_id}:{photo_id}:{expiry}".encode()
    return hmac.new(settings.download_secret.encode(), payload, hashlib.sha256).hexdigest()


def get_content_url(db, settings, owner_id, photo_id):
    owned_photo(db, photo_id, owner_id)
    expiry = int(time.time()) + settings.download_ttl_seconds
    return {
        "url": f"/v1/photos/{photo_id}/content?expires={expiry}&signature={sign(settings, owner_id, photo_id, expiry)}",
        "expires_at": datetime.fromtimestamp(expiry, UTC),
    }


def content_path(db, settings, owner_id, photo_id, expiry, signature):
    photo = owned_photo(db, photo_id, owner_id)
    if expiry < time.time() or not hmac.compare_digest(signature, sign(settings, owner_id, photo_id, expiry)):
        raise APIError(404, "not_found", "Ссылка на фотографию недействительна.")
    path = LocalImageStore(settings.storage_dir).path(photo.object_key)
    if not path.is_file():
        raise APIError(503, "storage_unavailable", "Фотография временно недоступна.")
    return path
