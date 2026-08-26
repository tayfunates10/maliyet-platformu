"""HTTP regression tests for rule-resolved employer personnel cost execution."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.baseline_loader import load_tr_2026_baseline
from app.main import CalculationExecutionResponse, app
from app.models import Calculation, CalculationVersion, Organization, OrganizationMembership, User


def _tenant_calculation(
    db_session: Session,
    *,
    suffix: str,
) -> tuple[Organization, Calculation, str]:
    user = User(email=f"personnel-{suffix}@example.test", display_name="Payroll Analyst")
    organization = Organization(slug=f"personnel-{suffix}", legal_name=f"Personnel {suffix} Org")
    db_session.add_all([user, organization])
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="analyst",
        )
    )
    db_session.flush()
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="Employer personnel cost",
        calculation_type="personnel_cost",
    )
    db_session.add(calculation)
    db_session.flush()
    _, raw_token = issue_session(db_session, user_id=user.id)
    return organization, calculation, raw_token


def _path(organization: Organization, calculation: Calculation) -> str:
    base = f"/organizations/{organization.id}/calculations/{calculation.id}"
    return f"{base}/execute/personnel_cost"


def _payload() -> dict[str, object]:
    return {
        "at_date": "2026-08-19",
        "gross_cash_compensation": "50000.00",
        "declared_monthly_earnings": "50000.00",
        "additional_employer_costs": [{"key": "meal", "amount": "1000.00"}],
    }


def test_authenticated_personnel_cost_resolves_rules_and_persists_provenance(
    app_db_session: Session,
) -> None:
    load_tr_2026_baseline(app_db_session)
    organization, calculation, raw_token = _tenant_calculation(
        app_db_session,
        suffix="persist",
    )

    response = TestClient(app).post(
        _path(organization, calculation),
        json=_payload(),
        headers={"Authorization": f"Bearer {raw_token}"},
    )

    assert response.status_code == 201
    body = CalculationExecutionResponse.model_validate(response.json())
    assert body.engine_key == "personnel_cost"
    assert body.engine_version == "personnel-cost-v1"
    assert body.output_snapshot["employer_sgk_premium"] == "11875.0000"
    assert body.output_snapshot["total_employer_cost"] == "62875.0000"
    assert body.output_snapshot["employee_income_tax_inferred"] is False

    version = app_db_session.scalar(
        select(CalculationVersion).where(CalculationVersion.id == body.calculation_version_id)
    )
    assert version is not None
    assert version.input_snapshot == _payload()
    assert version.ruleset_snapshot["regulatory_rules_applied"] is True
    assert version.ruleset_snapshot["current_rules_resolved"] is True
    assert version.ruleset_snapshot["effective_at"] == "2026-08-19"
    rule_codes = {
        item["code"]
        for item in version.ruleset_snapshot["rule_versions"]
        if isinstance(item, dict)
    }
    assert rule_codes == {
        "TR.SGK.4A.PRIVATE.PEK_LIMITS",
        "TR.SGK.4A.GENERAL.PREMIUM_RATES",
    }
    assert version.ruleset_sha256 == body.ruleset_sha256
    assert version.output_sha256 == body.output_sha256


def test_personnel_cost_fails_closed_when_required_rules_are_missing(
    app_db_session: Session,
) -> None:
    organization, calculation, raw_token = _tenant_calculation(
        app_db_session,
        suffix="missing-rules",
    )

    response = TestClient(app).post(
        _path(organization, calculation),
        json=_payload(),
        headers={"Authorization": f"Bearer {raw_token}"},
    )

    assert response.status_code == 422
    version = app_db_session.scalar(
        select(CalculationVersion).where(CalculationVersion.calculation_id == calculation.id)
    )
    assert version is None


def test_personnel_cost_rejects_numeric_money_before_rule_resolution(
    app_db_session: Session,
) -> None:
    load_tr_2026_baseline(app_db_session)
    organization, calculation, raw_token = _tenant_calculation(
        app_db_session,
        suffix="numeric-json",
    )
    payload = _payload()
    payload["gross_cash_compensation"] = 50000.0

    response = TestClient(app).post(
        _path(organization, calculation),
        json=payload,
        headers={"Authorization": f"Bearer {raw_token}"},
    )

    assert response.status_code == 422
    version = app_db_session.scalar(
        select(CalculationVersion).where(CalculationVersion.calculation_id == calculation.id)
    )
    assert version is None
