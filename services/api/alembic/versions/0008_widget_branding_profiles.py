"""Add tenant branding drafts and immutable widget presentation snapshots.

Revision ID: 0008_widget_branding_profiles
Revises: 0007_widget_domain_security
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_widget_branding_profiles"
down_revision: str | None = "0007_widget_domain_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _presentation_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("theme", sa.String(length=16), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("density", sa.String(length=24), nullable=False),
        sa.Column("show_title", sa.Boolean(), nullable=False),
        sa.Column("light_background_color", sa.String(length=7), nullable=False),
        sa.Column("light_text_color", sa.String(length=7), nullable=False),
        sa.Column("light_border_color", sa.String(length=7), nullable=False),
        sa.Column("dark_background_color", sa.String(length=7), nullable=False),
        sa.Column("dark_text_color", sa.String(length=7), nullable=False),
        sa.Column("dark_border_color", sa.String(length=7), nullable=False),
        sa.Column("error_color", sa.String(length=7), nullable=False),
        sa.Column("border_radius_px", sa.Integer(), nullable=False),
        sa.Column("font_family", sa.String(length=24), nullable=False),
    )


def _presentation_constraints(prefix: str) -> tuple[sa.CheckConstraint, ...]:
    return (
        sa.CheckConstraint(
            "theme IN ('auto', 'light', 'dark')",
            name=f"ck_{prefix}_theme",
        ),
        sa.CheckConstraint(
            "locale IN ('tr', 'en')",
            name=f"ck_{prefix}_locale",
        ),
        sa.CheckConstraint(
            "density IN ('comfortable', 'compact')",
            name=f"ck_{prefix}_density",
        ),
        sa.CheckConstraint(
            "font_family IN ('system', 'sans', 'serif', 'monospace')",
            name=f"ck_{prefix}_font_family",
        ),
        sa.CheckConstraint(
            "border_radius_px >= 0 AND border_radius_px <= 32",
            name=f"ck_{prefix}_radius",
        ),
        sa.CheckConstraint(
            "light_background_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_light_bg",
        ),
        sa.CheckConstraint(
            "light_text_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_light_text",
        ),
        sa.CheckConstraint(
            "light_border_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_light_border",
        ),
        sa.CheckConstraint(
            "dark_background_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_dark_bg",
        ),
        sa.CheckConstraint(
            "dark_text_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_dark_text",
        ),
        sa.CheckConstraint(
            "dark_border_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_dark_border",
        ),
        sa.CheckConstraint(
            "error_color ~ '^#[0-9A-F]{6}$'",
            name=f"ck_{prefix}_error_color",
        ),
    )


def upgrade() -> None:
    """Create mutable tenant drafts, immutable snapshots and one active pointer per deployment."""

    op.create_table(
        "widget_branding_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *_presentation_columns(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_presentation_constraints("widget_brand_profile"),
        sa.CheckConstraint("revision > 0", name="ck_widget_brand_profile_revision"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_widget_branding_profiles_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_brand_profile_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_brand_profile_updater",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_widget_branding_profiles"),
        sa.UniqueConstraint("id", "organization_id", name="uq_widget_brand_profile_id_org"),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            name="uq_widget_brand_profile_org_name",
        ),
    )
    op.create_index(
        "ix_widget_brand_profile_org_created",
        "widget_branding_profiles",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "widget_presentation_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("branding_profile_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        *_presentation_columns(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_presentation_constraints("widget_present_snapshot"),
        sa.CheckConstraint(
            "profile_revision > 0",
            name="ck_widget_present_snapshot_revision",
        ),
        sa.ForeignKeyConstraint(
            ["branding_profile_id", "organization_id"],
            ["widget_branding_profiles.id", "widget_branding_profiles.organization_id"],
            name="fk_widget_present_snapshot_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_present_snapshot_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_widget_presentation_snapshots"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            name="uq_widget_present_snapshot_id_org",
        ),
    )
    op.create_index(
        "ix_widget_present_snapshot_profile",
        "widget_presentation_snapshots",
        ["branding_profile_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "widget_published_presentations",
        sa.Column("widget_deployment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("presentation_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["widget_deployment_id", "organization_id"],
            ["widget_deployments.id", "widget_deployments.organization_id"],
            name="fk_widget_published_present_deploy",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_snapshot_id", "organization_id"],
            ["widget_presentation_snapshots.id", "widget_presentation_snapshots.organization_id"],
            name="fk_widget_published_present_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "published_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_published_present_actor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "widget_deployment_id",
            name="pk_widget_published_presentations",
        ),
        sa.UniqueConstraint(
            "presentation_snapshot_id",
            name="uq_widget_published_present_snapshot",
        ),
    )
    op.create_index(
        "ix_widget_published_present_org_time",
        "widget_published_presentations",
        ["organization_id", "published_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove widget presentation publication state in dependency-safe reverse order."""

    op.drop_index(
        "ix_widget_published_present_org_time",
        table_name="widget_published_presentations",
    )
    op.drop_table("widget_published_presentations")
    op.drop_index(
        "ix_widget_present_snapshot_profile",
        table_name="widget_presentation_snapshots",
    )
    op.drop_table("widget_presentation_snapshots")
    op.drop_index(
        "ix_widget_brand_profile_org_created",
        table_name="widget_branding_profiles",
    )
    op.drop_table("widget_branding_profiles")
