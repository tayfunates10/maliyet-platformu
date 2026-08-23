"""Tenant-owned immutable decision-analysis persistence models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class DecisionAnalysisArtifact(Base):
    """Append-only, tamper-evident investment/scenario analysis artifact."""

    __tablename__ = "decision_analysis_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_decision_artifact_creator_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_decision_artifact_id_org"),
        CheckConstraint(
            "length(input_sha256) = 64",
            name="ck_decision_artifact_input_sha256_length",
        ),
        CheckConstraint(
            "length(output_sha256) = 64",
            name="ck_decision_artifact_output_sha256_length",
        ),
        Index("ix_decision_artifact_org_created", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    output_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
