"""Fail-closed tenant ownership tests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Calculation,
    CalculationVersion,
    Organization,
    OrganizationMembership,
    User,
)
from app.tenancy import (
    TenantResourceNotFound,
    add_calculation_version,
    get_calculation_for_tenant,
    require_calculation_for_tenant,
)


@dataclass(frozen=True)
class TenantFixture:
    organization_a_id: UUID
    organization_b_id: UUID
    user_a_id: UUID
    user_b_id: UUID
    calculation_a_id: UUID
    calculation_b_id: UUID


def seed_two_tenants(session: Session) -> TenantFixture:
    """Create two isolated tenants with one member and calculation each."""

    user_a = User(email="a@example.test", display_name="A")
    user_b = User(email="b@example.test", display_name="B")
    organization_a = Organization(slug="tenant-a", legal_name="Tenant A")
    organization_b = Organization(slug="tenant-b", legal_name="Tenant B")
    session.add_all([user_a, user_b, organization_a, organization_b])
    session.flush()

    session.add_all(
        [
            OrganizationMembership(
                organization_id=organization_a.id,
                user_id=user_a.id,
                role="owner",
            ),
            OrganizationMembership(
                organization_id=organization_b.id,
                user_id=user_b.id,
                role="owner",
            ),
        ]
    )
    session.flush()

    calculation_a = Calculation(
        organization_id=organization_a.id,
        created_by_user_id=user_a.id,
        name="A calculation",
        calculation_type="cost",
    )
    calculation_b = Calculation(
        organization_id=organization_b.id,
        created_by_user_id=user_b.id,
        name="B calculation",
        calculation_type="cost",
    )
    session.add_all([calculation_a, calculation_b])
    session.flush()

    return TenantFixture(
        organization_a_id=organization_a.id,
        organization_b_id=organization_b.id,
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        calculation_a_id=calculation_a.id,
        calculation_b_id=calculation_b.id,
    )


def test_scoped_lookup_never_returns_another_tenants_calculation(
    db_session: Session,
) -> None:
    fixture = seed_two_tenants(db_session)

    owned = get_calculation_for_tenant(
        db_session,
        organization_id=fixture.organization_a_id,
        calculation_id=fixture.calculation_a_id,
    )
    foreign = get_calculation_for_tenant(
        db_session,
        organization_id=fixture.organization_a_id,
        calculation_id=fixture.calculation_b_id,
    )

    assert owned is not None
    assert owned.id == fixture.calculation_a_id
    assert foreign is None


def test_require_lookup_hides_cross_tenant_existence(db_session: Session) -> None:
    fixture = seed_two_tenants(db_session)

    with pytest.raises(TenantResourceNotFound, match="calculation not found"):
        require_calculation_for_tenant(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_b_id,
        )


def test_database_rejects_creator_from_another_tenant(db_session: Session) -> None:
    fixture = seed_two_tenants(db_session)
    invalid = Calculation(
        organization_id=fixture.organization_a_id,
        created_by_user_id=fixture.user_b_id,
        name="Cross tenant",
        calculation_type="cost",
    )

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(invalid)
        db_session.flush()


def test_database_rejects_cross_tenant_calculation_version(
    db_session: Session,
) -> None:
    fixture = seed_two_tenants(db_session)
    invalid = CalculationVersion(
        organization_id=fixture.organization_b_id,
        calculation_id=fixture.calculation_a_id,
        created_by_user_id=fixture.user_b_id,
        version=1,
        engine_version="test",
        input_snapshot={},
        ruleset_snapshot={},
        output_snapshot={},
    )

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(invalid)
        db_session.flush()


def test_repository_adds_version_only_inside_owner_tenant(
    db_session: Session,
) -> None:
    fixture = seed_two_tenants(db_session)

    version = add_calculation_version(
        db_session,
        organization_id=fixture.organization_a_id,
        calculation_id=fixture.calculation_a_id,
        created_by_user_id=fixture.user_a_id,
        version=1,
        engine_version="test",
        input_snapshot={"amount": "100.00"},
        ruleset_snapshot={"ruleset": "none"},
        output_snapshot={"net": "100.00"},
    )
    db_session.flush()

    assert version.organization_id == fixture.organization_a_id
    assert version.calculation_id == fixture.calculation_a_id

    with pytest.raises(TenantResourceNotFound):
        add_calculation_version(
            db_session,
            organization_id=fixture.organization_b_id,
            calculation_id=fixture.calculation_a_id,
            created_by_user_id=fixture.user_b_id,
            version=2,
            engine_version="test",
            input_snapshot={},
            ruleset_snapshot={},
            output_snapshot={},
        )
