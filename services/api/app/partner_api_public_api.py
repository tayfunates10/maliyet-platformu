"""Read-only Partner API over explicitly published customer-safe projections."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.http_dependencies import get_database_session
from app.models import PublicCalculationProjection
from app.partner_api_credentials import (
    PartnerApiAuthenticationError,
    authenticate_partner_api_token,
)

router = APIRouter(prefix="/partner/v1", tags=["partner-api"])


class PartnerProjectionResponse(BaseModel):
    """Exact customer-safe allowlist exposed to authenticated partner clients."""

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


def _raw_partner_token(authorization: str | None) -> str:
    if authorization is None:
        raise _authentication_required()
    scheme, separator, raw_token = authorization.partition(" ")
    if separator != " " or scheme != "Bearer" or not raw_token or " " in raw_token:
        raise _authentication_required()
    return raw_token


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="partner API authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get(
    "/calculation-projections/{projection_id}",
    response_model=PartnerProjectionResponse,
)
def get_partner_calculation_projection(
    projection_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> PartnerProjectionResponse:
    """Return one active published projection inside the partner credential's tenant."""

    try:
        credential = authenticate_partner_api_token(
            session,
            raw_token=_raw_partner_token(authorization),
        )
    except PartnerApiAuthenticationError as exc:
        raise _authentication_required() from exc

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
    return PartnerProjectionResponse(
        title=projection.title,
        currency=projection.currency,
        estimate_min=_amount_text(projection.estimate_min),
        estimate_max=_amount_text(projection.estimate_max),
        published_at=projection.created_at,
    )
