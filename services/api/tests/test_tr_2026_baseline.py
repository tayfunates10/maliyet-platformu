"""Production baseline integrity and official-fact regression tests."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.baseline_loader import (
    BaselineIntegrityError,
    SourceSpec,
    load_tr_2026_baseline,
    read_manifest,
    verify_source_capture,
    verify_tr_2026_baseline_state,
)
from app.rules_engine import RuleNotFound, resolve_rule, rule_payload_sha256
from app.rules_models import RuleDefinition, RuleSource, RuleVersion


def test_baseline_load_is_idempotent_and_complete(db_session: Session) -> None:
    first = load_tr_2026_baseline(db_session)
    second = load_tr_2026_baseline(db_session)
    db_session.flush()

    assert first == second
    assert first.sources == 6
    assert first.definitions == 11
    assert first.versions == 11
    assert db_session.scalar(select(func.count()).select_from(RuleSource)) == 6
    assert db_session.scalar(select(func.count()).select_from(RuleDefinition)) == 11
    assert db_session.scalar(select(func.count()).select_from(RuleVersion)) == 11


def test_baseline_load_rejects_existing_source_metadata_drift(db_session: Session) -> None:
    load_tr_2026_baseline(db_session)
    source = db_session.scalar(select(RuleSource).order_by(RuleSource.created_at).limit(1))
    assert source is not None
    source.title = f"{source.title} tampered"
    db_session.flush()

    with pytest.raises(BaselineIntegrityError, match="source metadata drift"):
        load_tr_2026_baseline(db_session)


def test_read_only_baseline_verifier_accepts_exact_persisted_state(db_session: Session) -> None:
    loaded = load_tr_2026_baseline(db_session)

    assert verify_tr_2026_baseline_state(db_session) == loaded


def test_read_only_baseline_verifier_rejects_persisted_payload_drift(
    db_session: Session,
) -> None:
    load_tr_2026_baseline(db_session)
    version = db_session.scalar(select(RuleVersion).order_by(RuleVersion.created_at).limit(1))
    assert version is not None
    version.payload = {"tampered": True}
    db_session.flush()

    with pytest.raises(BaselineIntegrityError, match="persisted rule version drift"):
        verify_tr_2026_baseline_state(db_session)


def test_read_only_baseline_verifier_rejects_unlisted_revision(db_session: Session) -> None:
    load_tr_2026_baseline(db_session)
    version = db_session.scalar(select(RuleVersion).order_by(RuleVersion.created_at).limit(1))
    assert version is not None
    db_session.add(
        RuleVersion(
            rule_definition_id=version.rule_definition_id,
            source_id=version.source_id,
            revision=version.revision + 1000,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            applicability=version.applicability,
            payload=version.payload,
            payload_sha256=rule_payload_sha256(version.payload),
        )
    )
    db_session.flush()

    with pytest.raises(BaselineIntegrityError, match="persisted rule revision set drift"):
        verify_tr_2026_baseline_state(db_session)


def test_all_declared_source_capture_hashes_verify() -> None:
    manifest = read_manifest()
    for source in manifest.sources:
        assert verify_source_capture(source).is_file()


def test_tampered_source_capture_hash_fails_closed() -> None:
    source = read_manifest().sources[0]
    tampered = SourceSpec(**{**source.model_dump(), "content_sha256": "0" * 64})
    with pytest.raises(BaselineIntegrityError, match="hash mismatch"):
        verify_source_capture(tampered)


def test_2026_income_tax_tariffs_preserve_wage_threshold_difference(
    db_session: Session,
) -> None:
    load_tr_2026_baseline(db_session)
    non_wage = resolve_rule(
        db_session,
        code="TR.INCOME_TAX.NON_WAGE.TARIFF",
        at_date=date(2026, 8, 19),
    )
    wage = resolve_rule(
        db_session,
        code="TR.INCOME_TAX.WAGE.TARIFF",
        at_date=date(2026, 8, 19),
    )

    non_wage_bands = non_wage.version.payload["bands"]
    wage_bands = wage.version.payload["bands"]
    assert isinstance(non_wage_bands, list)
    assert isinstance(wage_bands, list)
    assert non_wage_bands[2] == {
        "upper": "1000000.00",
        "base_tax": "70500.00",
        "rate": "0.27",
    }
    assert wage_bands[2] == {
        "upper": "1500000.00",
        "base_tax": "70500.00",
        "rate": "0.27",
    }


def test_core_2026_general_tax_rates(db_session: Session) -> None:
    load_tr_2026_baseline(db_session)
    expected = {
        "TR.PROVISIONAL_TAX.INCOME.GENERAL_RATE": "0.15",
        "TR.CORPORATE_TAX.GENERAL_RATE": "0.25",
        "TR.PROVISIONAL_TAX.CORPORATE.GENERAL_RATE": "0.25",
    }
    for code, rate in expected.items():
        resolved = resolve_rule(db_session, code=code, at_date=date(2026, 8, 19))
        assert resolved.version.payload == {"rate": rate}


def test_vat_rate_classes_are_explicit_not_auto_classified(db_session: Session) -> None:
    load_tr_2026_baseline(db_session)
    expected = {
        "TR.VAT.LIST_I_RATE": "0.01",
        "TR.VAT.LIST_II_RATE": "0.10",
        "TR.VAT.DEFAULT_RATE": "0.20",
    }
    for code, rate in expected.items():
        resolved = resolve_rule(db_session, code=code, at_date=date(2026, 8, 19))
        assert resolved.version.payload == {"rate": rate}


def test_2026_sgk_4a_private_limits_and_general_rates(db_session: Session) -> None:
    load_tr_2026_baseline(db_session)
    limits = resolve_rule(
        db_session,
        code="TR.SGK.4A.PRIVATE.PEK_LIMITS",
        at_date=date(2026, 8, 19),
    ).version.payload
    rates = resolve_rule(
        db_session,
        code="TR.SGK.4A.GENERAL.PREMIUM_RATES",
        at_date=date(2026, 8, 19),
    ).version.payload

    assert limits == {
        "daily_min": "1101.00",
        "monthly_min": "33030.00",
        "daily_max": "9909.00",
        "monthly_max": "297270.00",
    }
    assert rates["combined_total"] == "0.3875"
    assert rates["employer"]["total"] == "0.2375"
    assert rates["employee"]["total"] == "0.15"


def test_year_specific_income_tariff_does_not_leak_into_2027(db_session: Session) -> None:
    load_tr_2026_baseline(db_session)
    with pytest.raises(RuleNotFound, match="no effective rule"):
        resolve_rule(
            db_session,
            code="TR.INCOME_TAX.NON_WAGE.TARIFF",
            at_date=date(2027, 1, 1),
        )
