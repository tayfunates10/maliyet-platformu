"""Add tenant-bound widget deployments, exact origins and usage buckets.

Revision ID: 0007_widget_domain_security
Revises: 0006_public_projection
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_widget_domain_security"
down_revision: str | None = "0006_public_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the browser widget origin and atomic quota security boundary."""

    op.create_unique_constraint(
        "uq_public_projection_id_org",
        "public_calculation_projections",
        ["id", "organization_id"],
    )
    op.create_table(
        "widget_deployments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("public_projection_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("hourly_request_limit", sa.Integer(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "hourly_request_limit >= 1 AND hourly_request_limit <= 100000",
            name="ck_widget_deployment_hourly_limit",
        ),
        sa.ForeignKeyConstraint(
            ["public_projection_id", "organization_id"],
            ["public_calculation_projections.id", "public_calculation_projections.organization_id"],
            name="fk_widget_deployment_projection_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_deployment_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_widget_deployments"),
        sa.UniqueConstraint("id", "organization_id", name="uq_widget_deployment_id_org"),
    )
    op.create_index(
        "ix_widget_deployment_org_created",
        "widget_deployments",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_widget_deployment_projection",
        "widget_deployments",
        ["public_projection_id"],
        unique=False,
    )

    op.create_table(
        "widget_allowed_origins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("widget_deployment_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["widget_deployment_id", "organization_id"],
            ["widget_deployments.id", "widget_deployments.organization_id"],
            name="fk_widget_origin_deployment_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_origin_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_widget_allowed_origins"),
        sa.UniqueConstraint(
            "widget_deployment_id",
            "origin",
            name="uq_widget_origin_deployment_origin",
        ),
    )
    op.create_index(
        "ix_widget_origin_org_deployment",
        "widget_allowed_origins",
        ["organization_id", "widget_deployment_id"],
        unique=False,
    )

    op.create_table(
        "widget_usage_buckets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("widget_deployment_id", sa.Uuid(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("request_count >= 0", name="ck_widget_usage_request_count"),
        sa.ForeignKeyConstraint(
            ["widget_deployment_id", "organization_id"],
            ["widget_deployments.id", "widget_deployments.organization_id"],
            name="fk_widget_usage_deployment_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_widget_usage_buckets"),
        sa.UniqueConstraint(
            "widget_deployment_id",
            "bucket_start",
            name="uq_widget_usage_deployment_start",
        ),
    )
    op.create_index(
        "ix_widget_usage_org_bucket",
        "widget_usage_buckets",
        ["organization_id", "bucket_start"],
        unique=False,
    )


def downgrade() -> None:
    """Remove widget deployment security state and supporting source key."""

    op.drop_index("ix_widget_usage_org_bucket", table_name="widget_usage_buckets")
    op.drop_table("widget_usage_buckets")
    op.drop_index("ix_widget_origin_org_deployment", table_name="widget_allowed_origins")
    op.drop_table("widget_allowed_origins")
    op.drop_index("ix_widget_deployment_projection", table_name="widget_deployments")
    op.drop_index("ix_widget_deployment_org_created", table_name="widget_deployments")
    op.drop_table("widget_deployments")
    op.drop_constraint(
        "uq_public_projection_id_org",
        "public_calculation_projections",
        type_="unique",
    )
