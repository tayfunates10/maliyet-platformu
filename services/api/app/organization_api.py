"""HTTP routes for authenticated organization onboarding and discovery."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.organization_onboarding import (
    OrganizationAccess,
    OrganizationAccessDenied,
    OrganizationOnboardingError,
    create_organization_bootstrap,
    get_organization_access,
    list_organization_access,
)
from app.public_projection_api import public_router as public_projection_public_router
from app.public_projection_api import tenant_router as public_projection_tenant_router
from app.report_export_api import router as report_export_router
from app.tax_profile_api import router as tax_profile_router
from app.widget_api import public_router as widget_public_router
from app.widget_api import tenant_router as widget_tenant_router
from app.widget_branding_api import deployment_router as widget_branding_deployment_router
from app.widget_branding_api import profile_router as widget_branding_profile_router
from app.widget_deployment_discovery_api import router as widget_deployment_discovery_router

router = APIRouter(prefix="/organizations", tags=["organizations"])
router.include_router(tax_profile_router)
router.include_router(public_projection_tenant_router)
router.include_router(public_projection_public_router)
router.include_router(widget_tenant_router)
router.include_router(widget_public_router)
router.include_router(widget_branding_profile_router)
router.include_router(widget_branding_deployment_router)
router.include_router(widget_deployment_discovery_router)
router.include_router(report_export_router)


class OrganizationCreateRequest(BaseModel):
    """Strict bootstrap payload; owner identity and role are never caller-controlled."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(min_length=3, max_length=80)
    legal_name: str = Field(min_length=1, max_length=240)
    primary_sector: str = Field(min_length=1, max_length=64)
    city: str | None = Field(default=None, max_length=120)


class OrganizationResponse(BaseModel):
    """Tenant-safe organization projection for one authenticated membership."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str
    legal_name: str
    role: str
    primary_sector: str | None
    country_code: str | None
    city: str | None


def _response(access: OrganizationAccess) -> OrganizationResponse:
    profile = access.business_profile
    return OrganizationResponse(
        id=access.organization.id,
        slug=access.organization.slug,
        legal_name=access.organization.legal_name,
        role=access.membership.role,
        primary_sector=None if profile is None else profile.primary_sector,
        country_code=None if profile is None else profile.country_code,
        city=None if profile is None else profile.city,
    )


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    payload: OrganizationCreateRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> OrganizationResponse:
    """Create one organization and make the authenticated user its owner."""

    try:
        with session.begin_nested():
            access = create_organization_bootstrap(
                session,
                authenticated_user_id=identity.user_id,
                slug=payload.slug,
                legal_name=payload.legal_name,
                primary_sector=payload.primary_sector,
                city=payload.city,
            )
    except OrganizationOnboardingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except OrganizationAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="organization creation denied",
        ) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="organization slug already exists",
        ) from exc
    return _response(access)


@router.get("", response_model=list[OrganizationResponse])
def list_organizations(
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[OrganizationResponse]:
    """List only organizations for which the authenticated user is a member."""

    return [
        _response(access)
        for access in list_organization_access(
            session,
            authenticated_user_id=identity.user_id,
            limit=limit,
            offset=offset,
        )
    ]


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> OrganizationResponse:
    """Return one organization only after server-side membership resolution."""

    try:
        access = get_organization_access(
            session,
            authenticated_user_id=identity.user_id,
            organization_id=organization_id,
        )
    except OrganizationAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="organization access denied",
        ) from exc
    return _response(access)
