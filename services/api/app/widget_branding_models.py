"""Tenant-owned widget branding profiles and immutable public presentation snapshots."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _presentation_constraints(prefix: str) -> tuple[CheckConstraint, ...]:
    """Build identical storage validation for mutable profiles and immutable snapshots."""

    return (
        CheckConstraint(
            "theme IN ('auto', 'light', 'dark')",
            name=f"ck_{prefix}_theme",
        ),
        CheckConstraint(
            "locale IN ('tr', 'en')",
            name=f"ck_{prefix}_locale",
        ),
        CheckConstraint(
            "density IN ('comfortable', 'compact')",
            name=f"ck_{prefix}_density",
        ),
        CheckConstraint(
            "font_family IN ('system', 'sans', 'serif', 'monospace')",
            name=f"ck_{prefix}_font_family",
        ),
        CheckConstraint(
            "border_radius_px >= 0 AND border_radius_px <= 32",
            name=f"ck_{prefix}_radius",
        ),
        CheckConstraint(
            "light_background_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_light_bg",
        ),
        CheckConstraint(
            "light_text_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_light_text",
        ),
        CheckConstraint(
            "light_border_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_light_border",
        ),
        CheckConstraint(
            "dark_background_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_dark_bg",
        ),
        CheckConstraint(
            "dark_text_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_dark_text",
        ),
        CheckConstraint(
            "dark_border_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_dark_border",
        ),
        CheckConstraint(
            "error_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_error_color",
        ),
    )


class WidgetBrandingProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mutable tenant-owned presentation draft; never read directly by public widget clients."""

    __tablename__ = "widget_branding_profiles"
    __table_args__ = (
        *_presentation_constraints("widget_brand_profile"),
        CheckConstraint("revision > 0", name="ck_widget_brand_profile_revision"),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_brand_profile_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "updated_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_brand_profile_updater",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_widget_brand_profile_id_org"),
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_widget_brand_profile_org_name",
        ),
        Index(
            "ix_widget_brand_profile_org_created",
            "organization_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_widget_branding_profiles_organization_id_organizations",
        ),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    theme: Mapped[str] = mapped_column(String(16), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    density: Mapped[str] = mapped_column(String(24), nullable=False)
    show_title: Mapped[bool] = mapped_column(Boolean, nullable=False)
    light_background_color: Mapped[str] = mapped_column(String(7), nullable=False)
    light_text_color: Mapped[str] = mapped_column(String(7), nullable=False)
    light_border_color: Mapped[str] = mapped_column(String(7), nullable=False)
    dark_background_color: Mapped[str] = mapped_column(String(7), nullable=False)
    dark_text_color: Mapped[str] = mapped_column(String(7), nullable=False)
    dark_border_color: Mapped[str] = mapped_column(String(7), nullable=False)
    error_color: Mapped[str] = mapped_column(String(7), nullable=False)
    border_radius_px: Mapped[int] = mapped_column(Integer, nullable=False)
    font_family: Mapped[str] = mapped_column(String(24), nullable=False)


class WidgetPresentationSnapshot(UUIDPrimaryKeyMixin, Base):
    """Immutable copy of one branding-profile revision approved for public publication."""

    __tablename__ = "widget_presentation_snapshots"
    __table_args__ = (
        *_presentation_constraints("widget_present_snapshot"),
        CheckConstraint("profile_revision > 0", name="ck_widget_present_snapshot_revision"),
        ForeignKeyConstraint(
            ["branding_profile_id", "organization_id"],
            ["widget_branding_profiles.id", "widget_branding_profiles.organization_id"],
            name="fk_widget_present_snapshot_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_present_snapshot_creator",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_widget_present_snapshot_id_org"),
        Index(
            "ix_widget_present_snapshot_profile",
            "branding_profile_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    branding_profile_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    theme: Mapped[str] = mapped_column(String(16), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    density: Mapped[str] = mapped_column(String(24), nullable=False)
    show_title: Mapped[bool] = mapped_column(Boolean, nullable=False)
    light_background_color: Mapped[str] = mapped_column(String(7), nullable=False)
    light_text_color: Mapped[str] = mapped_column(String(7), nullable=False)
    light_border_color: Mapped[str] = mapped_column(String(7), nullable=False)
    dark_background_color: Mapped[str] = mapped_column(String(7), nullable=False)
    dark_text_color: Mapped[str] = mapped_column(String(7), nullable=False)
    dark_border_color: Mapped[str] = mapped_column(String(7), nullable=False)
    error_color: Mapped[str] = mapped_column(String(7), nullable=False)
    border_radius_px: Mapped[int] = mapped_column(Integer, nullable=False)
    font_family: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WidgetPublishedPresentation(Base):
    """Mutable deployment pointer to one immutable, same-tenant presentation snapshot."""

    __tablename__ = "widget_published_presentations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["widget_deployment_id", "organization_id"],
            ["widget_deployments.id", "widget_deployments.organization_id"],
            name="fk_widget_published_present_deploy",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["presentation_snapshot_id", "organization_id"],
            ["widget_presentation_snapshots.id", "widget_presentation_snapshots.organization_id"],
            name="fk_widget_published_present_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "published_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_published_present_actor",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "presentation_snapshot_id",
            name="uq_widget_published_present_snapshot",
        ),
        Index(
            "ix_widget_published_present_org_time",
            "organization_id",
            "published_at",
        ),
    )

    widget_deployment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    presentation_snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    published_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
