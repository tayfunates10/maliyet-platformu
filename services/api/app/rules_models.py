"""Persistence models for versioned, source-backed regulatory rules."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, UUIDPrimaryKeyMixin


class RuleSource(UUIDPrimaryKeyMixin, Base):
    """Immutable provenance identity for one retrieved official source revision."""

    __tablename__ = "rule_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('law', 'regulation', 'communique', 'decision', "
            "'circular', 'official_guidance', 'official_calendar', 'official_dataset')",
            name="ck_rule_source_type",
        ),
        CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_rule_source_sha256_length",
        ),
        UniqueConstraint(
            "canonical_url",
            "content_sha256",
            name="uq_rule_source_url_hash",
        ),
    )

    authority: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    official_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RuleDefinition(UUIDPrimaryKeyMixin, Base):
    """Stable logical identity for a rule whose values may change over time."""

    __tablename__ = "rule_definitions"
    __table_args__ = (
        CheckConstraint(
            "value_kind IN ('decimal', 'money', 'bands', 'structured', 'boolean', 'text')",
            name="ck_rule_definition_value_kind",
        ),
        UniqueConstraint(
            "jurisdiction",
            "code",
            name="uq_rule_definition_jurisdiction_code",
        ),
    )

    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False, default="TR")
    code: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RuleVersion(UUIDPrimaryKeyMixin, Base):
    """Effective-dated rule payload linked to exact official-source provenance."""

    __tablename__ = "rule_versions"
    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_rule_version_revision_positive"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_rule_version_effective_range",
        ),
        CheckConstraint(
            "length(payload_sha256) = 64",
            name="ck_rule_version_payload_sha256_length",
        ),
        UniqueConstraint(
            "rule_definition_id",
            "revision",
            name="uq_rule_version_definition_revision",
        ),
        Index(
            "ix_rule_version_definition_effective",
            "rule_definition_id",
            "effective_from",
            "effective_to",
        ),
    )

    rule_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("rule_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("rule_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    applicability: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
