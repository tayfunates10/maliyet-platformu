"""Password hashing and local credential authentication tests."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import User
from app.password_auth import (
    PASSWORD_LOCK_DURATION,
    PASSWORD_LOCK_THRESHOLD,
    PasswordAuthenticationError,
    UserCredential,
    authenticate_password,
    create_password_credential,
    hash_password,
    normalize_email,
    verify_password,
)

PASSWORD = "correct horse battery staple"


def _credential_user(db_session: Session, *, suffix: str) -> tuple[User, UserCredential]:
    user = User(email=f"password-{suffix}@example.test", display_name=f"Password {suffix}")
    db_session.add(user)
    db_session.flush()
    credential = create_password_credential(db_session, user_id=user.id, password=PASSWORD)
    return user, credential


def test_scrypt_hash_is_salted_versioned_and_verifiable() -> None:
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert first.startswith("scrypt$v=1$n=32768$r=8$p=3$dklen=64$")
    assert first != second
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong password value", first)
    assert not verify_password(PASSWORD, "sha256$not-accepted")


def test_email_normalization_is_deterministic() -> None:
    assert normalize_email("  USER@Example.COM ") == "user@example.com"
    with pytest.raises(ValueError, match="invalid email"):
        normalize_email("not-an-email")


def test_failed_password_attempts_lock_then_expire(db_session: Session) -> None:
    user, credential = _credential_user(db_session, suffix="lockout")
    now = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)

    for attempt in range(1, PASSWORD_LOCK_THRESHOLD + 1):
        with pytest.raises(PasswordAuthenticationError, match="invalid credentials"):
            authenticate_password(
                db_session,
                email=user.email,
                password="wrong password value",
                now=now,
            )
        assert credential.failed_attempts == attempt

    assert credential.locked_until == now + PASSWORD_LOCK_DURATION

    with pytest.raises(PasswordAuthenticationError, match="invalid credentials"):
        authenticate_password(
            db_session,
            email=user.email,
            password=PASSWORD,
            now=now + timedelta(minutes=1),
        )

    authenticated = authenticate_password(
        db_session,
        email=user.email,
        password=PASSWORD,
        now=now + PASSWORD_LOCK_DURATION + timedelta(seconds=1),
    )
    assert authenticated.id == user.id
    assert credential.failed_attempts == 0
    assert credential.locked_until is None


def test_unknown_user_uses_generic_authentication_error(db_session: Session) -> None:
    with pytest.raises(PasswordAuthenticationError, match="invalid credentials"):
        authenticate_password(
            db_session,
            email="missing@example.test",
            password=PASSWORD,
        )
