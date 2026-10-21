import pytest
from agrovision.app import create_app
from agrovision.assessments.worker import Worker
from agrovision.config import Settings
from agrovision.identity.auth import create_dev_token
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture(scope="session")
def test_database():
    local = Settings()
    parsed = make_url(local.database_url)
    name = "agrovision_test"
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name})
        if not exists:
            conn.execute(text("CREATE DATABASE agrovision_test"))
    admin.dispose()
    url = parsed.set(database=name).render_as_string(hide_password=False)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    return url


@pytest.fixture
def settings(test_database, tmp_path):
    return Settings(
        _env_file=None,
        environment="test",
        database_url=test_database,
        dev_predictor=True,
        dev_token_secret="test-token-secret-not-real-" * 2,
        download_secret="test-photo-secret-not-real-" * 2,
        storage_dir=tmp_path / "photos",
        bundle_dir=tmp_path / "missing",
        lease_seconds=20,
        inference_timeout_seconds=10,
        retry_base_seconds=0,
    )


@pytest.fixture
def app(settings):
    app = create_app(settings)
    with app.state.engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE feedback, idempotency_keys, assessment_jobs, assessments, photos, observations CASCADE"
            )
        )
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def headers(settings):
    return {"Authorization": "Bearer " + create_dev_token(settings, "user-a")}


@pytest.fixture
def other_headers(settings):
    return {"Authorization": "Bearer " + create_dev_token(settings, "user-b")}


@pytest.fixture
def worker(settings):
    worker = Worker(settings)
    yield worker
    worker.close()
