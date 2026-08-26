"""Fail-closed production readiness for schema and regulatory baseline parity."""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.baseline_loader import verify_tr_2026_baseline_state
from app.database import build_engine
from app.http_dependencies import validate_database_url
from app.production_migrations import _alembic_config

_DATABASE_URL_ENV = "DATABASE_URL"


def _require_single_head(heads: Sequence[str], *, source: str) -> str:
    """Return the only head or fail closed when migration state is ambiguous."""

    if len(heads) != 1:
        raise RuntimeError(f"production readiness requires exactly one {source} Alembic head")
    return heads[0]


def check_production_schema_readiness(database_url: str) -> str:
    """Verify PostgreSQL connectivity and exact repository/database Alembic head parity."""

    validated_url = validate_database_url(database_url)
    config = _alembic_config(validated_url)
    repository_head = _require_single_head(
        tuple(ScriptDirectory.from_config(config).get_heads()),
        source="repository",
    )

    engine = build_engine(validated_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            database_head = _require_single_head(
                tuple(MigrationContext.configure(connection).get_current_heads()),
                source="database",
            )
            connection.rollback()
    finally:
        engine.dispose()

    if database_head != repository_head:
        raise RuntimeError("database Alembic head does not match repository head")
    return repository_head


def check_production_readiness(database_url: str) -> str:
    """Verify schema parity plus exact curated TR-2026 regulatory baseline state.

    This probe is read-only. It never runs migrations, loads rules, repairs drift or
    treats process liveness as database readiness. Deployment must run the explicit
    migration and regulatory-baseline ceremonies before this traffic gate.
    """

    validated_url = validate_database_url(database_url)
    repository_head = check_production_schema_readiness(validated_url)
    engine = build_engine(validated_url)
    try:
        with engine.connect() as connection:
            with Session(bind=connection, expire_on_commit=False) as session:
                verify_tr_2026_baseline_state(session)
            connection.rollback()
    finally:
        engine.dispose()
    return repository_head


def main() -> int:
    """Run the readiness probe as a secret-safe deployment command."""

    database_url = os.environ.get(_DATABASE_URL_ENV)
    if database_url is None:
        raise RuntimeError(f"{_DATABASE_URL_ENV} is required for production readiness")
    head = check_production_readiness(database_url)
    print(f"production readiness: ok ({head}; TR-2026 baseline verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
