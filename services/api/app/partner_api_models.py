"""Tenant-scoped partner API credential persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, UUIDPrimaryKeyMixin


class PartnerApiCredential(UUIDPrimaryKeyMixin, Base):
    """Revocable tenant credential that stores only a SHA-256 token digest."""

    __tablename__ = "partner_api_credentials"
    __table_args__ = (
        CheckConstraint(
            "length(token_sha256) = 64",
            name="ck_partner_api_credential_token_sha256_length",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_partner_api_credential_creator_membership",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_partner_api_credential_org_created",
            "organization_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
