"""Issue, authenticate, list and revoke tenant-scoped partner API credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, OrganizationMembership
from app.partner_api_models import PartnerApiCredential

PARTNER_API_TOKEN_PREFIX = "mp_live_"
PARTNER_API_TOKEN_ENTROPY_BYTES = 32
PARTNER_API_TOKEN_MAX_LENGTH = 96
PARTNER_API_MANAGEMENT_ROLES = frozenset({"owner", "admin"})
PARTNER_API_LIST_MAX_LIMIT = 100


class PartnerApiCredentialError(ValueError):
    """Base credential lifecycle error."""


class PartnerApiAuthorizationError(PartnerApiCredentialError):
    """Raised when an actor lacks credential-management authority."""


class PartnerApiAuthenticationError(PartnerApiCredentialError):
    """Raised for unknown, malformed or revoked partner tokens."""


@dataclass(frozen=True)
class IssuedPartnerApiCredential:
    """One-time raw token plus persisted credential metadata."""

    credential: PartnerApiCredential
    raw_token: str


def _digest(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


def _require_manager(session: Session, *, organization_id: UUID, user_id: UUID) -> None:
    role = session.scalar(
        select(OrganizationMembership.role).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if role not in PARTNER_API_MANAGEMENT_ROLES:
        raise PartnerApiAuthorizationError("partner API credential management denied")


def issue_partner_api_credential(
    session: Session,
    *,
    organization_id: UUID,
    created_by_user_id: UUID,
    name: str,
) -> IssuedPartnerApiCredential:
    """Create one credential and return its raw token exactly once."""

    normalized_name = name.strip()
    if not normalized_name or len(normalized_name) > 160:
        raise PartnerApiCredentialError("credential name must be between 1 and 160 characters")
    _require_manager(
        session,
        organization_id=organization_id,
        user_id=created_by_user_id,
    )

    raw_token = PARTNER_API_TOKEN_PREFIX + token_urlsafe(PARTNER_API_TOKEN_ENTROPY_BYTES)
    token_sha256 = _digest(raw_token)
    credential = PartnerApiCredential(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        name=normalized_name,
        token_prefix=raw_token[:16],
        token_sha256=token_sha256,
    )
    session.add(credential)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=created_by_user_id,
            event_type="partner_api.credential_issued",
            entity_type="partner_api_credential",
            entity_id=credential.id,
            payload={"name": normalized_name, "token_prefix": credential.token_prefix},
        )
    )
    session.flush()
    return IssuedPartnerApiCredential(credential=credential, raw_token=raw_token)


def list_partner_api_credentials(
    session: Session,
    *,
    organization_id: UUID,
    requested_by_user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[PartnerApiCredential]:
    """List bounded non-secret credential metadata for one tenant manager."""

    if limit < 1 or limit > PARTNER_API_LIST_MAX_LIMIT or offset < 0:
        raise PartnerApiCredentialError("invalid credential pagination")
    _require_manager(
        session,
        organization_id=organization_id,
        user_id=requested_by_user_id,
    )
    return list(
        session.scalars(
            select(PartnerApiCredential)
            .where(PartnerApiCredential.organization_id == organization_id)
            .order_by(PartnerApiCredential.created_at.desc(), PartnerApiCredential.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )


def authenticate_partner_api_token(
    session: Session,
    *,
    raw_token: str,
) -> PartnerApiCredential:
    """Resolve one active credential without exposing token-existence details."""

    if (
        not raw_token.startswith(PARTNER_API_TOKEN_PREFIX)
        or len(raw_token) > PARTNER_API_TOKEN_MAX_LENGTH
    ):
        raise PartnerApiAuthenticationError("invalid partner API credential")
    credential = session.scalar(
        select(PartnerApiCredential).where(
            PartnerApiCredential.token_sha256 == _digest(raw_token),
            PartnerApiCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise PartnerApiAuthenticationError("invalid partner API credential")
    return credential


def revoke_partner_api_credential(
    session: Session,
    *,
    organization_id: UUID,
    credential_id: UUID,
    revoked_by_user_id: UUID,
) -> PartnerApiCredential:
    """Revoke one tenant credential idempotently and audit the first revocation."""

    _require_manager(
        session,
        organization_id=organization_id,
        user_id=revoked_by_user_id,
    )
    credential = session.scalar(
        select(PartnerApiCredential)
        .where(
            PartnerApiCredential.id == credential_id,
            PartnerApiCredential.organization_id == organization_id,
        )
        .with_for_update()
    )
    if credential is None:
        raise PartnerApiCredentialError("partner API credential not found")
    if credential.revoked_at is None:
        credential.revoked_at = datetime.now(UTC)
        session.add(
            AuditEvent(
                organization_id=organization_id,
                actor_user_id=revoked_by_user_id,
                event_type="partner_api.credential_revoked",
                entity_type="partner_api_credential",
                entity_id=credential.id,
                payload={"name": credential.name, "token_prefix": credential.token_prefix},
            )
        )
        session.flush()
    return credential
