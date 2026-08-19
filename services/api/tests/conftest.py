"""Database fixtures for PostgreSQL integration tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from alembic import command

API_ROOT = Path(__file__).resolve().parents[1]


def database_url() -> str:
    """Return the explicit integration-test database URL."""

    value = os.environ.get("TEST_DATABASE_URL")
    if value is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return value


def alembic_config(url: str) -> Config:
    """Build an Alembic config independent of the current working directory."""

    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """Migrate the test database to head and return a disposable engine."""

    url = database_url()
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Run each persistence test in a transaction that is rolled back."""

    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
