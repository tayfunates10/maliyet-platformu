"""Add immutable customer-safe calculation publication artifacts.

Revision ID: 0006_public_projection
Revises: 0005_user_credentials
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_public_projection"
down_revision: str | None = "0005_user_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenant-bound public projections without exposing source snapshots."""

    op.create_unique_constraint(
        "uq_calculation_version_id_org",
        "calculation_versions",
        ["id", "organization_id"],
    )
    op.create_table(
        "public_calculation_projections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("calculation_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("estimate_min", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("estimate_max", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(token_sha256) = 64",
            name="ck_public_projection_token_sha256_length",
        ),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_public_projection_currency",
        ),
        sa.CheckConstraint(
            "estimate_min >= 0",
            name="ck_public_projection_estimate_min_non_negative",
        ),
        sa.CheckConstraint(
            "estimate_max >= estimate_min",
            name="ck_public_projection_estimate_range",
        ),
        sa.ForeignKeyConstraint(
            ["calculation_version_id", "organization_id"],
            ["calculation_versions.id", "calculation_versions.organization_id"],
            name="fk_public_projection_version_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_public_projection_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_calculation_projections"),
        sa.UniqueConstraint("token_sha256", name="uq_public_projection_token_sha256"),
    )
    op.create_index(
        "ix_public_projection_org_created",
        "public_calculation_projections",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_public_projection_version",
        "public_calculation_projections",
        ["calculation_version_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove public projections and the composite source-key support."""

    op.drop_index("ix_public_projection_version", table_name="public_calculation_projections")
    op.drop_index("ix_public_projection_org_created", table_name="public_calculation_projections")
    op.drop_table("public_calculation_projections")
    op.drop_constraint(
        "uq_calculation_version_id_org",
        "calculation_versions",
        type_="unique",
    )
