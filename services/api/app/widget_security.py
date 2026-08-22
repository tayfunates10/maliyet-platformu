"""Browser widget domain lock and atomic usage enforcement.

Origin allowlisting controls browser embedding; it is not authentication because
non-browser clients can forge the Origin header. The widget therefore resolves
only a customer-safe PublicCalculationProjection and never a private calculation
snapshot or raw publication share token.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import idna
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity, AuthorizationError, resolve_actor_context
from app.models import (
    AuditEvent,
    PublicCalculationProjection,
    WidgetAllowedOrigin,
    WidgetDeployment,
    WidgetUsageBucket,
)

WIDGET_ADMIN_ROLES = frozenset({"owner", "admin"})
MAX_ALLOWED_ORIGINS = 20
MAX_ORIGIN_LENGTH = 512
MAX_HOURLY_REQUEST_LIMIT = 100000


class WidgetAccessDenied(PermissionError):
    """Raised when a tenant actor may not manage widget integration settings."""


class WidgetValidationError(ValueError):
    """Raised when deployment or origin configuration violates the contract."""


class WidgetProjectionNotFound(LookupError):
    """Raised when a tenant-safe source projection cannot be deployed."""


class WidgetDeploymentNotFound(LookupError):
    """Raised when a deployment is missing, disabled or no longer publishable."""


class WidgetOriginDenied(PermissionError):
    """Raised when a browser Origin header is missing, malformed or not allowlisted."""


class WidgetQuotaExceeded(RuntimeError):
    """Raised when the atomic request bucket has reached its configured limit."""

    def __init__(
        self,
        *,
        reset_at: datetime,
        canonical_origin: str,
        request_limit: int,
    ) -> None:
        super().__init__("widget request quota exceeded")
        self.reset_at = reset_at
        self.canonical_origin = canonical_origin
        self.request_limit = request_limit


@dataclass(frozen=True)
class WidgetConsumption:
    """One authorized widget projection read and its rate-limit metadata."""

    projection: PublicCalculationProjection
    canonical_origin: str
    request_limit: int
    request_count: int
    remaining: int
    reset_at: datetime


def normalize_https_origin(raw_origin: str) -> str:
    """Normalize one exact HTTPS DNS origin using browser-compatible UTS #46 IDNA."""

    candidate = raw_origin.strip()
    if not candidate or len(candidate) > MAX_ORIGIN_LENGTH:
        raise WidgetValidationError("origin is required and must not exceed 512 characters")
    if "*" in candidate:
        raise WidgetValidationError("wildcard origins are not allowed")

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise WidgetValidationError("origin is malformed") from exc

    if parsed.scheme.lower() != "https":
        raise WidgetValidationError("origin must use https")
    if parsed.username is not None or parsed.password is not None:
        raise WidgetValidationError("origin credentials are not allowed")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise WidgetValidationError("origin must not contain a path, query or fragment")
    hostname = parsed.hostname
    if hostname is None or hostname.endswith("."):
        raise WidgetValidationError("origin must contain a canonical DNS hostname")

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            canonical_host = idna.encode(hostname, uts46=True).decode("ascii").lower()
        except idna.IDNAError as exc:
            raise WidgetValidationError("origin hostname is invalid") from exc
    else:
        raise WidgetValidationError("IP-literal widget origins are not allowed")

    if "." not in canonical_host or not canonical_host.strip("."):
        raise WidgetValidationError("origin must use a fully qualified DNS hostname")
    if port is None or port == 443:
        return f"https://{canonical_host}"
    return f"https://{canonical_host}:{port}"


def _require_widget_admin(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
) -> UUID:
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
    return actor.user_id


def _validated_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or len(normalized) > 160:
        raise WidgetValidationError("widget deployment name must be between 1 and 160 characters")
    return normalized


def _validated_request_limit(value: int) -> int:
    if isinstance(value, bool) or value < 1 or value > MAX_HOURLY_REQUEST_LIMIT:
        raise WidgetValidationError(
            f"hourly request limit must be between 1 and {MAX_HOURLY_REQUEST_LIMIT}"
        )
    return value


def _normalized_origin_set(origins: list[str]) -> tuple[str, ...]:
    if not origins or len(origins) > MAX_ALLOWED_ORIGINS:
        raise WidgetValidationError(
            f"between 1 and {MAX_ALLOWED_ORIGINS} allowed origins are required"
        )
    normalized = tuple(normalize_https_origin(origin) for origin in origins)
    if len(set(normalized)) != len(normalized):
        raise WidgetValidationError("duplicate allowed origins are not permitted")
    return normalized


