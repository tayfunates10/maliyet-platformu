"""Fail-closed production readiness probe for database connectivity and schema parity."""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.database import build_engine
from app.http_dependencies import validate_database_url
from app.production_migrations import _alembic_config

_DATABASE_URL_ENV = "DATABASE_URL"


def _require_single_head(heads: Sequence[str], *, source: str) -> str:
    """Return the only head or fail closed when migration state is ambiguous."""

    if len(heads) != 1:
        raise RuntimeError(f"production readiness requires exactly one {source} Alembic head")
    return heads[0]


def check_production_readiness(database_url: str) -> str:
    """Verify PostgreSQL connectivity and exact repository/database Alembic head parity.

    This probe is intentionally read-only. It never runs migrations and never treats
    process liveness as database readiness. Deploy automation must run the explicit
    production migration ceremony first, then use this probe before routing traffic.
    """

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


def main() -> int:
    """Run the readiness probe as a secret-safe deployment command."""

    database_url = os.environ.get(_DATABASE_URL_ENV)
    if database_url is None:
        raise RuntimeError(f"{_DATABASE_URL_ENV} is required for production readiness")
    head = check_production_readiness(database_url)
    print(f"production readiness: ok ({head})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
