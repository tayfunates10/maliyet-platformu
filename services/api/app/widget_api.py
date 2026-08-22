"""HTTP routes for tenant widget configuration and browser-safe consumption."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.models import PublicCalculationProjection, WidgetAllowedOrigin, WidgetDeployment
from app.widget_branding import (
    WidgetPresentationPublication,
    get_published_widget_presentation,
)
from app.widget_security import (
    WidgetAccessDenied,
    WidgetDeploymentNotFound,
    WidgetOriginDenied,
    WidgetProjectionNotFound,
    WidgetQuotaExceeded,
    WidgetValidationError,
    add_widget_allowed_origin,
    consume_widget_projection,
    create_widget_deployment,
    disable_widget_deployment,
    remove_widget_allowed_origin,
)

tenant_router = APIRouter(prefix="/{organization_id}/widget-deployments", tags=["widgets"])
public_router = APIRouter(prefix="/widget/deployments", tags=["widgets"])


class WidgetDeploymentCreateRequest(BaseModel):
    """Strict tenant configuration for one customer-safe widget deployment."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    public_projection_id: UUID
    name: str = Field(min_length=1, max_length=160)
    hourly_request_limit: int = Field(strict=True, ge=1, le=100000)
    allowed_origins: list[str] = Field(min_length=1, max_length=20)


class WidgetAllowedOriginCreateRequest(BaseModel):
    """One exact HTTPS origin to add to a deployment."""

    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=1, max_length=512)


class WidgetAllowedOriginResponse(BaseModel):
    """Authenticated widget-origin registry item."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    origin: str


class WidgetDeploymentResponse(BaseModel):
    """Authenticated tenant projection of one widget deployment."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    public_projection_id: UUID
    name: str
    hourly_request_limit: int
    disabled_at: datetime | None
    created_at: datetime
    allowed_origins: list[WidgetAllowedOriginResponse]


class WidgetPublicPresentationResponse(BaseModel):
    """Public allowlisted presentation copied from an immutable published snapshot."""

    model_config = ConfigDict(frozen=True)

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
    published_at: datetime


class WidgetProjectionResponse(BaseModel):
    """Browser response containing only customer-safe publication fields."""

    model_config = ConfigDict(frozen=True)

    title: str
    currency: str
    estimate_min: str
    estimate_max: str
    published_at: datetime
    presentation: WidgetPublicPresentationResponse | None = None


def _amount_text(value: Decimal | str) -> str:
    """Render a persisted exact decimal without accepting binary floating-point values."""

    if isinstance(value, str):
        try:
            normalized = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("invalid persisted widget amount") from exc
    else:
        normalized = value
    if not normalized.is_finite():
        raise ValueError("invalid persisted widget amount")

    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _origin_response(origin: WidgetAllowedOrigin) -> WidgetAllowedOriginResponse:
    return WidgetAllowedOriginResponse(id=origin.id, origin=origin.origin)


def _deployment_response(
    deployment: WidgetDeployment,
    origins: tuple[WidgetAllowedOrigin, ...],
) -> WidgetDeploymentResponse:
    return WidgetDeploymentResponse(
        id=deployment.id,
        public_projection_id=deployment.public_projection_id,
        name=deployment.name,
        hourly_request_limit=deployment.hourly_request_limit,
        disabled_at=deployment.disabled_at,
        created_at=deployment.created_at,
        allowed_origins=[_origin_response(origin) for origin in origins],
    )


def _presentation_response(
    publication: WidgetPresentationPublication | None,
) -> WidgetPublicPresentationResponse | None:
    if publication is None:
        return None
    snapshot = publication.snapshot
    return WidgetPublicPresentationResponse(
        theme=snapshot.theme,
        locale=snapshot.locale,
        density=snapshot.density,
        show_title=snapshot.show_title,
        light_background_color=snapshot.light_background_color,
        light_text_color=snapshot.light_text_color,
        light_border_color=snapshot.light_border_color,
        dark_background_color=snapshot.dark_background_color,
        dark_text_color=snapshot.dark_text_color,
        dark_border_color=snapshot.dark_border_color,
        error_color=snapshot.error_color,
        border_radius_px=snapshot.border_radius_px,
        font_family=snapshot.font_family,
        published_at=publication.published_at,
    )


def _projection_response(
    projection: PublicCalculationProjection,
    *,
    presentation: WidgetPresentationPublication | None,
) -> WidgetProjectionResponse:
    return WidgetProjectionResponse(
        title=projection.title,
        currency=projection.currency,
        estimate_min=_amount_text(projection.estimate_min),
        estimate_max=_amount_text(projection.estimate_max),
        published_at=projection.created_at,
        presentation=_presentation_response(presentation),
    )


