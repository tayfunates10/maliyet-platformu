"""Tenant-owned widget branding drafts and immutable publication snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import AuthenticatedIdentity, AuthorizationError, resolve_actor_context
from app.models import AuditEvent, WidgetDeployment
from app.widget_branding_models import (
    WidgetBrandingProfile,
    WidgetPresentationSnapshot,
    WidgetPublishedPresentation,
)
from app.widget_security import WIDGET_ADMIN_ROLES, WidgetAccessDenied, WidgetDeploymentNotFound

SUPPORTED_WIDGET_THEMES = frozenset({"auto", "light", "dark"})
SUPPORTED_WIDGET_LOCALES = frozenset({"tr", "en"})
SUPPORTED_WIDGET_DENSITIES = frozenset({"comfortable", "compact"})
SUPPORTED_WIDGET_FONT_FAMILIES = frozenset({"system", "sans", "serif", "monospace"})
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

DEFAULT_LIGHT_BACKGROUND = "#FFFFFF"
DEFAULT_LIGHT_TEXT = "#17202A"
DEFAULT_LIGHT_BORDER = "#D7DCE3"
DEFAULT_DARK_BACKGROUND = "#151A21"
DEFAULT_DARK_TEXT = "#F5F7FA"
DEFAULT_DARK_BORDER = "#343B46"
DEFAULT_ERROR_COLOR = "#8B1E1E"
DEFAULT_BORDER_RADIUS_PX = 12


class WidgetBrandingValidationError(ValueError):
    """Raised when tenant presentation configuration is outside the safe allowlist."""


class WidgetBrandingNotFound(LookupError):
    """Raised when a tenant-owned branding profile does not exist."""


@dataclass(frozen=True)
class WidgetPresentationValues:
    """Strict presentation values that can be copied into an immutable public snapshot."""

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


@dataclass(frozen=True)
class WidgetPresentationPublication:
    """Resolved immutable snapshot plus the time it became active for one deployment."""

    snapshot: WidgetPresentationSnapshot
    published_at: datetime


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
        raise WidgetBrandingValidationError(
            "widget branding profile name must be between 1 and 160 characters"
        )
    return normalized


def _validated_enum(value: str, allowed: frozenset[str], field_name: str) -> str:
    if value not in allowed:
        raise WidgetBrandingValidationError(f"unsupported widget {field_name}")
    return value


def _validated_color(value: str, field_name: str) -> str:
    normalized = value.strip().upper()
    if _HEX_COLOR.fullmatch(normalized) is None:
        raise WidgetBrandingValidationError(f"{field_name} must use #RRGGBB format")
    return normalized


def validate_widget_presentation(
    *,
    theme: str,
    locale: str,
    density: str,
    show_title: bool,
    light_background_color: str,
    light_text_color: str,
    light_border_color: str,
    dark_background_color: str,
    dark_text_color: str,
    dark_border_color: str,
    error_color: str,
    border_radius_px: int,
    font_family: str,
) -> WidgetPresentationValues:
    """Reject arbitrary CSS/HTML-like inputs and normalize the bounded presentation surface."""

    if not isinstance(show_title, bool):
        raise WidgetBrandingValidationError("show_title must be a boolean")
    if isinstance(border_radius_px, bool) or not 0 <= border_radius_px <= 32:
        raise WidgetBrandingValidationError("border_radius_px must be between 0 and 32")
    return WidgetPresentationValues(
        theme=_validated_enum(theme, SUPPORTED_WIDGET_THEMES, "theme"),
        locale=_validated_enum(locale, SUPPORTED_WIDGET_LOCALES, "locale"),
        density=_validated_enum(density, SUPPORTED_WIDGET_DENSITIES, "density"),
        show_title=show_title,
        light_background_color=_validated_color(
            light_background_color,
            "light_background_color",
        ),
        light_text_color=_validated_color(light_text_color, "light_text_color"),
        light_border_color=_validated_color(light_border_color, "light_border_color"),
        dark_background_color=_validated_color(
            dark_background_color,
            "dark_background_color",
        ),
        dark_text_color=_validated_color(dark_text_color, "dark_text_color"),
        dark_border_color=_validated_color(dark_border_color, "dark_border_color"),
        error_color=_validated_color(error_color, "error_color"),
        border_radius_px=border_radius_px,
        font_family=_validated_enum(
            font_family,
            SUPPORTED_WIDGET_FONT_FAMILIES,
            "font_family",
        ),
    )


def _validated_values(values: WidgetPresentationValues) -> WidgetPresentationValues:
    return validate_widget_presentation(
        theme=values.theme,
        locale=values.locale,
        density=values.density,
        show_title=values.show_title,
        light_background_color=values.light_background_color,
        light_text_color=values.light_text_color,
        light_border_color=values.light_border_color,
        dark_background_color=values.dark_background_color,
        dark_text_color=values.dark_text_color,
        dark_border_color=values.dark_border_color,
        error_color=values.error_color,
        border_radius_px=values.border_radius_px,
        font_family=values.font_family,
    )


def _profile_values(profile: WidgetBrandingProfile) -> WidgetPresentationValues:
    return validate_widget_presentation(
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


def _apply_values(profile: WidgetBrandingProfile, values: WidgetPresentationValues) -> None:
    profile.theme = values.theme
    profile.locale = values.locale
    profile.density = values.density
    profile.show_title = values.show_title
    profile.light_background_color = values.light_background_color
    profile.light_text_color = values.light_text_color
    profile.light_border_color = values.light_border_color
    profile.dark_background_color = values.dark_background_color
    profile.dark_text_color = values.dark_text_color
    profile.dark_border_color = values.dark_border_color
    profile.error_color = values.error_color
    profile.border_radius_px = values.border_radius_px
    profile.font_family = values.font_family


def create_widget_branding_profile(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    name: str,
    presentation: WidgetPresentationValues,
) -> WidgetBrandingProfile:
    """Create one mutable tenant draft; it has no public effect until explicitly published."""

    actor_user_id = _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    presentation = _validated_values(presentation)
    profile = WidgetBrandingProfile(
        organization_id=organization_id,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
        name=_validated_name(name),
        revision=1,
        theme=presentation.theme,
        locale=presentation.locale,
        density=presentation.density,
        show_title=presentation.show_title,
        light_background_color=presentation.light_background_color,
        light_text_color=presentation.light_text_color,
        light_border_color=presentation.light_border_color,
        dark_background_color=presentation.dark_background_color,
        dark_text_color=presentation.dark_text_color,
        dark_border_color=presentation.dark_border_color,
        error_color=presentation.error_color,
        border_radius_px=presentation.border_radius_px,
        font_family=presentation.font_family,
    )
    session.add(profile)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="widget_branding_profile.created",
            entity_type="widget_branding_profile",
            entity_id=profile.id,
            payload={"revision": profile.revision},
        )
    )
    session.flush()
    return profile


def _tenant_profile_for_update(
    session: Session,
    *,
    organization_id: UUID,
    profile_id: UUID,
) -> WidgetBrandingProfile:
    profile = session.scalar(
        select(WidgetBrandingProfile)
        .where(
            WidgetBrandingProfile.id == profile_id,
            WidgetBrandingProfile.organization_id == organization_id,
        )
        .with_for_update()
    )
    if profile is None:
        raise WidgetBrandingNotFound("widget branding profile not found")
    return profile


def update_widget_branding_profile(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    profile_id: UUID,
    name: str,
    presentation: WidgetPresentationValues,
    now: datetime | None = None,
) -> WidgetBrandingProfile:
    """Replace one mutable tenant draft and advance its monotonic revision."""

    actor_user_id = _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    presentation = _validated_values(presentation)
    profile = _tenant_profile_for_update(
        session,
        organization_id=organization_id,
        profile_id=profile_id,
    )
    changed_at = now or datetime.now(UTC)
    if changed_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    profile.name = _validated_name(name)
    profile.updated_by_user_id = actor_user_id
    profile.revision += 1
    profile.updated_at = changed_at
    _apply_values(profile, presentation)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="widget_branding_profile.updated",
            entity_type="widget_branding_profile",
            entity_id=profile.id,
            payload={"revision": profile.revision},
        )
    )
    session.flush()
    return profile


def get_widget_branding_profile(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    profile_id: UUID,
) -> WidgetBrandingProfile:
    """Read one branding draft only after owner/admin tenant authorization."""

    _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    profile = session.scalar(
        select(WidgetBrandingProfile).where(
            WidgetBrandingProfile.id == profile_id,
            WidgetBrandingProfile.organization_id == organization_id,
        )
    )
    if profile is None:
        raise WidgetBrandingNotFound("widget branding profile not found")
    return profile


def list_widget_branding_profiles(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> tuple[WidgetBrandingProfile, ...]:
    """List mutable drafts only inside the authenticated owner/admin tenant boundary."""

    _require_widget_admin(
        session,
        identity=identity,
        organization_id=organization_id,
    )
    rows = session.scalars(
        select(WidgetBrandingProfile)
        .where(WidgetBrandingProfile.organization_id == organization_id)
        .order_by(
            WidgetBrandingProfile.created_at.desc(),
            WidgetBrandingProfile.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return tuple(rows)


def publish_widget_presentation(
    session: Session,
    *,
    identity: AuthenticatedIdentity,
    organization_id: UUID,
    deployment_id: UUID,
    branding_profile_id: UUID,
    now: datetime | None = None,
) -> WidgetPresentationPublication:
    """Copy one profile revision into an immutable snapshot and atomically activate it."""

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

    profile = _tenant_profile_for_update(
        session,
        organization_id=organization_id,
        profile_id=branding_profile_id,
    )
    values = _profile_values(profile)
    snapshot = WidgetPresentationSnapshot(
        organization_id=organization_id,
        branding_profile_id=profile.id,
        created_by_user_id=actor_user_id,
        profile_revision=profile.revision,
        theme=values.theme,
        locale=values.locale,
        density=values.density,
        show_title=values.show_title,
        light_background_color=values.light_background_color,
        light_text_color=values.light_text_color,
        light_border_color=values.light_border_color,
        dark_background_color=values.dark_background_color,
        dark_text_color=values.dark_text_color,
        dark_border_color=values.dark_border_color,
        error_color=values.error_color,
        border_radius_px=values.border_radius_px,
        font_family=values.font_family,
    )
    session.add(snapshot)
    session.flush()

    published_at = now or datetime.now(UTC)
    if published_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    pointer = session.scalar(
        select(WidgetPublishedPresentation)
        .where(
            WidgetPublishedPresentation.widget_deployment_id == deployment_id,
            WidgetPublishedPresentation.organization_id == organization_id,
        )
        .with_for_update()
    )
    if pointer is None:
        pointer = WidgetPublishedPresentation(
            widget_deployment_id=deployment_id,
            organization_id=organization_id,
            presentation_snapshot_id=snapshot.id,
            published_by_user_id=actor_user_id,
            published_at=published_at,
        )
        session.add(pointer)
    else:
        pointer.presentation_snapshot_id = snapshot.id
        pointer.published_by_user_id = actor_user_id
        pointer.published_at = published_at
    session.flush()

    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="widget_presentation.published",
            entity_type="widget_deployment",
            entity_id=deployment_id,
            payload={
                "branding_profile_id": str(profile.id),
                "presentation_snapshot_id": str(snapshot.id),
                "profile_revision": profile.revision,
            },
        )
    )
    session.flush()
    return WidgetPresentationPublication(snapshot=snapshot, published_at=published_at)


def get_published_widget_presentation(
    session: Session,
    *,
    deployment_id: UUID,
) -> WidgetPresentationPublication | None:
    """Resolve the already-authorized deployment's immutable public presentation, if any."""

    pointer = session.get(WidgetPublishedPresentation, deployment_id)
    if pointer is None:
        return None
    snapshot = session.scalar(
        select(WidgetPresentationSnapshot).where(
            WidgetPresentationSnapshot.id == pointer.presentation_snapshot_id,
            WidgetPresentationSnapshot.organization_id == pointer.organization_id,
        )
    )
    if snapshot is None:
        return None
    return WidgetPresentationPublication(snapshot=snapshot, published_at=pointer.published_at)
