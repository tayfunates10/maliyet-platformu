"""PostgreSQL tests for opaque sessions and tenant-scoped actor resolution."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth_context import (
    AuthenticationError,
    AuthorizationError,
    authenticate_session,
    issue_session,
    require_calculation_write,
    resolve_actor_context,
    revoke_session,
)
from app.models import Organization, OrganizationMembership, User


def _user_and_org(db_session: Session, *, role: str = "owner") -> tuple[User, Organization]:
    user = User(email=f"auth-{role}@example.test", display_name=f"Auth {role}")
    organization = Organization(slug=f"auth-{role}-org", legal_name=f"Auth {role} Org")
    db_session.add_all([user, organization])
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
        )
    )
    db_session.flush()
    return user, organization


def test_session_stores_only_token_digest_and_authenticates_active_user(
    db_session: Session,
) -> None:
    user, _ = _user_and_org(db_session)
    now = datetime(2026, 8, 19, 16, 0, tzinfo=UTC)

    auth_session, raw_token = issue_session(db_session, user_id=user.id, now=now)

    assert raw_token != auth_session.token_sha256
    assert auth_session.token_sha256 == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    assert len(auth_session.token_sha256) == 64
    identity = authenticate_session(db_session, raw_token=raw_token, now=now)
    assert identity.user_id == user.id


def test_expired_revoked_and_inactive_sessions_fail_closed(db_session: Session) -> None:
    user, _ = _user_and_org(db_session, role="admin")
    now = datetime(2026, 8, 19, 16, 0, tzinfo=UTC)

    expired, expired_token = issue_session(
        db_session,
        user_id=user.id,
        ttl=timedelta(minutes=1),
        now=now,
    )
    assert expired.expires_at > now
    with pytest.raises(AuthenticationError, match="invalid session"):
        authenticate_session(
            db_session,
            raw_token=expired_token,
            now=now + timedelta(minutes=2),
        )

    active, active_token = issue_session(db_session, user_id=user.id, now=now)
    revoke_session(db_session, auth_session=active, now=now + timedelta(seconds=1))
    with pytest.raises(AuthenticationError, match="invalid session"):
        authenticate_session(db_session, raw_token=active_token, now=now + timedelta(seconds=2))

    inactive_session, inactive_token = issue_session(db_session, user_id=user.id, now=now)
    assert inactive_session.user_id == user.id
    user.is_active = False
    db_session.flush()
    with pytest.raises(AuthenticationError, match="invalid session"):
        authenticate_session(db_session, raw_token=inactive_token, now=now + timedelta(seconds=1))


def test_actor_context_comes_from_membership_and_viewer_cannot_write(db_session: Session) -> None:
    owner, owner_org = _user_and_org(db_session, role="owner")
    owner_session, owner_token = issue_session(db_session, user_id=owner.id)
    assert owner_session.user_id == owner.id
    owner_identity = authenticate_session(db_session, raw_token=owner_token)
    owner_actor = resolve_actor_context(
        db_session,
        identity=owner_identity,
        organization_id=owner_org.id,
    )
    assert owner_actor.user_id == owner.id
    assert owner_actor.role == "owner"
    require_calculation_write(owner_actor)

    viewer, viewer_org = _user_and_org(db_session, role="viewer")
    _, viewer_token = issue_session(db_session, user_id=viewer.id)
    viewer_identity = authenticate_session(db_session, raw_token=viewer_token)
    viewer_actor = resolve_actor_context(
        db_session,
        identity=viewer_identity,
        organization_id=viewer_org.id,
    )
    with pytest.raises(AuthorizationError, match="write access denied"):
        require_calculation_write(viewer_actor)

    with pytest.raises(AuthorizationError, match="organization access denied"):
        resolve_actor_context(
            db_session,
            identity=owner_identity,
            organization_id=viewer_org.id,
        )
