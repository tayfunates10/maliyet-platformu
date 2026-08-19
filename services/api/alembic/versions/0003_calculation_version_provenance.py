"""Add replay provenance and snapshot-integrity fields to calculation versions.

Revision ID: 0003_calculation_version_provenance
Revises: 0002_rules_engine_foundation
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_calculation_version_provenance"
down_revision: str | None = "0002_rules_engine_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable provenance columns without fabricating metadata for legacy rows."""

    op.add_column(
        "calculation_versions",
        sa.Column("engine_key", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "calculation_versions",
        sa.Column("input_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "calculation_versions",
        sa.Column("ruleset_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "calculation_versions",
        sa.Column("output_sha256", sa.String(length=64), nullable=True),
    )

    op.create_check_constraint(
        "ck_calculation_version_input_sha256_length",
        "calculation_versions",
        "input_sha256 IS NULL OR length(input_sha256) = 64",
    )
    op.create_check_constraint(
        "ck_calculation_version_ruleset_sha256_length",
        "calculation_versions",
        "ruleset_sha256 IS NULL OR length(ruleset_sha256) = 64",
    )
    op.create_check_constraint(
        "ck_calculation_version_output_sha256_length",
        "calculation_versions",
        "output_sha256 IS NULL OR length(output_sha256) = 64",
    )


def downgrade() -> None:
    """Remove calculation-version provenance columns and constraints."""

    op.drop_constraint(
        "ck_calculation_version_output_sha256_length",
        "calculation_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_calculation_version_ruleset_sha256_length",
        "calculation_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_calculation_version_input_sha256_length",
        "calculation_versions",
        type_="check",
    )
    op.drop_column("calculation_versions", "output_sha256")
    op.drop_column("calculation_versions", "ruleset_sha256")
    op.drop_column("calculation_versions", "input_sha256")
    op.drop_column("calculation_versions", "engine_key")
