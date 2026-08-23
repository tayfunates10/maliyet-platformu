"""Add immutable tenant decision-analysis artifacts.

Revision ID: 0009_decision_artifacts
Revises: 0008_widget_branding_profiles
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_decision_artifacts"
down_revision: str | None = "0008_widget_branding_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_analysis_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("engine_version", sa.String(length=80), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(input_sha256) = 64",
            name="ck_decision_artifact_input_sha256_length",
        ),
        sa.CheckConstraint(
            "length(output_sha256) = 64",
            name="ck_decision_artifact_output_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_decision_artifact_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "organization_id", name="uq_decision_artifact_id_org"),
    )
    op.create_index(
        "ix_decision_artifact_org_created",
        "decision_analysis_artifacts",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_decision_artifact_org_created",
        table_name="decision_analysis_artifacts",
    )
    op.drop_table("decision_analysis_artifacts")