def _active_projection(
    session: Session,
    *,
    organization_id: UUID,
    projection_id: UUID,
) -> PublicCalculationProjection:
    projection = session.scalar(
        select(PublicCalculationProjection).where(
            PublicCalculationProjection.id == projection_id,
            PublicCalculationProjection.organization_id == organization_id,
            PublicCalculationProjection.revoked_at.is_(None),
        )
    )
    if projection is None:
        raise WidgetProjectionNotFound("public projection not found")
    return projection


def create_widget_deployment(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    public_projection_id: UUID,
    name: str,
    hourly_request_limit: int,
    allowed_origins: list[str],
) -> tuple[WidgetDeployment, tuple[WidgetAllowedOrigin, ...]]:
    """Create one widget deployment and its initial exact-origin registry atomically."""

    actor_user_id = _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    _active_projection(
        session,
        organization_id=organization_id,
        projection_id=public_projection_id,
    )
    normalized_name = _validated_name(name)
    request_limit = _validated_request_limit(hourly_request_limit)
    normalized_origins = _normalized_origin_set(allowed_origins)

    deployment = WidgetDeployment(
        organization_id=organization_id,
        public_projection_id=public_projection_id,
        created_by_user_id=actor_user_id,
        name=normalized_name,
        hourly_request_limit=request_limit,
    )
    session.add(deployment)
    session.flush()
    origin_rows = tuple(
        WidgetAllowedOrigin(
            organization_id=organization_id,
            widget_deployment_id=deployment.id,
            created_by_user_id=actor_user_id,
            origin=origin,
        )
        for origin in normalized_origins
    )
    session.add_all(origin_rows)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="widget_deployment.created",
            entity_type="widget_deployment",
            entity_id=deployment.id,
            payload={
                "public_projection_id": str(public_projection_id),
                "hourly_request_limit": request_limit,
                "allowed_origins": list(normalized_origins),
            },
        )
    )
    session.flush()
    return deployment, origin_rows


def add_widget_allowed_origin(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    deployment_id: UUID,
    origin: str,
) -> WidgetAllowedOrigin:
    """Add one exact origin to an active tenant deployment."""

    actor_user_id = _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    deployment = session.scalar(
        select(WidgetDeployment)
        .where(
            WidgetDeployment.id == deployment_id,
            WidgetDeployment.organization_id == organization_id,
            WidgetDeployment.disabled_at.is_(None),
        )
        .with_for_update()
    )
    if deployment is None:
        raise WidgetDeploymentNotFound("widget deployment not found")
    canonical_origin = normalize_https_origin(origin)
    existing = session.scalar(
        select(WidgetAllowedOrigin.id).where(
            WidgetAllowedOrigin.widget_deployment_id == deployment_id,
            WidgetAllowedOrigin.organization_id == organization_id,
            WidgetAllowedOrigin.origin == canonical_origin,
        )
    )
    if existing is not None:
        raise WidgetValidationError("origin is already allowed")
    origin_count = session.scalar(
        select(func.count())
        .select_from(WidgetAllowedOrigin)
        .where(
            WidgetAllowedOrigin.widget_deployment_id == deployment_id,
            WidgetAllowedOrigin.organization_id == organization_id,
        )
    )
    if origin_count is None or origin_count >= MAX_ALLOWED_ORIGINS:
        raise WidgetValidationError("allowed origin limit reached")

    row = WidgetAllowedOrigin(
        organization_id=organization_id,
        widget_deployment_id=deployment_id,
        created_by_user_id=actor_user_id,
        origin=canonical_origin,
    )
    session.add(row)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="widget_origin.added",
            entity_type="widget_allowed_origin",
            entity_id=row.id,
            payload={"widget_deployment_id": str(deployment_id), "origin": canonical_origin},
        )
    )
    session.flush()
    return row


def remove_widget_allowed_origin(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    deployment_id: UUID,
    origin_id: UUID,
) -> None:
    """Remove one tenant-owned origin; the change takes effect for the next request."""

    actor_user_id = _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    deployment = session.scalar(
        select(WidgetDeployment)
        .where(
            WidgetDeployment.id == deployment_id,
            WidgetDeployment.organization_id == organization_id,
        )
        .with_for_update()
    )
    if deployment is None:
        raise WidgetDeploymentNotFound("widget deployment not found")
    origin = session.scalar(
        select(WidgetAllowedOrigin).where(
            WidgetAllowedOrigin.id == origin_id,
            WidgetAllowedOrigin.widget_deployment_id == deployment_id,
            WidgetAllowedOrigin.organization_id == organization_id,
        )
    )
    if origin is None:
        raise WidgetDeploymentNotFound("widget allowed origin not found")
    canonical_origin = origin.origin
    session.execute(
        delete(WidgetAllowedOrigin).where(
            WidgetAllowedOrigin.id == origin_id,
            WidgetAllowedOrigin.organization_id == organization_id,
        )
    )
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="widget_origin.removed",
            entity_type="widget_allowed_origin",
            entity_id=origin_id,
            payload={"widget_deployment_id": str(deployment_id), "origin": canonical_origin},
        )
    )
    session.flush()


