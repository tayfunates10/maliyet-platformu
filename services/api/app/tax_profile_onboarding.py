"""Tenant-scoped tax-profile context with least-privilege authorization.

`entity_type` is an application classification only. It must not be treated as
an authoritative Turkish statutory legal-form taxonomy or as a tax-rate source.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, TaxProfile
from app.organization_onboarding import (
    OrganizationAccessDenied,
    get_organization_access,
)

TAX_ENTITY_TYPES = frozenset(
    {
        "sole_proprietorship",
        "limited",
        "joint_stock",
        "partnership",
        "cooperative",
        "other",
    }
)
TAX_PROFILE_READ_ROLES = frozenset({"owner", "admin", "accountant"})
TAX_PROFILE_WRITE_ROLES = frozenset({"owner", "admin"})


class TaxProfileValidationError(ValueError):
    """Raised when declared tax-profile context violates the application contract."""


class TaxProfileAccessDenied(PermissionError):
    """Raised when a tenant member lacks tax-profile permission."""


class TaxProfileNotFound(LookupError):
    """Raised when an authorized organization has no tax profile yet."""


class TaxProfileAlreadyExists(ValueError):
    """Raised when a create request targets an organization with a tax profile."""


def _authorize(
    session: Session,
    *,
    authenticated_user_id: UUID,
    organization_id: UUID,
    write: bool,
) -> str:
    try:
        access = get_organization_access(
            session,
            authenticated_user_id=authenticated_user_id,
            organization_id=organization_id,
        )
    except OrganizationAccessDenied as exc:
        raise TaxProfileAccessDenied("tax profile access denied") from exc

    allowed_roles = TAX_PROFILE_WRITE_ROLES if write else TAX_PROFILE_READ_ROLES
    if access.membership.role not in allowed_roles:
        raise TaxProfileAccessDenied("tax profile access denied")
    return access.membership.role


def _validated_entity_type(entity_type: str) -> str:
    normalized = entity_type.strip()
    if normalized not in TAX_ENTITY_TYPES:
        raise TaxProfileValidationError("unsupported tax entity type")
    return normalized


def _profile_or_not_found(session: Session, *, organization_id: UUID) -> TaxProfile:
    profile = session.scalar(
        select(TaxProfile).where(TaxProfile.organization_id == organization_id)
    )
    if profile is None:
        raise TaxProfileNotFound("tax profile not found")
    return profile


def _locked_profile_or_not_found(session: Session, *, organization_id: UUID) -> TaxProfile:
    """Lock one tenant tax profile before capturing mutable audit state."""

    profile = session.scalar(
        select(TaxProfile).where(TaxProfile.organization_id == organization_id).with_for_update()
    )
    if profile is None:
        raise TaxProfileNotFound("tax profile not found")
    return profile


def create_tax_profile(
    session: Session,
    *,
    authenticated_user_id: UUID,
    organization_id: UUID,
    entity_type: str,
    vat_registered: bool,
) -> TaxProfile:
    """Create one declared tax context for an organization as owner/admin."""

    _authorize(
        session,
        authenticated_user_id=authenticated_user_id,
        organization_id=organization_id,
        write=True,
    )
    if (
        session.scalar(select(TaxProfile.id).where(TaxProfile.organization_id == organization_id))
        is not None
    ):
        raise TaxProfileAlreadyExists("tax profile already exists")

    normalized_entity_type = _validated_entity_type(entity_type)
    profile = TaxProfile(
        organization_id=organization_id,
        entity_type=normalized_entity_type,
        vat_registered=vat_registered,
    )
    session.add(profile)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=authenticated_user_id,
            event_type="tax_profile.created",
            entity_type="tax_profile",
            entity_id=profile.id,
            payload={
                "entity_type": normalized_entity_type,
                "vat_registered": vat_registered,
            },
        )
    )
    session.flush()
    return profile


def get_tax_profile(
    session: Session,
    *,
    authenticated_user_id: UUID,
    organization_id: UUID,
) -> TaxProfile:
    """Read declared tax context only for owner/admin/accountant roles."""

    _authorize(
        session,
        authenticated_user_id=authenticated_user_id,
        organization_id=organization_id,
        write=False,
    )
    return _profile_or_not_found(session, organization_id=organization_id)


def update_tax_profile(
    session: Session,
    *,
    authenticated_user_id: UUID,
    organization_id: UUID,
    entity_type: str,
    vat_registered: bool,
) -> TaxProfile:
    """Serialize updates, then append an audit event from the locked prior state."""

    _authorize(
        session,
        authenticated_user_id=authenticated_user_id,
        organization_id=organization_id,
        write=True,
    )
    profile = _locked_profile_or_not_found(session, organization_id=organization_id)
    normalized_entity_type = _validated_entity_type(entity_type)
    before = {
        "entity_type": profile.entity_type,
        "vat_registered": profile.vat_registered,
    }
    after = {
        "entity_type": normalized_entity_type,
        "vat_registered": vat_registered,
    }
    profile.entity_type = normalized_entity_type
    profile.vat_registered = vat_registered
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=authenticated_user_id,
            event_type="tax_profile.updated",
            entity_type="tax_profile",
            entity_id=profile.id,
            payload={"before": before, "after": after},
        )
    )
    session.flush()
    return profile
