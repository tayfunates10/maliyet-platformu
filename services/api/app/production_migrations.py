"""Controlled production database readiness and Alembic migration ceremony."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.database import build_engine
from app.http_dependencies import validate_database_url

_API_ROOT = Path(__file__).resolve().parents[1]
_MIGRATION_LOCK_KEY = 1_296_129_097


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def run_production_migration_ceremony(database_url: str) -> str:
    """Verify readiness, serialize migration ownership, and upgrade to the single head.

    The ceremony is deliberately external to application startup. It accepts only the
    canonical PostgreSQL+psycopg runtime URL, requires a single repository migration
    head, refuses databases already reporting multiple heads, and uses a PostgreSQL
    advisory lock so two deployment actors cannot migrate concurrently.
    """

    validated_url = validate_database_url(database_url)
    config = _alembic_config(validated_url)
    script = ScriptDirectory.from_config(config)
    repository_heads = tuple(script.get_heads())
    if len(repository_heads) != 1:
        raise RuntimeError("production migration requires exactly one repository head")
    target_head = repository_heads[0]

    engine = build_engine(validated_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _MIGRATION_LOCK_KEY},
            ).scalar_one()
            connection.commit()
            if acquired is not True:
                raise RuntimeError("another production migration ceremony is active")

            try:
                current_heads = tuple(MigrationContext.configure(connection).get_current_heads())
                connection.commit()
                if len(current_heads) > 1:
                    raise RuntimeError("database reports multiple Alembic heads")

                command.upgrade(config, "head")

                migrated_heads = tuple(MigrationContext.configure(connection).get_current_heads())
                connection.commit()
                if migrated_heads != (target_head,):
                    raise RuntimeError("database did not reach the expected Alembic head")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _MIGRATION_LOCK_KEY},
                )
                connection.commit()
    finally:
        engine.dispose()

    return target_head