def disable_widget_deployment(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    deployment_id: UUID,
    now: datetime | None = None,
) -> None:
    """Disable one deployment idempotently while preserving history and usage buckets."""

    actor_user_id = _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    deployment = session.scalar(
        select(WidgetDeployment)
        .where(
            WidgetDeployment.id == deployment_id,
            WidgetDeployment.organization_id == organization_id,
        )
        .with_for_update()
    )
    if deployment is None:
        raise WidgetDeploymentNotFound("widget deployment not found")
    if deployment.disabled_at is not None:
        return
    disabled_at = now or datetime.now(UTC)
    if disabled_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    deployment.disabled_at = disabled_at
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="widget_deployment.disabled",
            entity_type="widget_deployment",
            entity_id=deployment_id,
            payload={},
        )
    )
    session.flush()


def _request_origin(raw_origin: str | None) -> str:
    if raw_origin is None or raw_origin == "null":
        raise WidgetOriginDenied("widget origin denied")
    try:
        return normalize_https_origin(raw_origin)
    except WidgetValidationError as exc:
        raise WidgetOriginDenied("widget origin denied") from exc


def _reserve_usage(
    session: Session,
    *,
    deployment: WidgetDeployment,
    canonical_origin: str,
    checked_at: datetime,
) -> tuple[int, datetime]:
    bucket_start = checked_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    reset_at = bucket_start + timedelta(hours=1)
    statement = (
        pg_insert(WidgetUsageBucket)
        .values(
            id=uuid4(),
            organization_id=deployment.organization_id,
            widget_deployment_id=deployment.id,
            bucket_start=bucket_start,
            request_count=1,
        )
        .on_conflict_do_update(
            constraint="uq_widget_usage_deployment_start",
            set_={"request_count": WidgetUsageBucket.request_count + 1},
            where=WidgetUsageBucket.request_count < deployment.hourly_request_limit,
        )
        .returning(WidgetUsageBucket.request_count)
    )
    request_count = session.scalar(statement)
    if request_count is None:
        raise WidgetQuotaExceeded(
            reset_at=reset_at,
            canonical_origin=canonical_origin,
            request_limit=deployment.hourly_request_limit,
        )
    return request_count, reset_at


def consume_widget_projection(
    session: Session,
    *,
    deployment_id: UUID,
    raw_origin: str | None,
    now: datetime | None = None,
) -> WidgetConsumption:
    """Authorize an exact browser origin and atomically reserve one usage unit."""

    checked_at = now or datetime.now(UTC)
    if checked_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    canonical_origin = _request_origin(raw_origin)
    deployment = session.scalar(
        select(WidgetDeployment).where(
            WidgetDeployment.id == deployment_id,
            WidgetDeployment.disabled_at.is_(None),
        )
    )
    if deployment is None:
        raise WidgetDeploymentNotFound("widget deployment not found")
    projection = session.scalar(
        select(PublicCalculationProjection).where(
            PublicCalculationProjection.id == deployment.public_projection_id,
            PublicCalculationProjection.organization_id == deployment.organization_id,
            PublicCalculationProjection.revoked_at.is_(None),
        )
    )
    if projection is None:
        raise WidgetDeploymentNotFound("widget deployment not found")
    allowed = session.scalar(
        select(WidgetAllowedOrigin.id).where(
            WidgetAllowedOrigin.widget_deployment_id == deployment.id,
            WidgetAllowedOrigin.organization_id == deployment.organization_id,
            WidgetAllowedOrigin.origin == canonical_origin,
        )
    )
    if allowed is None:
        raise WidgetOriginDenied("widget origin denied")

    request_count, reset_at = _reserve_usage(
        session,
        deployment=deployment,
        canonical_origin=canonical_origin,
        checked_at=checked_at,
    )
    return WidgetConsumption(
        projection=projection,
        canonical_origin=canonical_origin,
        request_limit=deployment.hourly_request_limit,
        request_count=request_count,
        remaining=max(deployment.hourly_request_limit - request_count, 0),
        reset_at=reset_at,
    )
