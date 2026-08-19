"""Create versioned rule and official-source provenance tables.

Revision ID: 0002_rules_engine_foundation
Revises: 0001_tenant_core
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_rules_engine_foundation"
down_revision: str | None = "0001_tenant_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rule_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("authority", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        sa.Column("official_reference", sa.String(length=200), nullable=True),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('law', 'regulation', 'communique', 'decision', "
            "'circular', 'official_guidance', 'official_calendar', 'official_dataset')",
            name="ck_rule_source_type",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_rule_source_sha256_length",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_url",
            "content_sha256",
            name="uq_rule_source_url_hash",
        ),
    )

    op.create_table(
        "rule_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=2), nullable=False),
        sa.Column("code", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("value_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value_kind IN ('decimal', 'money', 'bands', 'structured', 'boolean', 'text')",
            name="ck_rule_definition_value_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "jurisdiction",
            "code",
            name="uq_rule_definition_jurisdiction_code",
        ),
    )

    op.create_table(
        "rule_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_definition_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("applicability", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_rule_version_revision_positive",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_rule_version_effective_range",
        ),
        sa.CheckConstraint(
            "length(payload_sha256) = 64",
            name="ck_rule_version_payload_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["rule_definition_id"],
            ["rule_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["rule_sources.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_definition_id",
            "revision",
            name="uq_rule_version_definition_revision",
        ),
    )
    op.create_index(
        "ix_rule_version_definition_effective",
        "rule_versions",
        ["rule_definition_id", "effective_from", "effective_to"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rule_version_definition_effective",
        table_name="rule_versions",
    )
    op.drop_table("rule_versions")
    op.drop_table("rule_definitions")
    op.drop_table("rule_sources")
