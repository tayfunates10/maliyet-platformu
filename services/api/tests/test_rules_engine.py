"""Effective-date, provenance, and Decimal-safety tests for the rules engine."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.rules_engine import (
    RuleConfigurationError,
    RuleNotFound,
    RulePayloadError,
    build_rule_snapshot,
    create_rule_version,
    resolve_rule,
    rule_payload_sha256,
)
from app.rules_models import RuleDefinition, RuleSource, RuleVersion


def seed_rule_identity(db_session: Session) -> tuple[RuleSource, RuleDefinition]:
    """Create source/definition records using explicitly synthetic test data."""

    source = RuleSource(
        authority="SYNTHETIC TEST AUTHORITY",
        source_type="official_guidance",
        title="Synthetic rules-engine fixture — not legislation",
        canonical_url="https://example.invalid/synthetic-rule-source",
        official_reference="TEST-ONLY",
        published_on=date(2026, 1, 1),
        retrieved_at=datetime(2026, 1, 2, tzinfo=UTC),
        content_sha256="a" * 64,
    )
    definition = RuleDefinition(
        jurisdiction="TR",
        code="TEST.DECIMAL_RATE",
        category="test_only",
        description="Synthetic decimal rule used only by automated tests.",
        value_kind="decimal",
    )
    db_session.add_all([source, definition])
    db_session.flush()
    return source, definition


def test_effective_to_is_exclusive_at_boundary(db_session: Session) -> None:
    source, definition = seed_rule_identity(db_session)
    first = create_rule_version(
        db_session,
        definition=definition,
        source=source,
        revision=1,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 7, 1),
        applicability={},
        payload={"rate": "0.10"},
    )
    second = create_rule_version(
        db_session,
        definition=definition,
        source=source,
        revision=2,
        effective_from=date(2026, 7, 1),
        effective_to=None,
        applicability={},
        payload={"rate": "0.20"},
    )
    db_session.flush()

    before = resolve_rule(db_session, code=definition.code, at_date=date(2026, 6, 30))
    boundary = resolve_rule(db_session, code=definition.code, at_date=date(2026, 7, 1))

    assert before.version.id == first.id
    assert boundary.version.id == second.id


def test_missing_effective_rule_fails_closed(db_session: Session) -> None:
    source, definition = seed_rule_identity(db_session)
    create_rule_version(
        db_session,
        definition=definition,
        source=source,
        revision=1,
        effective_from=date(2026, 2, 1),
        effective_to=None,
        applicability={},
        payload={"rate": "0.10"},
    )
    db_session.flush()

    with pytest.raises(RuleNotFound, match="no effective rule"):
        resolve_rule(db_session, code=definition.code, at_date=date(2026, 1, 31))


def test_overlap_is_rejected_by_creation_service(db_session: Session) -> None:
    source, definition = seed_rule_identity(db_session)
    create_rule_version(
        db_session,
        definition=definition,
        source=source,
        revision=1,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        applicability={},
        payload={"rate": "0.10"},
    )
    db_session.flush()

    with pytest.raises(RuleConfigurationError, match="overlap"):
        create_rule_version(
            db_session,
            definition=definition,
            source=source,
            revision=2,
            effective_from=date(2026, 6, 1),
            effective_to=None,
            applicability={},
            payload={"rate": "0.20"},
        )


def test_ambiguous_persisted_rules_fail_closed_on_resolution(db_session: Session) -> None:
    source, definition = seed_rule_identity(db_session)
    payload_one = {"rate": "0.10"}
    payload_two = {"rate": "0.20"}
    db_session.add_all(
        [
            RuleVersion(
                rule_definition_id=definition.id,
                source_id=source.id,
                revision=1,
                effective_from=date(2026, 1, 1),
                effective_to=None,
                applicability={},
                payload=payload_one,
                payload_sha256=rule_payload_sha256(payload_one),
            ),
            RuleVersion(
                rule_definition_id=definition.id,
                source_id=source.id,
                revision=2,
                effective_from=date(2026, 6, 1),
                effective_to=None,
                applicability={},
                payload=payload_two,
                payload_sha256=rule_payload_sha256(payload_two),
            ),
        ]
    )
    db_session.flush()

    with pytest.raises(RuleConfigurationError, match="ambiguous"):
        resolve_rule(db_session, code=definition.code, at_date=date(2026, 7, 1))


def test_binary_float_payload_is_forbidden(db_session: Session) -> None:
    source, definition = seed_rule_identity(db_session)

    with pytest.raises(RulePayloadError, match="binary float"):
        create_rule_version(
            db_session,
            definition=definition,
            source=source,
            revision=1,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            applicability={},
            payload={"rate": 0.1},
        )


def test_database_rejects_invalid_effective_range(db_session: Session) -> None:
    source, definition = seed_rule_identity(db_session)
    payload = {"rate": "0.10"}
    invalid = RuleVersion(
        rule_definition_id=definition.id,
        source_id=source.id,
        revision=1,
        effective_from=date(2026, 7, 1),
        effective_to=date(2026, 7, 1),
        applicability={},
        payload=payload,
        payload_sha256=rule_payload_sha256(payload),
    )

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(invalid)
        db_session.flush()


def test_snapshot_freezes_rule_and_source_identity(db_session: Session) -> None:
    source, definition = seed_rule_identity(db_session)
    create_rule_version(
        db_session,
        definition=definition,
        source=source,
        revision=1,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        applicability={"entity_type": "synthetic"},
        payload={"rate": "0.10", "threshold": "1000.00"},
    )
    db_session.flush()

    resolved = resolve_rule(db_session, code=definition.code, at_date=date(2026, 8, 1))
    snapshot = build_rule_snapshot(resolved)
    source_snapshot = snapshot["source"]

    assert UUID(snapshot["rule_version_id"]) == resolved.version.id
    assert snapshot["payload"] == {"rate": "0.10", "threshold": "1000.00"}
    assert isinstance(source_snapshot, dict)
    assert source_snapshot["content_sha256"] == "a" * 64
    assert source_snapshot["canonical_url"] == "https://example.invalid/synthetic-rule-source"
