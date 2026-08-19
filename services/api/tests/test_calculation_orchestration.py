"""PostgreSQL integration tests for reproducible calculation-version persistence."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calculation_orchestration import (
    CalculationIntegrityError,
    CalculationOrchestrationError,
    canonicalize_snapshot,
    load_replay_material,
    record_calculation_version,
    verify_calculation_version_integrity,
)
from app.models import (
    AuditEvent,
    Calculation,
    CalculationVersion,
    Organization,
    OrganizationMembership,
    User,
)
from app.tenancy import TenantResourceNotFound


@dataclass(frozen=True)
class OrchestrationFixture:
    organization_a_id: UUID
    organization_b_id: UUID
    user_a_id: UUID
    user_b_id: UUID
    calculation_a_id: UUID


def seed_orchestration_fixture(session: Session) -> OrchestrationFixture:
    """Create two tenants and one engine-bound calculation owned by tenant A."""

    user_a = User(email="orchestrator-a@example.test", display_name="A")
    user_b = User(email="orchestrator-b@example.test", display_name="B")
    organization_a = Organization(slug="orchestrator-a", legal_name="Orchestrator A")
    organization_b = Organization(slug="orchestrator-b", legal_name="Orchestrator B")
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

    calculation = Calculation(
        organization_id=organization_a.id,
        created_by_user_id=user_a.id,
        name="Tourism scenario",
        calculation_type="tourism_package",
    )
    session.add(calculation)
    session.flush()

    return OrchestrationFixture(
        organization_a_id=organization_a.id,
        organization_b_id=organization_b.id,
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        calculation_a_id=calculation.id,
    )


def record_fixture_version(
    session: Session,
    fixture: OrchestrationFixture,
    *,
    output: str = "250.00",
) -> CalculationVersion:
    """Record one deterministic tourism version for test reuse."""

    return record_calculation_version(
        session,
        organization_id=fixture.organization_a_id,
        calculation_id=fixture.calculation_a_id,
        created_by_user_id=fixture.user_a_id,
        engine_key="tourism_package",
        engine_version="tourism-package-costing-v1",
        input_snapshot={"participant_count": 2, "currency": "TRY"},
        ruleset_snapshot={
            "resolved_at": "2026-08-19",
            "rules": [{"code": "example", "source_sha256": "abc123"}],
        },
        output_snapshot={"package_contribution": output},
    )


def test_record_version_persists_provenance_hashes_and_audit_event(
    db_session: Session,
) -> None:
    fixture = seed_orchestration_fixture(db_session)

    version = record_fixture_version(db_session, fixture)

    assert version.version == 1
    assert version.engine_key == "tourism_package"
    assert version.engine_version == "tourism-package-costing-v1"
    assert version.input_sha256 is not None
    assert len(version.input_sha256) == 64
    assert version.ruleset_sha256 is not None
    assert len(version.ruleset_sha256) == 64
    assert version.output_sha256 is not None
    assert len(version.output_sha256) == 64
    verify_calculation_version_integrity(version)

    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == fixture.organization_a_id,
            AuditEvent.entity_id == version.id,
            AuditEvent.event_type == "calculation.version_recorded",
        )
    )
    assert audit is not None
    assert audit.payload["calculation_id"] == str(fixture.calculation_a_id)
    assert audit.payload["version"] == 1
    assert audit.payload["engine_key"] == "tourism_package"
    assert audit.payload["input_sha256"] == version.input_sha256
    assert audit.payload["ruleset_sha256"] == version.ruleset_sha256
    assert audit.payload["output_sha256"] == version.output_sha256


def test_sequential_writes_allocate_monotonic_versions(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)

    first = record_fixture_version(db_session, fixture, output="100.00")
    second = record_fixture_version(db_session, fixture, output="200.00")

    assert first.version == 1
    assert second.version == 2
    versions = db_session.scalars(
        select(CalculationVersion.version)
        .where(CalculationVersion.calculation_id == fixture.calculation_a_id)
        .order_by(CalculationVersion.version)
    ).all()
    assert versions == [1, 2]


def test_recording_deep_copies_caller_snapshots(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)
    input_snapshot: dict[str, object] = {
        "participant_count": 2,
        "nested": {"currency": "TRY"},
    }
    ruleset_snapshot: dict[str, object] = {"rules": [{"code": "original"}]}
    output_snapshot: dict[str, object] = {"result": "100.00"}

    version = record_calculation_version(
        db_session,
        organization_id=fixture.organization_a_id,
        calculation_id=fixture.calculation_a_id,
        created_by_user_id=fixture.user_a_id,
        engine_key="tourism_package",
        engine_version="tourism-package-costing-v1",
        input_snapshot=input_snapshot,
        ruleset_snapshot=ruleset_snapshot,
        output_snapshot=output_snapshot,
    )

    input_snapshot["participant_count"] = 999
    ruleset_snapshot["rules"] = []
    output_snapshot["result"] = "999.00"

    assert version.input_snapshot["participant_count"] == 2
    assert version.ruleset_snapshot["rules"] == [{"code": "original"}]
    assert version.output_snapshot["result"] == "100.00"
    verify_calculation_version_integrity(version)


def test_replay_uses_stored_material_without_current_rule_resolution(
    db_session: Session,
) -> None:
    fixture = seed_orchestration_fixture(db_session)
    version = record_fixture_version(db_session, fixture)

    replay = load_replay_material(
        db_session,
        organization_id=fixture.organization_a_id,
        calculation_id=fixture.calculation_a_id,
        version_number=1,
    )

    assert replay.version_id == version.id
    assert replay.engine_key == "tourism_package"
    assert replay.engine_version == "tourism-package-costing-v1"
    assert replay.input_snapshot == {"currency": "TRY", "participant_count": 2}
    assert replay.ruleset_snapshot == {
        "resolved_at": "2026-08-19",
        "rules": [{"code": "example", "source_sha256": "abc123"}],
    }
    assert replay.output_snapshot == {"package_contribution": "250.00"}
    assert replay.ruleset_sha256 == version.ruleset_sha256


def test_tampered_snapshot_fails_integrity_verification(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)
    version = record_fixture_version(db_session, fixture)

    version.output_snapshot = {"package_contribution": "999999.00"}
    db_session.flush()

    with pytest.raises(CalculationIntegrityError, match="output snapshot digest mismatch"):
        verify_calculation_version_integrity(version)

    with pytest.raises(CalculationIntegrityError, match="output snapshot digest mismatch"):
        load_replay_material(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_a_id,
            version_number=1,
        )


def test_cross_tenant_replay_hides_version_existence(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)
    record_fixture_version(db_session, fixture)

    with pytest.raises(TenantResourceNotFound, match="calculation version not found"):
        load_replay_material(
            db_session,
            organization_id=fixture.organization_b_id,
            calculation_id=fixture.calculation_a_id,
            version_number=1,
        )


def test_non_member_actor_cannot_record_version(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)

    with pytest.raises(TenantResourceNotFound, match="organization membership not found"):
        record_calculation_version(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_a_id,
            created_by_user_id=fixture.user_b_id,
            engine_key="tourism_package",
            engine_version="tourism-package-costing-v1",
            input_snapshot={},
            ruleset_snapshot={},
            output_snapshot={},
        )

    count = db_session.scalar(
        select(func.count(CalculationVersion.id)).where(
            CalculationVersion.calculation_id == fixture.calculation_a_id
        )
    )
    assert count == 0


def test_engine_key_must_match_calculation_type(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)

    with pytest.raises(CalculationOrchestrationError, match="must match"):
        record_calculation_version(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_a_id,
            created_by_user_id=fixture.user_a_id,
            engine_key="transportation",
            engine_version="transportation-costing-v1",
            input_snapshot={},
            ruleset_snapshot={},
            output_snapshot={},
        )


def test_snapshot_rejects_binary_float_before_persistence(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)

    with pytest.raises(CalculationOrchestrationError, match="must not contain binary float"):
        record_calculation_version(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_a_id,
            created_by_user_id=fixture.user_a_id,
            engine_key="tourism_package",
            engine_version="tourism-package-costing-v1",
            input_snapshot={"amount": 1.5},
            ruleset_snapshot={},
            output_snapshot={},
        )


def test_engine_identity_must_not_be_blank(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)

    with pytest.raises(CalculationOrchestrationError, match="engine_version must not be blank"):
        record_calculation_version(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_a_id,
            created_by_user_id=fixture.user_a_id,
            engine_key="tourism_package",
            engine_version="   ",
            input_snapshot={},
            ruleset_snapshot={},
            output_snapshot={},
        )


def test_canonical_snapshot_hash_is_key_order_independent() -> None:
    _, first = canonicalize_snapshot({"b": 2, "a": 1}, field="snapshot")
    _, second = canonicalize_snapshot({"a": 1, "b": 2}, field="snapshot")

    assert first == second


def test_legacy_version_without_provenance_fails_replay_closed(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)
    legacy = CalculationVersion(
        organization_id=fixture.organization_a_id,
        calculation_id=fixture.calculation_a_id,
        created_by_user_id=fixture.user_a_id,
        version=1,
        engine_version="legacy-v1",
        input_snapshot={},
        ruleset_snapshot={},
        output_snapshot={},
    )
    db_session.add(legacy)
    db_session.flush()

    with pytest.raises(CalculationIntegrityError, match="missing engine_key"):
        load_replay_material(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_a_id,
            version_number=1,
        )


def test_replay_version_number_must_be_positive(db_session: Session) -> None:
    fixture = seed_orchestration_fixture(db_session)

    with pytest.raises(CalculationOrchestrationError, match="version_number must be positive"):
        load_replay_material(
            db_session,
            organization_id=fixture.organization_a_id,
            calculation_id=fixture.calculation_a_id,
            version_number=0,
        )
