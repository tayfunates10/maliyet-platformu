"""Authenticated tenant discovery for widget deployments used by management workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity, AuthorizationError, resolve_actor_context
from app.models import PublicCalculationProjection, WidgetAllowedOrigin, WidgetDeployment
from app.widget_security import WIDGET_ADMIN_ROLES, WidgetAccessDenied


@dataclass(frozen=True)
class DiscoveredWidgetDeployment:
    """Tenant-safe deployment management state without public tokens or private calculations."""

    deployment: WidgetDeployment
    allowed_origins: tuple[WidgetAllowedOrigin, ...]
    source_revoked_at: datetime | None

    @property
    def publishable(self) -> bool:
        """Whether current persisted state can pass the presentation publish preconditions."""

        return self.deployment.disabled_at is None and self.source_revoked_at is None


def _require_widget_admin(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
) -> None:
    try:
        actor = resolve_actor_context(
            session,
            identity=identity,
            organization_id=organization_id,
        )
    except AuthorizationError as exc:
        raise WidgetAccessDenied("widget access denied") from exc
    if actor.role not in WIDGET_ADMIN_ROLES:
        raise WidgetAccessDenied("widget access denied")


def list_widget_deployments(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> tuple[DiscoveredWidgetDeployment, ...]:
    """List one tenant's deployments including disabled/revoked state for safe operator choice."""

    _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    rows = session.execute(
        select(WidgetDeployment, PublicCalculationProjection.revoked_at)
        .join(
            PublicCalculationProjection,
            (PublicCalculationProjection.id == WidgetDeployment.public_projection_id)
            & (PublicCalculationProjection.organization_id == WidgetDeployment.organization_id),
        )
        .where(WidgetDeployment.organization_id == organization_id)
        .order_by(WidgetDeployment.created_at.desc(), WidgetDeployment.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    if not rows:
        return ()

    deployment_ids = tuple(row[0].id for row in rows)
    origins = session.scalars(
        select(WidgetAllowedOrigin)
        .where(
            WidgetAllowedOrigin.organization_id == organization_id,
            WidgetAllowedOrigin.widget_deployment_id.in_(deployment_ids),
        )
        .order_by(
            WidgetAllowedOrigin.widget_deployment_id,
            WidgetAllowedOrigin.created_at,
            WidgetAllowedOrigin.id,
        )
    ).all()
    origins_by_deployment: dict[UUID, list[WidgetAllowedOrigin]] = {
        deployment_id: [] for deployment_id in deployment_ids
    }
    for origin in origins:
        origins_by_deployment[origin.widget_deployment_id].append(origin)

    return tuple(
        DiscoveredWidgetDeployment(
            deployment=deployment,
            allowed_origins=tuple(origins_by_deployment[deployment.id]),
            source_revoked_at=source_revoked_at,
        )
        for deployment, source_revoked_at in rows
    )
