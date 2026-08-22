"""Authenticated HTTP routes for safe widget branding profile publication."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.widget_branding import (
    DEFAULT_BORDER_RADIUS_PX,
    DEFAULT_DARK_BACKGROUND,
    DEFAULT_DARK_BORDER,
    DEFAULT_DARK_TEXT,
    DEFAULT_ERROR_COLOR,
    DEFAULT_LIGHT_BACKGROUND,
    DEFAULT_LIGHT_BORDER,
    DEFAULT_LIGHT_TEXT,
    WidgetBrandingNotFound,
    WidgetBrandingValidationError,
    WidgetPresentationPublication,
    WidgetPresentationValues,
    create_widget_branding_profile,
    get_widget_branding_profile,
    list_widget_branding_profiles,
    publish_widget_presentation,
    update_widget_branding_profile,
    validate_widget_presentation,
)
from app.widget_branding_models import WidgetBrandingProfile
from app.widget_security import WidgetAccessDenied, WidgetDeploymentNotFound

profile_router = APIRouter(
    prefix="/{organization_id}/widget-branding-profiles",
    tags=["widgets"],
)
deployment_router = APIRouter(
    prefix="/{organization_id}/widget-deployments",
    tags=["widgets"],
)


class WidgetBrandingProfileWriteRequest(BaseModel):
    """Strict allowlisted presentation draft; arbitrary CSS/HTML/URLs are not accepted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    theme: Literal["auto", "light", "dark"] = "auto"
    locale: Literal["tr", "en"] = "tr"
    density: Literal["comfortable", "compact"] = "comfortable"
    show_title: bool = Field(default=True, strict=True)
    light_background_color: str = Field(
        default=DEFAULT_LIGHT_BACKGROUND,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    light_text_color: str = Field(
        default=DEFAULT_LIGHT_TEXT,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    light_border_color: str = Field(
        default=DEFAULT_LIGHT_BORDER,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    dark_background_color: str = Field(
        default=DEFAULT_DARK_BACKGROUND,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    dark_text_color: str = Field(
        default=DEFAULT_DARK_TEXT,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    dark_border_color: str = Field(
        default=DEFAULT_DARK_BORDER,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    error_color: str = Field(
        default=DEFAULT_ERROR_COLOR,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    border_radius_px: int = Field(default=DEFAULT_BORDER_RADIUS_PX, strict=True, ge=0, le=32)
    font_family: Literal["system", "sans", "serif", "monospace"] = "system"


class WidgetBrandingProfileResponse(BaseModel):
    """Authenticated tenant view of one mutable branding draft."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    revision: int
    theme: str
    locale: str
    density: str
    show_title: bool
    light_background_color: str
    light_text_color: str
    light_border_color: str
    dark_background_color: str
    dark_text_color: str
    dark_border_color: str
    error_color: str
    border_radius_px: int
    font_family: str


class WidgetPresentationPublishRequest(BaseModel):
    """Select one tenant-owned branding draft to publish on a deployment."""

    model_config = ConfigDict(extra="forbid")

    branding_profile_id: UUID


class WidgetPresentationPublishResponse(BaseModel):
    """Authenticated publication receipt without exposing the internal snapshot identifier."""

    model_config = ConfigDict(frozen=True)

    deployment_id: UUID
    branding_profile_id: UUID
    profile_revision: int
    published_at: datetime


def _profile_response(profile: WidgetBrandingProfile) -> WidgetBrandingProfileResponse:
    return WidgetBrandingProfileResponse(
        id=profile.id,
        name=profile.name,
        revision=profile.revision,
        theme=profile.theme,
        locale=profile.locale,
        density=profile.density,
        show_title=profile.show_title,
        light_background_color=profile.light_background_color,
        light_text_color=profile.light_text_color,
        light_border_color=profile.light_border_color,
        dark_background_color=profile.dark_background_color,
        dark_text_color=profile.dark_text_color,
        dark_border_color=profile.dark_border_color,
        error_color=profile.error_color,
        border_radius_px=profile.border_radius_px,
        font_family=profile.font_family,
    )


def _presentation_from_request(
    payload: WidgetBrandingProfileWriteRequest,
) -> WidgetPresentationValues:
    return validate_widget_presentation(
        theme=payload.theme,
        locale=payload.locale,
        density=payload.density,
        show_title=payload.show_title,
        light_background_color=payload.light_background_color,
        light_text_color=payload.light_text_color,
        light_border_color=payload.light_border_color,
        dark_background_color=payload.dark_background_color,
        dark_text_color=payload.dark_text_color,
        dark_border_color=payload.dark_border_color,
        error_color=payload.error_color,
        border_radius_px=payload.border_radius_px,
        font_family=payload.font_family,
    )


def _tenant_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WidgetAccessDenied):
        return HTTPException(status_code=403, detail="widget access denied")
    if isinstance(exc, (WidgetBrandingNotFound, WidgetDeploymentNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, WidgetBrandingValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


def _publish_response(
    deployment_id: UUID,
    publication: WidgetPresentationPublication,
) -> WidgetPresentationPublishResponse:
    snapshot = publication.snapshot
    return WidgetPresentationPublishResponse(
        deployment_id=deployment_id,
        branding_profile_id=snapshot.branding_profile_id,
        profile_revision=snapshot.profile_revision,
        published_at=publication.published_at,
    )


@profile_router.post(
    "",
    response_model=WidgetBrandingProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_widget_branding_profile_endpoint(
    organization_id: UUID,
    payload: WidgetBrandingProfileWriteRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> WidgetBrandingProfileResponse:
    """Create one tenant branding draft with no public side effect."""

    try:
        profile = create_widget_branding_profile(
            session,
            identity=identity,
            organization_id=organization_id,
            name=payload.name,
            presentation=_presentation_from_request(payload),
        )
    except (WidgetAccessDenied, WidgetBrandingValidationError) as exc:
        raise _tenant_error(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="widget branding profile conflict") from exc
    return _profile_response(profile)


@profile_router.get("", response_model=list[WidgetBrandingProfileResponse])
def list_widget_branding_profiles_endpoint(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WidgetBrandingProfileResponse]:
    """List only branding drafts inside the authorized organization."""

    try:
        profiles = list_widget_branding_profiles(
            session,
            identity=identity,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )
    except WidgetAccessDenied as exc:
        raise _tenant_error(exc) from exc
    return [_profile_response(profile) for profile in profiles]


@profile_router.get("/{profile_id}", response_model=WidgetBrandingProfileResponse)
def get_widget_branding_profile_endpoint(
    organization_id: UUID,
    profile_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> WidgetBrandingProfileResponse:
    """Read one mutable draft only within its tenant boundary."""

    try:
        profile = get_widget_branding_profile(
            session,
            identity=identity,
            organization_id=organization_id,
            profile_id=profile_id,
        )
    except (WidgetAccessDenied, WidgetBrandingNotFound) as exc:
        raise _tenant_error(exc) from exc
    return _profile_response(profile)


@profile_router.put("/{profile_id}", response_model=WidgetBrandingProfileResponse)
def update_widget_branding_profile_endpoint(
    organization_id: UUID,
    profile_id: UUID,
    payload: WidgetBrandingProfileWriteRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> WidgetBrandingProfileResponse:
    """Replace a mutable draft; already-published snapshots remain unchanged."""

    try:
        profile = update_widget_branding_profile(
            session,
            identity=identity,
            organization_id=organization_id,
            profile_id=profile_id,
            name=payload.name,
            presentation=_presentation_from_request(payload),
        )
    except (WidgetAccessDenied, WidgetBrandingNotFound, WidgetBrandingValidationError) as exc:
        raise _tenant_error(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="widget branding profile conflict") from exc
    return _profile_response(profile)


@deployment_router.post(
    "/{deployment_id}/presentation",
    response_model=WidgetPresentationPublishResponse,
    status_code=status.HTTP_201_CREATED,
)
def publish_widget_presentation_endpoint(
    organization_id: UUID,
    deployment_id: UUID,
    payload: WidgetPresentationPublishRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> WidgetPresentationPublishResponse:
    """Publish an immutable snapshot of the selected draft on one active deployment."""

    try:
        publication = publish_widget_presentation(
            session,
            identity=identity,
            organization_id=organization_id,
            deployment_id=deployment_id,
            branding_profile_id=payload.branding_profile_id,
        )
    except (
        WidgetAccessDenied,
        WidgetBrandingNotFound,
        WidgetDeploymentNotFound,
        WidgetBrandingValidationError,
    ) as exc:
        raise _tenant_error(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="widget presentation conflict") from exc
    return _publish_response(deployment_id, publication)
