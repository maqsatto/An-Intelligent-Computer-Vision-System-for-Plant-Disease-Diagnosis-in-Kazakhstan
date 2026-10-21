from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_migrations_roundtrip_and_schema_guards(test_database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_database.replace("%", "%%"))
    command.downgrade(config, "base")
    engine = create_engine(test_database)
    assert "observations" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    tables = set(inspect(engine).get_table_names())
    assert {"observations", "photos", "assessments", "assessment_jobs", "idempotency_keys"} <= tables
    with engine.connect() as conn:
        triggers = set(conn.scalars(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")))
        assert {"assessment_immutable", "photo_immutable"} <= triggers
    engine.dispose()
