"""Customer-safe publication boundary for immutable calculation versions.

Public projections never copy source input, ruleset or output snapshots. They
contain only an explicitly customer-visible estimate envelope and an opaque
share token whose digest is persisted server-side.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import (
    AuthenticatedIdentity,
    AuthorizationError,
    resolve_actor_context,
)
from app.models import AuditEvent, CalculationVersion, PublicCalculationProjection

PUBLICATION_ROLES = frozenset({"owner", "admin"})
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_MAX_INTEGER_DIGITS = 26
_MAX_SCALE = 12
_MAX_RAW_TOKEN_LENGTH = 256


class PublicProjectionAccessDenied(PermissionError):
    """Raised when a tenant member may not publish or revoke customer output."""


class PublicProjectionSourceNotFound(LookupError):
    """Raised when the requested immutable source version is outside the tenant."""


class PublicProjectionSourceNotReady(ValueError):
    """Raised when a calculation version lacks complete provenance digests."""


class PublicProjectionValidationError(ValueError):
    """Raised when customer-visible publication fields violate the contract."""


class PublicProjectionNotFound(LookupError):
    """Raised for invalid, unknown or revoked public projection tokens."""


@dataclass(frozen=True)
class CreatedPublicProjection:
    """Projection plus its one-time raw token returned only at publication time."""

    projection: PublicCalculationProjection
    raw_token: str


def _token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _require_publisher(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
) -> UUID:
    try:
        actor = resolve_actor_context(
            session,
            identity=identity,
            organization_id=organization_id,
        )
    except AuthorizationError as exc:
        raise PublicProjectionAccessDenied("public projection access denied") from exc
    if actor.role not in PUBLICATION_ROLES:
        raise PublicProjectionAccessDenied("public projection access denied")
    return actor.user_id


def _validated_title(title: str) -> str:
    normalized = title.strip()
    if not normalized or len(normalized) > 160:
        raise PublicProjectionValidationError("title must be between 1 and 160 characters")
    return normalized


def _validated_currency(currency: str) -> str:
    normalized = currency.strip().upper()
    if _CURRENCY_PATTERN.fullmatch(normalized) is None:
        raise PublicProjectionValidationError("currency must be a three-letter code")
    return normalized


def _validated_amount(value: str, *, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PublicProjectionValidationError(f"{field} must be a decimal string") from exc
    if not parsed.is_finite() or parsed < 0:
        raise PublicProjectionValidationError(f"{field} must be a finite non-negative amount")

    exponent = parsed.as_tuple().exponent
    if not isinstance(exponent, int):
        raise PublicProjectionValidationError(f"{field} must be a finite non-negative amount")
    scale = max(-exponent, 0)
    if scale > _MAX_SCALE:
        raise PublicProjectionValidationError(
            f"{field} supports at most {_MAX_SCALE} decimal places"
        )
    integer_digits = max(parsed.adjusted() + 1, 1) if parsed != 0 else 1
    if integer_digits > _MAX_INTEGER_DIGITS:
        raise PublicProjectionValidationError(
            f"{field} supports at most {_MAX_INTEGER_DIGITS} integer digits"
        )
    return parsed


def _source_version(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
) -> CalculationVersion:
    version = session.scalar(
        select(CalculationVersion).where(
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.calculation_id == calculation_id,
            CalculationVersion.version == version_number,
        )
    )
    if version is None:
        raise PublicProjectionSourceNotFound("calculation version not found")
    if (
        version.input_sha256 is None
        or version.ruleset_sha256 is None
        or version.output_sha256 is None
    ):
        raise PublicProjectionSourceNotReady("calculation version provenance is incomplete")
    return version


def create_public_projection(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
    title: str,
    currency: str,
    estimate_min: str,
    estimate_max: str,
) -> CreatedPublicProjection:
    """Publish an immutable customer-safe envelope for one completed version."""

    actor_user_id = _require_publisher(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    version = _source_version(
        session,
        organization_id=organization_id,
        calculation_id=calculation_id,
        version_number=version_number,
    )
    normalized_title = _validated_title(title)
    normalized_currency = _validated_currency(currency)
    minimum = _validated_amount(estimate_min, field="estimate_min")
    maximum = _validated_amount(estimate_max, field="estimate_max")
    if maximum < minimum:
        raise PublicProjectionValidationError(
            "estimate_max must be greater than or equal to estimate_min"
        )

    raw_token = secrets.token_urlsafe(32)
    projection = PublicCalculationProjection(
        organization_id=organization_id,
        calculation_version_id=version.id,
        created_by_user_id=actor_user_id,
        token_sha256=_token_digest(raw_token),
        title=normalized_title,
        currency=normalized_currency,
        estimate_min=minimum,
        estimate_max=maximum,
    )
    session.add(projection)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="public_projection.created",
            entity_type="public_calculation_projection",
            entity_id=projection.id,
            payload={
                "calculation_version_id": str(version.id),
                "title": normalized_title,
                "currency": normalized_currency,
                "estimate_min": str(minimum),
                "estimate_max": str(maximum),
            },
        )
    )
    session.flush()
    return CreatedPublicProjection(projection=projection, raw_token=raw_token)


def revoke_public_projection(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    projection_id: UUID,
    now: datetime | None = None,
) -> None:
    """Revoke a public token idempotently while preserving an audit event."""

    actor_user_id = _require_publisher(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    projection = session.scalar(
        select(PublicCalculationProjection)
        .where(
            PublicCalculationProjection.id == projection_id,
            PublicCalculationProjection.organization_id == organization_id,
        )
        .with_for_update()
    )
    if projection is None:
        raise PublicProjectionNotFound("public projection not found")
    if projection.revoked_at is not None:
        return

    revoked_at = now or datetime.now(UTC)
    if revoked_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    projection.revoked_at = revoked_at
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="public_projection.revoked",
            entity_type="public_calculation_projection",
            entity_id=projection.id,
            payload={},
        )
    )
    session.flush()


def resolve_public_projection(
    session: Session,
    *,
    raw_token: str,
) -> PublicCalculationProjection:
    """Resolve one active public artifact without exposing tenant/source identifiers."""

    if not raw_token or len(raw_token) > _MAX_RAW_TOKEN_LENGTH:
        raise PublicProjectionNotFound("public projection not found")
    projection = session.scalar(
        select(PublicCalculationProjection).where(
            PublicCalculationProjection.token_sha256 == _token_digest(raw_token),
            PublicCalculationProjection.revoked_at.is_(None),
        )
    )
    if projection is None:
        raise PublicProjectionNotFound("public projection not found")
    return projection
