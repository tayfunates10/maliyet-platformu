"""Authenticated actor and organization-role resolution.

Raw bearer tokens are never persisted. Sessions store only SHA-256 token digests,
and organization authorization is resolved from server-side membership rows.
Caller input can never choose the authenticated user or membership role.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.models import Base, OrganizationMembership, User

CALCULATION_WRITE_ROLES = frozenset({"owner", "admin", "accountant", "analyst"})
DEFAULT_SESSION_TTL = timedelta(hours=12)


class AuthenticationError(ValueError):
    """Raised when a bearer session cannot authenticate an active user."""


class AuthorizationError(PermissionError):
    """Raised when an authenticated user lacks tenant permission."""


class AuthSession(Base):
    """Opaque server-side session; only the bearer-token digest is persisted."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("length(token_sha256) = 64", name="ck_auth_session_token_sha256_length"),
        Index("ix_auth_session_user_id", "user_id"),
        Index("ix_auth_session_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Identity established exclusively from a valid server-side session."""

    user_id: UUID
    auth_session_id: UUID | None = None


@dataclass(frozen=True)
class ActorContext:
    """Authenticated identity bound to one organization membership."""

    user_id: UUID
    organization_id: UUID
    role: str


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_session(
    session: Session,
    *,
    user_id: UUID,
    ttl: timedelta = DEFAULT_SESSION_TTL,
    now: datetime | None = None,
) -> tuple[AuthSession, str]:
    """Issue a high-entropy opaque token for a known active user."""

    issued_at = now or _now_utc()
    if issued_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if ttl <= timedelta(0):
        raise ValueError("ttl must be positive")

    user = session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise AuthenticationError("active user not found")

    raw_token = secrets.token_urlsafe(32)
    auth_session = AuthSession(
        user_id=user_id,
        token_sha256=_token_digest(raw_token),
        expires_at=issued_at + ttl,
    )
    session.add(auth_session)
    session.flush()
    return auth_session, raw_token


def revoke_session(
    session: Session,
    *,
    auth_session: AuthSession,
    now: datetime | None = None,
) -> None:
    """Revoke a session without retaining or recovering its raw token."""

    revoked_at = now or _now_utc()
    if revoked_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if auth_session.revoked_at is None:
        auth_session.revoked_at = revoked_at
        session.flush()


def revoke_authenticated_session(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    now: datetime | None = None,
) -> None:
    """Revoke exactly the bearer session that authenticated the current request."""

    if identity.auth_session_id is None:
        raise AuthenticationError("authenticated session id missing")
    auth_session = session.get(AuthSession, identity.auth_session_id)
    if auth_session is None or auth_session.user_id != identity.user_id:
        raise AuthenticationError("invalid session")
    revoke_session(session, auth_session=auth_session, now=now)


def authenticate_session(
    session: Session,
    *,
    raw_token: str,
    now: datetime | None = None,
) -> AuthenticatedIdentity:
    """Resolve one active, unexpired, unrevoked bearer session."""

    checked_at = now or _now_utc()
    if checked_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not raw_token:
        raise AuthenticationError("invalid session")

    row = session.execute(
        select(AuthSession.id, AuthSession.user_id)
        .join(User, User.id == AuthSession.user_id)
        .where(
            AuthSession.token_sha256 == _token_digest(raw_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > checked_at,
            User.is_active.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise AuthenticationError("invalid session")
    return AuthenticatedIdentity(user_id=row[1], auth_session_id=row[0])


def resolve_actor_context(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
) -> ActorContext:
    """Bind an authenticated user to a server-side organization membership."""

    membership = session.execute(
        select(OrganizationMembership.user_id, OrganizationMembership.role).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == identity.user_id,
        )
    ).one_or_none()
    if membership is None:
        raise AuthorizationError("organization access denied")
    return ActorContext(
        user_id=membership[0],
        organization_id=organization_id,
        role=membership[1],
    )


def require_calculation_write(actor: ActorContext) -> None:
    """Allow calculation writes only to explicitly authorized membership roles."""

    if actor.role not in CALCULATION_WRITE_ROLES:
        raise AuthorizationError("calculation write access denied")
