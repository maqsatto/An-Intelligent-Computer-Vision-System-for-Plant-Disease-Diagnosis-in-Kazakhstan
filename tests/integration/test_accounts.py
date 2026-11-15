from uuid import uuid4

import pytest
from agrovision.config import Settings


def _email():
    return f"{uuid4().hex[:12]}@example.com"


def _register(client, email=None, password="correct-horse-1", name="Анна"):
    return client.post(
        "/v1/auth/register",
        json={"email": email or _email(), "password": password, "display_name": name},
    )


def test_register_login_and_me(client):
    email = _email()
    created = _register(client, email.upper())
    assert created.status_code == 201
    assert created.json()["account"]["display_name"] == "Анна"

    login = client.post("/v1/auth/login", json={"email": email, "password": "correct-horse-1"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] != login.json()["account"]["id"]  # actor id is namespaced by issuer
    assert me.json()["display_name"] == "Анна"


def test_duplicate_email_and_weak_password(client):
    email = _email()
    assert _register(client, email).status_code == 201
    assert _register(client, email).status_code == 409
    assert _register(client, password="short").status_code == 422
    assert _register(client, email="not-an-email").status_code == 422


def test_wrong_password_and_unknown_user_are_indistinguishable(client):
    email = _email()
    _register(client, email)
    wrong = client.post("/v1/auth/login", json={"email": email, "password": "nope"})
    unknown = client.post("/v1/auth/login", json={"email": _email(), "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "invalid_credentials"


def test_login_throttle(client):
    email = _email()
    _register(client, email)
    codes = [
        client.post("/v1/auth/login", json={"email": email, "password": "bad"}).status_code for _ in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    # Even the right password is refused while throttled.
    assert (
        client.post("/v1/auth/login", json={"email": email, "password": "correct-horse-1"}).status_code == 429
    )


def test_password_is_not_stored_in_clear(client, app):
    from sqlalchemy import text

    email = _email()
    _register(client, email, password="very-secret-pass")
    with app.state.engine.connect() as conn:
        stored = conn.scalar(text("SELECT password_hash FROM accounts WHERE email=:e"), {"e": email})
    assert stored.startswith("scrypt$") and "very-secret-pass" not in stored


def test_tampered_account_token_rejected(client):
    token = _register(client).json()["access_token"]
    bad = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_production_requires_auth_secret_or_oidc(tmp_path):
    base = dict(
        _env_file=None,
        environment="production",
        download_secret="x" * 40,
        storage_dir=tmp_path,
    )
    with pytest.raises(ValueError):
        Settings(**base)
    assert Settings(**base, auth_secret="y" * 40).account_secret == "y" * 40
    with pytest.raises(ValueError):
        Settings(**base, auth_secret="short")
