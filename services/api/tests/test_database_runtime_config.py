"""Fail-closed runtime database configuration tests."""

import pytest

from app.http_dependencies import get_database_url, validate_database_url


def test_validate_database_url_accepts_canonical_postgresql_psycopg() -> None:
    value = "postgresql+psycopg://app:secret@db.internal:5432/maliyet"
    assert validate_database_url(value) == value


def test_validate_database_url_accepts_postgresql_alias() -> None:
    value = "postgresql://app:secret@db.internal:5432/maliyet"
    assert validate_database_url(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "sqlite:///tmp/maliyet.db",
        "mysql://app:secret@db.internal/maliyet",
        "postgresql+asyncpg://app:secret@db.internal/maliyet",
    ],
)
def test_validate_database_url_rejects_noncanonical_drivers(value: str) -> None:
    with pytest.raises(RuntimeError, match="must use PostgreSQL with psycopg"):
        validate_database_url(value)


def test_validate_database_url_rejects_missing_database_name() -> None:
    with pytest.raises(RuntimeError, match="must select a database"):
        validate_database_url("postgresql+psycopg://app:secret@db.internal")


def test_validate_database_url_rejects_malformed_value_without_echoing_secret() -> None:
    secret = "do-not-echo"
    with pytest.raises(RuntimeError, match="DATABASE_URL is invalid") as exc_info:
        validate_database_url(f"postgresql://app:{secret}@[bad-host/maliyet")
    assert secret not in str(exc_info.value)


def test_get_database_url_reads_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    first = "postgresql+psycopg://app:one@db-a.internal/maliyet"
    second = "postgresql+psycopg://app:two@db-b.internal/maliyet"

    monkeypatch.setenv("DATABASE_URL", first)
    assert get_database_url() == first

    monkeypatch.setenv("DATABASE_URL", second)
    assert get_database_url() == second


def test_get_database_url_fails_closed_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        get_database_url()
