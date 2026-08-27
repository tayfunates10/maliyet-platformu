"""Password credential storage and verification using memory-hard scrypt."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.auth_context import AuthSession, issue_session
from app.models import Base, User

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256
PASSWORD_LOCK_THRESHOLD = 5
PASSWORD_LOCK_DURATION = timedelta(minutes=15)

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3
SCRYPT_DKLEN = 64
SCRYPT_SALT_BYTES = 16
SCRYPT_MAXMEM = 64 * 1024 * 1024
_PASSWORD_HASH_VERSION = "1"

# Fixed dummy verifier for unknown-user timing equalization. It is not a credential.
_DUMMY_HASH = (
    "scrypt$v=1$n=32768$r=8$p=3$dklen=64$"
    "bWFsaXlldC1kdW1teS1zYWx0$"
    "3hZKyaVfW3XBCgyx7oFiTtkeG8-UxDr-r5IBHPV9c8_XLQ3gFywujs8VdVaRztTji9cVvS397BHmocPzlzO52g=="
)


class PasswordAuthenticationError(ValueError):
    """Raised when a password credential cannot authenticate."""


class UserCredential(Base):
    """One password credential row per local-password user."""

    __tablename__ = "user_credentials"
    __table_args__ = (
        CheckConstraint("failed_attempts >= 0", name="ck_user_credential_failed_attempts"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _now_utc() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    """Normalize login identifiers without guessing provider-specific aliases."""

    normalized = email.strip().casefold()
    if not normalized or len(normalized) > 320 or "@" not in normalized:
        raise ValueError("invalid email")
    local_part, domain = normalized.rsplit("@", 1)
    if not local_part or not domain or "." not in domain:
        raise ValueError("invalid email")
    return normalized


def validate_password(password: str) -> None:
    """Apply length-only policy; composition rules are intentionally avoided."""

    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"password length must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH}"
        )
    if len(password.encode("utf-8")) > 1024:
        raise ValueError("password UTF-8 representation is too long")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)


def _derive(password: str, *, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=SCRYPT_MAXMEM,
        dklen=dklen,
    )


def hash_password(password: str) -> str:
    """Create a versioned, salted scrypt password hash."""

    validate_password(password)
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    derived = _derive(
        password,
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt$v={_PASSWORD_HASH_VERSION}$n={SCRYPT_N}$r={SCRYPT_R}$p={SCRYPT_P}$"
        f"dklen={SCRYPT_DKLEN}${_b64encode(salt)}${_b64encode(derived)}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify one versioned password hash in constant-time at the digest boundary."""

    try:
        parts = encoded_hash.split("$")
        if len(parts) != 8 or parts[0] != "scrypt" or parts[1] != f"v={_PASSWORD_HASH_VERSION}":
            return False
        n = int(parts[2].removeprefix("n="))
        r = int(parts[3].removeprefix("r="))
        p = int(parts[4].removeprefix("p="))
        dklen = int(parts[5].removeprefix("dklen="))
        salt = _b64decode(parts[6])
        expected = _b64decode(parts[7])
        if (
            n != SCRYPT_N
            or r != SCRYPT_R
            or p != SCRYPT_P
            or dklen != SCRYPT_DKLEN
            or len(salt) < SCRYPT_SALT_BYTES
            or len(expected) != SCRYPT_DKLEN
        ):
            return False
        actual = _derive(password, salt=salt, n=n, r=r, p=p, dklen=dklen)
    except ValueError, TypeError:
        return False
    return hmac.compare_digest(actual, expected)


def create_password_credential(
    session: Session,
    *,
    user_id: UUID,
    password: str,
) -> UserCredential:
    """Create one local-password credential for an existing active user."""

    existing = session.get(UserCredential, user_id)
    if existing is not None:
        raise ValueError("password credential already exists")
    user = session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise ValueError("active user not found")

    credential = UserCredential(user_id=user_id, password_hash=hash_password(password))
    session.add(credential)
    session.flush()
    return credential


def authenticate_password(
    session: Session,
    *,
    email: str,
    password: str,
    now: datetime | None = None,
) -> User:
    """Authenticate a local-password user and persist bounded lockout state."""

    checked_at = now or _now_utc()
    if checked_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    normalized = normalize_email(email)
    row = session.execute(
        select(User, UserCredential)
        .join(UserCredential, UserCredential.user_id == User.id)
        .where(User.email == normalized, User.is_active.is_(True))
        .with_for_update()
    ).one_or_none()

    if row is None:
        verify_password(password, _DUMMY_HASH)
        raise PasswordAuthenticationError("invalid credentials")

    user = cast(User, row[0])
    credential = cast(UserCredential, row[1])
    valid = verify_password(password, credential.password_hash)
    if credential.locked_until is not None and credential.locked_until > checked_at:
        raise PasswordAuthenticationError("invalid credentials")

    if credential.locked_until is not None and credential.locked_until <= checked_at:
        credential.failed_attempts = 0
        credential.locked_until = None

    if not valid:
        credential.failed_attempts += 1
        if credential.failed_attempts >= PASSWORD_LOCK_THRESHOLD:
            credential.locked_until = checked_at + PASSWORD_LOCK_DURATION
        session.flush()
        raise PasswordAuthenticationError("invalid credentials")

    credential.failed_attempts = 0
    credential.locked_until = None
    session.flush()
    return user


def authenticate_password_and_issue_session(
    session: Session,
    *,
    email: str,
    password: str,
    now: datetime | None = None,
) -> tuple[User, AuthSession, str]:
    """Authenticate a password and issue the existing opaque bearer session."""

    user = authenticate_password(session, email=email, password=password, now=now)
    auth_session, raw_token = issue_session(session, user_id=user.id, now=now)
    return user, auth_session, raw_token
