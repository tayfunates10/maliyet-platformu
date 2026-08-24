"""Production database migration ceremony regressions."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, create_engine, text

from app.production_migrations import (
    _MIGRATION_LOCK_KEY,
    _alembic_config,
    run_production_migration_ceremony,
)


def _test_database_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL")
    if value is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return value


def test_alembic_config_preserves_percent_encoded_credentials() -> None:
    database_url = "postgresql+psycopg://user:p%40ss@db.example.test:5432/maliyet"

    config = _alembic_config(database_url)

    assert config.get_main_option("sqlalchemy.url") == database_url


def test_production_migration_ceremony_is_idempotent_at_head(db_engine: Engine) -> None:
    target_head = run_production_migration_ceremony(_test_database_url())

    with db_engine.connect() as connection:
        current_head = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert current_head == target_head


def test_production_migration_ceremony_refuses_concurrent_actor(db_engine: Engine) -> None:
    lock_engine = create_engine(_test_database_url(), pool_pre_ping=True)
    try:
        with lock_engine.connect() as connection:
            locked = connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _MIGRATION_LOCK_KEY},
            ).scalar_one()
            connection.commit()
            assert locked is True

            with pytest.raises(
                RuntimeError,
                match="another production migration ceremony is active",
            ):
                run_production_migration_ceremony(_test_database_url())

            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": _MIGRATION_LOCK_KEY},
            )
            connection.commit()
    finally:
        lock_engine.dispose()
