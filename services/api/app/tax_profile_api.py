"""HTTP routes for tenant-scoped declared tax-profile context."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.models import TaxProfile
from app.tax_profile_onboarding import (
    TaxProfileAccessDenied,
    TaxProfileAlreadyExists,
    TaxProfileNotFound,
    TaxProfileValidationError,
    create_tax_profile,
    get_tax_profile,
    update_tax_profile,
)

router = APIRouter(
    prefix="/{organization_id}/tax-profile",
    tags=["tax-profile"],
)


class TaxProfileWriteRequest(BaseModel):
    """Declared tax context only; rates, brackets and actor identity are forbidden."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_type: str = Field(min_length=1, max_length=48)
    vat_registered: StrictBool


class TaxProfileResponse(BaseModel):
    """Internal tax-context projection without tax rates or formula outputs."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    entity_type: str
    vat_registered: bool
    created_at: datetime
    updated_at: datetime


def _response(profile: TaxProfile) -> TaxProfileResponse:
    return TaxProfileResponse(
        id=profile.id,
        organization_id=profile.organization_id,
        entity_type=profile.entity_type,
        vat_registered=profile.vat_registered,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _access_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="tax profile access denied",
    )


@router.post("", response_model=TaxProfileResponse, status_code=status.HTTP_201_CREATED)
def create_tax_profile_endpoint(
    organization_id: UUID,
    payload: TaxProfileWriteRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> TaxProfileResponse:
    """Create one tax context; only owner/admin may write business tax settings."""

    try:
        with session.begin_nested():
            profile = create_tax_profile(
                session,
                authenticated_user_id=identity.user_id,
                organization_id=organization_id,
                entity_type=payload.entity_type,
                vat_registered=payload.vat_registered,
            )
    except TaxProfileAccessDenied as exc:
        raise _access_denied() from exc
    except TaxProfileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (TaxProfileAlreadyExists, IntegrityError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="tax profile already exists",
        ) from exc
    return _response(profile)


@router.get("", response_model=TaxProfileResponse)
def get_tax_profile_endpoint(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> TaxProfileResponse:
    """Read declared tax context only for owner/admin/accountant roles."""

    try:
        profile = get_tax_profile(
            session,
            authenticated_user_id=identity.user_id,
            organization_id=organization_id,
        )
    except TaxProfileAccessDenied as exc:
        raise _access_denied() from exc
    except TaxProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="tax profile not found") from exc
    return _response(profile)


@router.put("", response_model=TaxProfileResponse)
def update_tax_profile_endpoint(
    organization_id: UUID,
    payload: TaxProfileWriteRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> TaxProfileResponse:
    """Update tax context as owner/admin while preserving the audit trail."""

    try:
        with session.begin_nested():
            profile = update_tax_profile(
                session,
                authenticated_user_id=identity.user_id,
                organization_id=organization_id,
                entity_type=payload.entity_type,
                vat_registered=payload.vat_registered,
            )
    except TaxProfileAccessDenied as exc:
        raise _access_denied() from exc
    except TaxProfileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except TaxProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="tax profile not found") from exc
    return _response(profile)
