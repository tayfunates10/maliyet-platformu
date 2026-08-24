"""Read-only Partner API over explicitly published customer-safe projections."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.http_dependencies import get_database_session
from app.models import PartnerApiCredential, PublicCalculationProjection
from app.partner_api_credentials import (
    PartnerApiAuthenticationError,
    authenticate_partner_api_token,
)

router = APIRouter(prefix="/partner/v1", tags=["partner-api"])
partner_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="PartnerApiBearer",
    description="Tenant-scoped Partner API bearer credential.",
)


class PartnerProjectionResponse(BaseModel):
    """Exact customer-safe allowlist exposed to authenticated partner clients."""

    model_config = ConfigDict(frozen=True)

    title: str
    currency: str
    estimate_min: str
    estimate_max: str
    published_at: datetime


class PartnerProjectionListItem(PartnerProjectionResponse):
    """Discoverable public artifact identifier plus the customer-safe projection."""

    projection_id: UUID


class PartnerProjectionListResponse(BaseModel):
    """Bounded tenant-scoped collection of active public projections."""

    model_config = ConfigDict(frozen=True)

    items: list[PartnerProjectionListItem]
    next_offset: int | None


def _amount_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _raw_partner_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise _authentication_required()
    return credentials.credentials


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="partner API authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authenticate_partner(
    session: Session,
    credentials: HTTPAuthorizationCredentials | None,
) -> PartnerApiCredential:
    try:
        return authenticate_partner_api_token(
            session,
            raw_token=_raw_partner_token(credentials),
        )
    except PartnerApiAuthenticationError as exc:
        raise _authentication_required() from exc


def _projection_response(projection: PublicCalculationProjection) -> PartnerProjectionResponse:
    return PartnerProjectionResponse(
        title=projection.title,
        currency=projection.currency,
        estimate_min=_amount_text(projection.estimate_min),
        estimate_max=_amount_text(projection.estimate_max),
        published_at=projection.created_at,
    )


@router.get(
    "/calculation-projections",
    response_model=PartnerProjectionListResponse,
)
def list_partner_calculation_projections(
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(partner_bearer),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> PartnerProjectionListResponse:
    """List active published projections inside the partner credential's tenant."""

    credential = _authenticate_partner(session, credentials)
    projections = list(
        session.scalars(
            select(PublicCalculationProjection)
            .where(
                PublicCalculationProjection.organization_id == credential.organization_id,
                PublicCalculationProjection.revoked_at.is_(None),
            )
            .order_by(
                PublicCalculationProjection.created_at.desc(),
                PublicCalculationProjection.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
    )
    has_more = len(projections) > limit
    visible = projections[:limit]
    response.headers["Cache-Control"] = "no-store"
    return PartnerProjectionListResponse(
        items=[
            PartnerProjectionListItem(
                projection_id=projection.id,
                **_projection_response(projection).model_dump(),
            )
            for projection in visible
        ],
        next_offset=offset + limit if has_more else None,
    )


@router.get(
    "/calculation-projections/{projection_id}",
    response_model=PartnerProjectionResponse,
)
def get_partner_calculation_projection(
    projection_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(partner_bearer),
    ],
) -> PartnerProjectionResponse:
    """Return one active published projection inside the partner credential's tenant."""

    credential = _authenticate_partner(session, credentials)
    projection = session.scalar(
        select(PublicCalculationProjection).where(
            PublicCalculationProjection.id == projection_id,
            PublicCalculationProjection.organization_id == credential.organization_id,
            PublicCalculationProjection.revoked_at.is_(None),
        )
    )
    if projection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="partner projection not found",
        )

    response.headers["Cache-Control"] = "no-store"
    return _projection_response(projection)
