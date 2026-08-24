"""Production database readiness probe regressions."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, text

from app.production_readiness import check_production_readiness


def _test_database_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL")
    if value is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return value


def test_production_readiness_accepts_database_at_repository_head(db_engine: Engine) -> None:
    expected_head = check_production_readiness(_test_database_url())

    with db_engine.connect() as connection:
        current_head = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert current_head == expected_head


def test_production_readiness_rejects_wrong_database_driver() -> None:
    with pytest.raises(RuntimeError, match="must use postgresql\\+psycopg"):
        check_production_readiness("sqlite:///tmp/maliyet.db")


def test_production_readiness_error_does_not_echo_credentials() -> None:
    secret = "super-secret-password"
    with pytest.raises(RuntimeError) as exc_info:
        check_production_readiness(f"postgresql+psycopg://user:{secret}@localhost:99999/maliyet")

    assert secret not in str(exc_info.value)
