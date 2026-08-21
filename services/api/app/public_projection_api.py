"""HTTP routes for publishing and resolving customer-safe calculation projections."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.models import PublicCalculationProjection
from app.public_projection import (
    PublicProjectionAccessDenied,
    PublicProjectionNotFound,
    PublicProjectionSourceNotFound,
    PublicProjectionSourceNotReady,
    PublicProjectionValidationError,
    create_public_projection,
    resolve_public_projection,
    revoke_public_projection,
)

tenant_router = APIRouter(prefix="/{organization_id}", tags=["public-projections"])
public_router = APIRouter(prefix="/public/calculation-projections", tags=["public-projections"])


class PublicProjectionCreateRequest(BaseModel):
    """Strict customer-visible estimate envelope; no internal economics are accepted."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=160)
    currency: str = Field(min_length=3, max_length=3)
    estimate_min: str = Field(min_length=1, max_length=80)
    estimate_max: str = Field(min_length=1, max_length=80)


class PublicProjectionCreateResponse(BaseModel):
    """Authenticated creation response including the one-time raw share token."""

    model_config = ConfigDict(frozen=True)

    projection_id: UUID
    share_token: str
    title: str
    currency: str
    estimate_min: str
    estimate_max: str
    created_at: datetime


class PublicProjectionResponse(BaseModel):
    """Anonymous customer response containing only explicitly public presentation fields."""

    model_config = ConfigDict(frozen=True)

    title: str
    currency: str
    estimate_min: str
    estimate_max: str
    published_at: datetime


def _amount_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _public_response(projection: PublicCalculationProjection) -> PublicProjectionResponse:
    return PublicProjectionResponse(
        title=projection.title,
        currency=projection.currency,
        estimate_min=_amount_text(projection.estimate_min),
        estimate_max=_amount_text(projection.estimate_max),
        published_at=projection.created_at,
    )


@tenant_router.post(
    "/calculations/{calculation_id}/versions/{version_number}/public-projections",
    response_model=PublicProjectionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def publish_calculation_projection(
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
    payload: PublicProjectionCreateRequest,
    response: Response,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> PublicProjectionCreateResponse:
    """Create one immutable customer-safe artifact from a completed source version."""

    try:
        created = create_public_projection(
            session,
            identity=identity,
            organization_id=organization_id,
            calculation_id=calculation_id,
            version_number=version_number,
            title=payload.title,
            currency=payload.currency,
            estimate_min=payload.estimate_min,
            estimate_max=payload.estimate_max,
        )
    except PublicProjectionAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="public projection access denied",
        ) from exc
    except PublicProjectionSourceNotFound as exc:
        raise HTTPException(status_code=404, detail="calculation version not found") from exc
    except PublicProjectionSourceNotReady as exc:
        raise HTTPException(
            status_code=409,
            detail="calculation version is not publishable",
        ) from exc
    except PublicProjectionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    projection = created.projection
    response.headers["Cache-Control"] = "no-store"
    return PublicProjectionCreateResponse(
        projection_id=projection.id,
        share_token=created.raw_token,
        title=projection.title,
        currency=projection.currency,
        estimate_min=_amount_text(projection.estimate_min),
        estimate_max=_amount_text(projection.estimate_max),
        created_at=projection.created_at,
    )


@tenant_router.delete(
    "/public-calculation-projections/{projection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def revoke_calculation_projection(
    organization_id: UUID,
    projection_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> Response:
    """Revoke a customer share token as an owner/admin without deleting audit history."""

    try:
        revoke_public_projection(
            session,
            identity=identity,
            organization_id=organization_id,
            projection_id=projection_id,
        )
    except PublicProjectionAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="public projection access denied",
        ) from exc
    except PublicProjectionNotFound as exc:
        raise HTTPException(status_code=404, detail="public projection not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/{share_token}", response_model=PublicProjectionResponse)
def get_public_calculation_projection(
    share_token: str,
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
) -> PublicProjectionResponse:
    """Resolve an active opaque share token without returning tenant/source/private data."""

    try:
        projection = resolve_public_projection(session, raw_token=share_token)
    except PublicProjectionNotFound as exc:
        raise HTTPException(status_code=404, detail="public projection not found") from exc
    response.headers["Cache-Control"] = "no-store"
    return _public_response(projection)
