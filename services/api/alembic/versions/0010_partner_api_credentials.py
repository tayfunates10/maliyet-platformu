"""Add tenant-scoped partner API credentials.

Revision ID: 0010_partner_api_credentials
Revises: 0009_decision_artifacts
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_partner_api_credentials"
down_revision = "0009_decision_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_api_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(token_sha256) = 64",
            name="ck_partner_api_credential_token_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_partner_api_credential_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_sha256"),
    )
    op.create_index(
        "ix_partner_api_credential_org_created",
        "partner_api_credentials",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_partner_api_credential_org_created",
        table_name="partner_api_credentials",
    )
    op.drop_table("partner_api_credentials")
