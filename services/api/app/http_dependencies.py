"""FastAPI dependencies for database transactions and bearer authentication."""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from app.auth_context import AuthenticatedIdentity, AuthenticationError, authenticate_session
from app.database import build_engine, build_session_factory

_DATABASE_URL_ENV = "DATABASE_URL"
_DATABASE_DRIVER = "postgresql+psycopg"
_bearer = HTTPBearer(auto_error=False)


def validate_database_url(database_url: str) -> str:
    """Validate the canonical PostgreSQL runtime URL without exposing credentials.

    Maliyet Platformu's persistence and concurrency contracts are PostgreSQL-specific.
    The project pins psycopg 3, so accepting SQLAlchemy's bare ``postgresql`` alias
    could silently select an unavailable or unintended DBAPI driver.
    """

    value = database_url.strip()
    if not value:
        raise RuntimeError(f"{_DATABASE_URL_ENV} is required for database-backed endpoints")

    try:
        parsed = make_url(value)
    except ArgumentError as exc:
        raise RuntimeError(f"{_DATABASE_URL_ENV} is invalid") from exc

    if parsed.drivername != _DATABASE_DRIVER:
        raise RuntimeError(f"{_DATABASE_URL_ENV} must use postgresql+psycopg")
    if not parsed.database:
        raise RuntimeError(f"{_DATABASE_URL_ENV} must select a database")

    return value


def get_database_url() -> str:
    """Resolve and validate the database URL at request time."""

    value = os.environ.get(_DATABASE_URL_ENV)
    if value is None:
        raise RuntimeError(f"{_DATABASE_URL_ENV} is required for database-backed endpoints")
    return validate_database_url(value)


@lru_cache(maxsize=4)
def _session_factory(database_url: str) -> sessionmaker[Session]:
    """Cache the canonical session factory per validated database URL."""

    return build_session_factory(build_engine(database_url))


def get_database_session() -> Iterator[Session]:
    """Provide one request transaction and commit only after a successful response path."""

    database_url = get_database_url()
    session = _session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_authenticated_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    session: Annotated[Session, Depends(get_database_session)],
) -> AuthenticatedIdentity:
    """Resolve the actor only from an opaque bearer session token."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return authenticate_session(session, raw_token=credentials.credentials)
    except AuthenticationError as exc:
        raise _unauthorized() from exc
