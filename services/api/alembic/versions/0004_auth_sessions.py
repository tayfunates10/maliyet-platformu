"""Add opaque authenticated user sessions.

Revision ID: 0004_auth_sessions
Revises: 0003_calc_version_provenance
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_auth_sessions"
down_revision: str | None = "0003_calc_version_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create server-side opaque sessions without storing raw bearer tokens."""

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(token_sha256) = 64",
            name="ck_auth_session_token_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_session_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_sha256", name="uq_auth_session_token_sha256"),
    )
    op.create_index("ix_auth_session_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_index(
        "ix_auth_session_expires_at",
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove opaque authenticated sessions."""

    op.drop_index("ix_auth_session_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_session_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
