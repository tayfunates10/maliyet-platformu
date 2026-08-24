"""Authenticated HTTP management routes for tenant partner API credentials."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.partner_api_credentials import (
    PartnerApiAuthorizationError,
    PartnerApiCredentialError,
    issue_partner_api_credential,
    list_partner_api_credentials,
    revoke_partner_api_credential,
)
from app.partner_api_models import PartnerApiCredential

router = APIRouter(
    prefix="/organizations/{organization_id}/partner-api-credentials",
    tags=["partner-api"],
)


class PartnerApiCredentialCreateRequest(BaseModel):
    """Strict request for a named tenant partner credential."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=160)


class PartnerApiCredentialMetadataResponse(BaseModel):
    """Non-secret partner credential metadata safe for tenant managers."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    token_prefix: str
    created_by_user_id: UUID
    created_at: datetime
    revoked_at: datetime | None


class PartnerApiCredentialCreateResponse(PartnerApiCredentialMetadataResponse):
    """Credential issuance response containing the raw token exactly once."""

    raw_token: str


def _metadata(credential: PartnerApiCredential) -> PartnerApiCredentialMetadataResponse:
    return PartnerApiCredentialMetadataResponse(
        id=credential.id,
        name=credential.name,
        token_prefix=credential.token_prefix,
        created_by_user_id=credential.created_by_user_id,
        created_at=credential.created_at,
        revoked_at=credential.revoked_at,
    )


def _management_error(exc: PartnerApiCredentialError) -> HTTPException:
    if isinstance(exc, PartnerApiAuthorizationError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="partner API credential management denied",
        )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="partner API credential not found",
    )


@router.post(
    "",
    response_model=PartnerApiCredentialCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_partner_api_credential(
    organization_id: UUID,
    payload: PartnerApiCredentialCreateRequest,
    response: Response,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> PartnerApiCredentialCreateResponse:
    """Issue one tenant credential and return its raw token once with no-store caching."""

    try:
        issued = issue_partner_api_credential(
            session,
            organization_id=organization_id,
            created_by_user_id=identity.user_id,
            name=payload.name,
        )
    except PartnerApiAuthorizationError as exc:
        raise _management_error(exc) from exc
    except PartnerApiCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    credential = issued.credential
    response.headers["Cache-Control"] = "no-store"
    return PartnerApiCredentialCreateResponse(
        id=credential.id,
        name=credential.name,
        token_prefix=credential.token_prefix,
        created_by_user_id=credential.created_by_user_id,
        created_at=credential.created_at,
        revoked_at=credential.revoked_at,
        raw_token=issued.raw_token,
    )


@router.get("", response_model=list[PartnerApiCredentialMetadataResponse])
def list_partner_credentials(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PartnerApiCredentialMetadataResponse]:
    """List bounded tenant credential metadata without raw tokens or digests."""

    try:
        credentials = list_partner_api_credentials(
            session,
            organization_id=organization_id,
            requested_by_user_id=identity.user_id,
            limit=limit,
            offset=offset,
        )
    except PartnerApiCredentialError as exc:
        raise _management_error(exc) from exc
    return [_metadata(credential) for credential in credentials]


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def revoke_partner_credential(
    organization_id: UUID,
    credential_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
) -> Response:
    """Idempotently revoke one tenant credential without deleting audit history."""

    try:
        revoke_partner_api_credential(
            session,
            organization_id=organization_id,
            credential_id=credential_id,
            revoked_by_user_id=identity.user_id,
        )
    except PartnerApiCredentialError as exc:
        raise _management_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
