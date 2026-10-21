from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

import jwt
from agrovision.errors import APIError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    id: str
    display_name: str | None = None


def actor_id(issuer: str, subject: str) -> str:
    return str(uuid5(NAMESPACE_URL, issuer + "\0" + subject))


def create_dev_token(settings, subject: str, hours: int = 24):
    if settings.environment == "production":
        raise ValueError("Development credentials are disabled")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "iss": "agrovision-development",
            "aud": "agrovision-mobile",
            "iat": now,
            "exp": now + timedelta(hours=hours),
        },
        settings.dev_token_secret,
        algorithm="HS256",
    )


def current_actor(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise APIError(401, "authentication_required", "Войдите в приложение.")
    settings = request.app.state.settings
    try:
        unverified = jwt.decode(credentials.credentials, options={"verify_signature": False})
        development_token = (
            settings.environment != "production" and unverified.get("iss") == "agrovision-development"
        )
        if development_token:
            payload = jwt.decode(
                credentials.credentials,
                settings.dev_token_secret,
                algorithms=["HS256"],
                audience="agrovision-mobile",
                issuer="agrovision-development",
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        else:
            if request.app.state.jwks is None or not settings.oidc_issuer:
                raise jwt.InvalidTokenError("OIDC is not configured")
            signing = request.app.state.jwks.get_signing_key_from_jwt(credentials.credentials)
            payload = jwt.decode(
                credentials.credentials,
                signing.key,
                algorithms=["RS256"],
                audience=settings.oidc_audience,
                issuer=settings.oidc_issuer,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        if not isinstance(payload["sub"], str) or not payload["sub"]:
            raise jwt.InvalidTokenError("Invalid subject")
    except jwt.ExpiredSignatureError:
        raise APIError(401, "session_expired", "Сессия истекла. Войдите снова.") from None
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise APIError(401, "authentication_required", "Сессия недействительна.") from None
    return Actor(
        actor_id(payload["iss"], payload["sub"]),
        payload.get("name") if isinstance(payload.get("name"), str) else None,
    )
