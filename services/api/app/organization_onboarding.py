"""Authenticated organization bootstrap and membership-scoped reads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models import (
    SUPPORTED_SECTORS,
    AuditEvent,
    BusinessProfile,
    Organization,
    OrganizationMembership,
    User,
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationOnboardingError(ValueError):
    """Raised when organization bootstrap input violates a domain contract."""


class OrganizationAccessDenied(PermissionError):
    """Raised when an authenticated user is not a member of an organization."""


@dataclass(frozen=True)
class OrganizationAccess:
    """Organization metadata paired with the authenticated user's membership."""

    organization: Organization
    membership: OrganizationMembership
    business_profile: BusinessProfile | None


def _validated_slug(slug: str) -> str:
    normalized = slug.strip()
    if len(normalized) < 3 or len(normalized) > 80 or _SLUG_PATTERN.fullmatch(normalized) is None:
        raise OrganizationOnboardingError(
            "organization slug must be 3-80 lowercase letters, numbers or single hyphens"
        )
    return normalized


def _validated_text(value: str, *, field: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise OrganizationOnboardingError(f"{field} must be between 1 and {max_length} characters")
    return normalized


def _validated_city(city: str | None) -> str | None:
    if city is None:
        return None
    normalized = city.strip()
    if not normalized:
        return None
    if len(normalized) > 120:
        raise OrganizationOnboardingError("city must be at most 120 characters")
    return normalized


def create_organization_bootstrap(
    session: Session,
    *,
    authenticated_user_id: UUID,
    slug: str,
    legal_name: str,
    primary_sector: str,
    city: str | None,
) -> OrganizationAccess:
    """Create one tenant and bind the authenticated user as its server-assigned owner."""

    user = session.scalar(
        select(User).where(User.id == authenticated_user_id, User.is_active.is_(True))
    )
    if user is None:
        raise OrganizationAccessDenied("active authenticated user is required")
    if primary_sector not in SUPPORTED_SECTORS:
        raise OrganizationOnboardingError("unsupported primary sector")

    organization = Organization(
        slug=_validated_slug(slug),
        legal_name=_validated_text(legal_name, field="legal name", max_length=240),
    )
    session.add(organization)
    session.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=authenticated_user_id,
        role="owner",
    )
    business_profile = BusinessProfile(
        organization_id=organization.id,
        primary_sector=primary_sector,
        country_code="TR",
        city=_validated_city(city),
    )
    session.add_all([membership, business_profile])
    session.flush()

    session.add(
        AuditEvent(
            organization_id=organization.id,
            actor_user_id=authenticated_user_id,
            event_type="organization.created",
            entity_type="organization",
            entity_id=organization.id,
            payload={"primary_sector": primary_sector},
        )
    )
    session.flush()
    return OrganizationAccess(
        organization=organization,
        membership=membership,
        business_profile=business_profile,
    )


def _access_query() -> Select[tuple[OrganizationMembership, Organization, BusinessProfile]]:
    return (
        select(OrganizationMembership, Organization, BusinessProfile)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .outerjoin(BusinessProfile, BusinessProfile.organization_id == Organization.id)
    )


def _access_from_tuple(
    row: tuple[OrganizationMembership, Organization, BusinessProfile],
) -> OrganizationAccess:
    membership, organization, business_profile = row
    return OrganizationAccess(
        organization=organization,
        membership=membership,
        business_profile=cast(BusinessProfile | None, business_profile),
    )


def list_organization_access(
    session: Session,
    *,
    authenticated_user_id: UUID,
    limit: int,
    offset: int,
) -> list[OrganizationAccess]:
    """List memberships and tenant projections with one bounded joined query."""

    rows = (
        session.execute(
            _access_query()
            .where(OrganizationMembership.user_id == authenticated_user_id)
            .order_by(OrganizationMembership.created_at.desc(), OrganizationMembership.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .tuples()
        .all()
    )
    return [_access_from_tuple(row) for row in rows]


def get_organization_access(
    session: Session,
    *,
    authenticated_user_id: UUID,
    organization_id: UUID,
) -> OrganizationAccess:
    """Return one joined tenant projection only after membership is established."""

    row = (
        session.execute(
            _access_query().where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == authenticated_user_id,
            )
        )
        .tuples()
        .one_or_none()
    )
    if row is None:
        raise OrganizationAccessDenied("organization access denied")
    return _access_from_tuple(row)
