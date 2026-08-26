"""Explicit production ceremony for the curated TR-2026 regulatory baseline."""

from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.baseline_loader import BaselineLoadResult, load_tr_2026_baseline
from app.database import build_engine
from app.http_dependencies import validate_database_url
from app.production_readiness import check_production_schema_readiness

_DATABASE_URL_ENV = "DATABASE_URL"
_BASELINE_LOCK_KEY = 1_296_129_098


def run_production_baseline_ceremony(database_url: str) -> BaselineLoadResult:
    """Load the reviewed regulatory baseline only after exact schema readiness.

    The operation is explicit, idempotent and serialized with a PostgreSQL advisory
    lock. Source captures are hash-verified by the baseline loader and any persisted
    drift fails closed inside one transaction.
    """

    validated_url = validate_database_url(database_url)
    check_production_schema_readiness(validated_url)
    engine = build_engine(validated_url)
    try:
        with engine.connect() as connection:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _BASELINE_LOCK_KEY},
            ).scalar_one()
            connection.commit()
            if acquired is not True:
                raise RuntimeError("another regulatory baseline ceremony is active")

            try:
                with Session(bind=connection, expire_on_commit=False) as session:
                    with session.begin():
                        result = load_tr_2026_baseline(session)
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _BASELINE_LOCK_KEY},
                )
                connection.commit()
    finally:
        engine.dispose()

    return result


def main() -> int:
    """Run the production baseline ceremony without exposing database credentials."""

    database_url = os.environ.get(_DATABASE_URL_ENV)
    if database_url is None:
        raise RuntimeError(f"{_DATABASE_URL_ENV} is required for regulatory baseline loading")
    result = run_production_baseline_ceremony(database_url)
    print(
        "production regulatory baseline: ok "
        f"({result.sources} sources, {result.definitions} definitions, {result.versions} versions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