def _tenant_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WidgetAccessDenied):
        return HTTPException(status_code=403, detail="widget access denied")
    if isinstance(exc, (WidgetProjectionNotFound, WidgetDeploymentNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, WidgetValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


@tenant_router.post(
    "",
    response_model=WidgetDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_widget_deployment_endpoint(
    organization_id: UUID,
    payload: WidgetDeploymentCreateRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> WidgetDeploymentResponse:
    """Create a deployment without exposing the projection's raw share token."""

    try:
        deployment, origins = create_widget_deployment(
            session,
            identity=identity,
            organization_id=organization_id,
            public_projection_id=payload.public_projection_id,
            name=payload.name,
            hourly_request_limit=payload.hourly_request_limit,
            allowed_origins=payload.allowed_origins,
        )
    except (WidgetAccessDenied, WidgetProjectionNotFound, WidgetValidationError) as exc:
        raise _tenant_error(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="widget configuration conflict") from exc
    return _deployment_response(deployment, origins)


@tenant_router.post(
    "/{deployment_id}/allowed-origins",
    response_model=WidgetAllowedOriginResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_widget_allowed_origin_endpoint(
    organization_id: UUID,
    deployment_id: UUID,
    payload: WidgetAllowedOriginCreateRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> WidgetAllowedOriginResponse:
    """Add one exact normalized HTTPS origin as owner/admin."""

    try:
        origin = add_widget_allowed_origin(
            session,
            identity=identity,
            organization_id=organization_id,
            deployment_id=deployment_id,
            origin=payload.origin,
        )
    except (WidgetAccessDenied, WidgetDeploymentNotFound, WidgetValidationError) as exc:
        raise _tenant_error(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="widget configuration conflict") from exc
    return _origin_response(origin)


@tenant_router.delete(
    "/{deployment_id}/allowed-origins/{origin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def remove_widget_allowed_origin_endpoint(
    organization_id: UUID,
    deployment_id: UUID,
    origin_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> Response:
    """Remove one exact origin from the allowlist immediately."""

    try:
        remove_widget_allowed_origin(
            session,
            identity=identity,
            organization_id=organization_id,
            deployment_id=deployment_id,
            origin_id=origin_id,
        )
    except (WidgetAccessDenied, WidgetDeploymentNotFound) as exc:
        raise _tenant_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@tenant_router.delete(
    "/{deployment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def disable_widget_deployment_endpoint(
    organization_id: UUID,
    deployment_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> Response:
    """Disable one deployment idempotently; its public ID stops resolving."""

    try:
        disable_widget_deployment(
            session,
            identity=identity,
            organization_id=organization_id,
            deployment_id=deployment_id,
        )
    except (WidgetAccessDenied, WidgetDeploymentNotFound) as exc:
        raise _tenant_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get(
    "/{deployment_id}/projection",
    response_model=WidgetProjectionResponse,
    response_model_exclude_none=True,
)
def consume_widget_projection_endpoint(
    deployment_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
    origin: Annotated[str | None, Header()] = None,
) -> WidgetProjectionResponse:
    """Resolve a safe projection only for an exact allowed browser Origin."""

    try:
        consumption = consume_widget_projection(
            session,
            deployment_id=deployment_id,
            raw_origin=origin,
        )
    except WidgetDeploymentNotFound as exc:
        raise HTTPException(status_code=404, detail="widget deployment not found") from exc
    except WidgetOriginDenied as exc:
        raise HTTPException(status_code=403, detail="widget origin denied") from exc
    except WidgetQuotaExceeded as exc:
        retry_after = max(
            math.ceil((exc.reset_at - datetime.now(UTC)).total_seconds()),
            1,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="widget request quota exceeded",
            headers={
                "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": exc.canonical_origin,
                "Vary": "Origin",
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(exc.request_limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(exc.reset_at.timestamp())),
            },
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    response.headers["Access-Control-Allow-Origin"] = consumption.canonical_origin
    response.headers["Vary"] = "Origin"
    response.headers["X-RateLimit-Limit"] = str(consumption.request_limit)
    response.headers["X-RateLimit-Remaining"] = str(consumption.remaining)
    response.headers["X-RateLimit-Reset"] = str(int(consumption.reset_at.timestamp()))
    return _projection_response(
        consumption.projection,
        presentation=get_published_widget_presentation(
            session,
            deployment_id=deployment_id,
        ),
    )
