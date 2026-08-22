"""Authenticated tenant widget deployment discovery routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity
from app.http_dependencies import get_authenticated_identity, get_database_session
from app.widget_deployment_discovery import DiscoveredWidgetDeployment, list_widget_deployments
from app.widget_security import WidgetAccessDenied

router = APIRouter(prefix="/{organization_id}/widget-deployments", tags=["widgets"])


class WidgetDeploymentDiscoveryResponse(BaseModel):
    """Tenant-safe deployment state for authenticated management selection."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    public_projection_id: UUID
    name: str
    hourly_request_limit: int
    disabled_at: datetime | None
    source_revoked_at: datetime | None
    created_at: datetime
    allowed_origins: list[str]
    publishable: bool


def _response(item: DiscoveredWidgetDeployment) -> WidgetDeploymentDiscoveryResponse:
    deployment = item.deployment
    return WidgetDeploymentDiscoveryResponse(
        id=deployment.id,
        public_projection_id=deployment.public_projection_id,
        name=deployment.name,
        hourly_request_limit=deployment.hourly_request_limit,
        disabled_at=deployment.disabled_at,
        source_revoked_at=item.source_revoked_at,
        created_at=deployment.created_at,
        allowed_origins=[origin.origin for origin in item.allowed_origins],
        publishable=item.publishable,
    )


@router.get("", response_model=list[WidgetDeploymentDiscoveryResponse])
def discover_widget_deployments(
    organization_id: UUID,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    session: Annotated[Session, Depends(get_database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WidgetDeploymentDiscoveryResponse]:
    """List tenant deployments, including disabled/revoked state, for safe operator choice."""

    try:
        discovered = list_widget_deployments(
            session,
            identity=identity,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )
    except WidgetAccessDenied as exc:
        raise HTTPException(status_code=403, detail="widget access denied") from exc
    return [_response(item) for item in discovered]
