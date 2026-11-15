"""Personal email/password accounts with scrypt hashes and signed access tokens."""

import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime, timedelta

import jwt
from agrovision.errors import APIError
from agrovision.models import Account
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

ISSUER = "agrovision-accounts"
AUDIENCE = "agrovision-mobile"
TOKEN_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
MAX_FAILURES = 5
WINDOW_SECONDS = 300


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise APIError(422, "invalid_email", "Укажите корректный email.")
    return email


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2
        )
        return hmac.compare_digest(candidate.hex(), digest)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password("timing-equalizer")


def _check_throttle(throttle: dict, key: str):
    now = time.monotonic()
    attempts = [t for t in throttle.get(key, []) if now - t < WINDOW_SECONDS]
    throttle[key] = attempts
    if len(attempts) >= MAX_FAILURES:
        raise APIError(429, "too_many_attempts", "Слишком много попыток входа. Подождите несколько минут.")


def register(db, email: str, password: str, display_name: str | None) -> Account:
    account = Account(
        email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=(display_name or "").strip() or None,
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise APIError(409, "email_taken", "Аккаунт с таким email уже существует.") from None
    return account


def authenticate(db, throttle: dict, email: str, password: str, client: str) -> Account:
    email = normalize_email(email)
    key = f"{client}|{email}"
    _check_throttle(throttle, key)
    account = db.scalar(select(Account).where(Account.email == email))
    ok = verify_password(password, account.password_hash if account else _DUMMY_HASH)
    if not account or not ok:
        throttle.setdefault(key, []).append(time.monotonic())
        raise APIError(401, "invalid_credentials", "Неверный email или пароль.")
    throttle.pop(key, None)
    return account


def issue_token(secret: str, account: Account) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires = timedelta(days=TOKEN_DAYS)
    claims = {
        "sub": account.id,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + expires,
    }
    if account.display_name:
        claims["name"] = account.display_name
    return jwt.encode(claims, secret, algorithm="HS256"), int(expires.total_seconds())
