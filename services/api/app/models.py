"""Tenant-scoped persistence models.

The schema deliberately encodes tenant ownership into foreign keys so that
cross-organization references fail at the database boundary, not only in
application code.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SUPPORTED_SECTORS = (
    "food_manufacturing",
    "textile_manufacturing",
    "basic_metals",
    "ecommerce",
    "trade",
    "transportation",
    "accommodation",
    "tourism",
)

MEMBERSHIP_ROLES = ("owner", "admin", "accountant", "analyst", "viewer")


class Base(DeclarativeBase):
    """Declarative metadata root for all application tables."""


class UUIDPrimaryKeyMixin:
    """Use application-generated UUIDs for stable public identifiers."""

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


class TimestampMixin:
    """Track row creation and last update in the database timezone."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A human identity that may belong to multiple organizations."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Top-level tenant boundary."""

    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    legal_name: Mapped[str] = mapped_column(String(240), nullable=False)


class OrganizationMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Authorization link between a user and an organization."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_membership_org_user",
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'accountant', 'analyst', 'viewer')",
            name="ck_membership_role",
        ),
        Index("ix_membership_user_org", "user_id", "organization_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Organization business identity and primary operational context."""

    __tablename__ = "business_profiles"
    __table_args__ = (
        CheckConstraint(
            "primary_sector IN ("
            "'food_manufacturing', 'textile_manufacturing', 'basic_metals', "
            "'ecommerce', 'trade', 'transportation', 'accommodation', 'tourism'"
            ")",
            name="ck_business_profile_primary_sector",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    primary_sector: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="TR")
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)


class TaxProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant tax context without hard-coding rates or monetary thresholds."""

    __tablename__ = "tax_profiles"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('sole_proprietorship', 'limited', 'joint_stock', "
            "'partnership', 'cooperative', 'other')",
            name="ck_tax_profile_entity_type",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    vat_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Calculation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned logical calculation with immutable versions."""

    __tablename__ = "calculations"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_calculation_id_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_calculation_creator_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_calculation_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    calculation_type: Mapped[str] = mapped_column(String(80), nullable=False)


class CalculationVersion(UUIDPrimaryKeyMixin, Base):
    """Append-only, tamper-evident input/rule/engine/output calculation snapshot."""

    __tablename__ = "calculation_versions"
    __table_args__ = (
        UniqueConstraint(
            "calculation_id",
            "version",
            name="uq_calculation_version",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_calculation_version_id_org",
        ),
        ForeignKeyConstraint(
            ["calculation_id", "organization_id"],
            ["calculations.id", "calculations.organization_id"],
            name="fk_calculation_version_tenant_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_calculation_version_creator_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="ck_calculation_version_positive"),
        CheckConstraint(
            "input_sha256 IS NULL OR length(input_sha256) = 64",
            name="ck_calculation_version_input_sha256_length",
        ),
        CheckConstraint(
            "ruleset_sha256 IS NULL OR length(ruleset_sha256) = 64",
            name="ck_calculation_version_ruleset_sha256_length",
        ),
        CheckConstraint(
            "output_sha256 IS NULL OR length(output_sha256) = 64",
            name="ck_calculation_version_output_sha256_length",
        ),
        Index(
            "ix_calculation_version_org_calculation",
            "organization_id",
            "calculation_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    calculation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    input_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ruleset_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    ruleset_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PublicCalculationProjection(UUIDPrimaryKeyMixin, Base):
    """Immutable customer-safe publication linked to one tenant calculation version."""

    __tablename__ = "public_calculation_projections"
    __table_args__ = (
        CheckConstraint(
            "length(token_sha256) = 64",
            name="ck_public_projection_token_sha256_length",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_public_projection_currency",
        ),
        CheckConstraint(
            "estimate_min >= 0",
            name="ck_public_projection_estimate_min_non_negative",
        ),
        CheckConstraint(
            "estimate_max >= estimate_min",
            name="ck_public_projection_estimate_range",
        ),
        ForeignKeyConstraint(
            ["calculation_version_id", "organization_id"],
            ["calculation_versions.id", "calculation_versions.organization_id"],
            name="fk_public_projection_version_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_public_projection_creator_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("token_sha256", name="uq_public_projection_token_sha256"),
        UniqueConstraint("id", "organization_id", name="uq_public_projection_id_org"),
        Index("ix_public_projection_org_created", "organization_id", "created_at"),
        Index("ix_public_projection_version", "calculation_version_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    calculation_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    estimate_min: Mapped[Decimal] = mapped_column(Numeric(38, 12), nullable=False)
    estimate_max: Mapped[Decimal] = mapped_column(Numeric(38, 12), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WidgetDeployment(UUIDPrimaryKeyMixin, Base):
    """Public widget identifier bound to one already-safe projection and tenant."""

    __tablename__ = "widget_deployments"
    __table_args__ = (
        CheckConstraint(
            "hourly_request_limit >= 1 AND hourly_request_limit <= 100000",
            name="ck_widget_deployment_hourly_limit",
        ),
        ForeignKeyConstraint(
            ["public_projection_id", "organization_id"],
            ["public_calculation_projections.id", "public_calculation_projections.organization_id"],
            name="fk_widget_deployment_projection_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_deployment_creator_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_widget_deployment_id_org"),
        Index("ix_widget_deployment_org_created", "organization_id", "created_at"),
        Index("ix_widget_deployment_projection", "public_projection_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    public_projection_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    hourly_request_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WidgetAllowedOrigin(UUIDPrimaryKeyMixin, Base):
    """Exact normalized HTTPS origin allowed to consume one widget deployment."""

    __tablename__ = "widget_allowed_origins"
    __table_args__ = (
        ForeignKeyConstraint(
            ["widget_deployment_id", "organization_id"],
            ["widget_deployments.id", "widget_deployments.organization_id"],
            name="fk_widget_origin_deployment_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_widget_origin_creator_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "widget_deployment_id",
            "origin",
            name="uq_widget_origin_deployment_origin",
        ),
        Index(
            "ix_widget_origin_org_deployment",
            "organization_id",
            "widget_deployment_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    widget_deployment_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    origin: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WidgetUsageBucket(UUIDPrimaryKeyMixin, Base):
    """Atomic per-deployment UTC-hour request counter used for quota enforcement."""

    __tablename__ = "widget_usage_buckets"
    __table_args__ = (
        CheckConstraint("request_count >= 0", name="ck_widget_usage_request_count"),
        ForeignKeyConstraint(
            ["widget_deployment_id", "organization_id"],
            ["widget_deployments.id", "widget_deployments.organization_id"],
            name="fk_widget_usage_deployment_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "widget_deployment_id",
            "bucket_start",
            name="uq_widget_usage_deployment_start",
        ),
        Index("ix_widget_usage_org_bucket", "organization_id", "bucket_start"),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    widget_deployment_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only tenant audit record for security-sensitive domain actions."""

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_audit_actor_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_audit_event_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
