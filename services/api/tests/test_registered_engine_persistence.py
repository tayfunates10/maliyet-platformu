"""PostgreSQL integration tests for registered-engine persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculation_orchestration import load_replay_material
from app.engine_registry import execute_and_record_registered_engine
from app.models import (
    AuditEvent,
    Calculation,
    Organization,
    OrganizationMembership,
    User,
)


def test_registered_execution_persists_verified_replay_material(
    db_session: Session,
) -> None:
    user = User(email="registry@example.test", display_name="Registry User")
    organization = Organization(slug="registry-org", legal_name="Registry Org")
    db_session.add_all([user, organization])
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
        )
    )
    db_session.flush()
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="Trade order",
        calculation_type="trade",
    )
    db_session.add(calculation)
    db_session.flush()

    version, execution = execute_and_record_registered_engine(
        db_session,
        organization_id=organization.id,
        calculation_id=calculation.id,
        created_by_user_id=user.id,
        engine_key="trade",
        payload={
            "sales": [
                {
                    "key": "sale",
                    "quantity": "2",
                    "unit_sale_price": "100.00",
                    "unit_acquisition_cost": "40.00",
                }
            ]
        },
    )
    db_session.flush()

    assert version.version == 1
    assert version.engine_key == "trade"
    assert version.engine_version == execution.engine_version
    assert version.output_snapshot["contribution_profit"] == "120.00"

    replay = load_replay_material(
        db_session,
        organization_id=organization.id,
        calculation_id=calculation.id,
        version_number=1,
    )
    assert replay.engine_key == "trade"
    assert replay.input_snapshot == execution.input_snapshot
    assert replay.ruleset_snapshot == execution.ruleset_snapshot
    assert replay.output_snapshot == execution.output_snapshot

    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.entity_id == version.id,
            AuditEvent.event_type == "calculation.version_recorded",
        )
    )
    assert audit is not None
    assert audit.payload["engine_key"] == "trade"
