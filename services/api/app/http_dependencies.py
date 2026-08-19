"""FastAPI dependencies for database transactions and bearer authentication."""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.auth_context import AuthenticatedIdentity, AuthenticationError, authenticate_session
from app.database import build_engine, build_session_factory

_DATABASE_URL_ENV = "DATABASE_URL"
_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def _session_factory(database_url: str) -> sessionmaker[Session]:
    """Cache the canonical session factory per configured database URL."""

    return build_session_factory(build_engine(database_url))


def get_database_session() -> Iterator[Session]:
    """Provide one request transaction and commit only after a successful response path."""

    database_url = os.environ.get(_DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(f"{_DATABASE_URL_ENV} is required for database-backed endpoints")

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
