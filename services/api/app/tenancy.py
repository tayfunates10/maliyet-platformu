"""Tenant-scoped repository helpers.

Callers never query tenant-owned calculations by identifier alone.  A missing
resource and a resource owned by another organization intentionally produce the
same result so that identifiers cannot be used as an ownership oracle.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Calculation, CalculationVersion


class TenantResourceNotFound(LookupError):
    """Raised when a tenant cannot access the requested resource."""


def get_calculation_for_tenant(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
) -> Calculation | None:
    """Return a calculation only when it belongs to the requested tenant."""

    statement = select(Calculation).where(
        Calculation.id == calculation_id,
        Calculation.organization_id == organization_id,
    )
    return session.scalar(statement)


def require_calculation_for_tenant(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
) -> Calculation:
    """Resolve tenant ownership without disclosing cross-tenant existence."""

    calculation = get_calculation_for_tenant(
        session,
        organization_id=organization_id,
        calculation_id=calculation_id,
    )
    if calculation is None:
        raise TenantResourceNotFound("calculation not found")
    return calculation


def add_calculation_version(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
    created_by_user_id: UUID,
    version: int,
    engine_version: str,
    input_snapshot: dict[str, object],
    ruleset_snapshot: dict[str, object],
    output_snapshot: dict[str, object],
) -> CalculationVersion:
    """Add an immutable version after enforcing tenant-scoped ownership."""

    require_calculation_for_tenant(
        session,
        organization_id=organization_id,
        calculation_id=calculation_id,
    )
    item = CalculationVersion(
        organization_id=organization_id,
        calculation_id=calculation_id,
        created_by_user_id=created_by_user_id,
        version=version,
        engine_version=engine_version,
        input_snapshot=input_snapshot,
        ruleset_snapshot=ruleset_snapshot,
        output_snapshot=output_snapshot,
    )
    session.add(item)
    return item
