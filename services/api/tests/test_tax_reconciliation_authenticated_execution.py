"""HTTP regression tests for persisted tax-base reconciliation execution."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import CalculationExecutionResponse, app
from app.models import Calculation, CalculationVersion, Organization, OrganizationMembership, User


def _tenant_calculation(
    db_session: Session,
    *,
    suffix: str,
) -> tuple[Organization, Calculation, str]:
    user = User(email=f"tax-recon-{suffix}@example.test", display_name="Tax Analyst")
    organization = Organization(slug=f"tax-recon-{suffix}", legal_name=f"Tax Recon {suffix} Org")
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
        name="Tax base reconciliation",
        calculation_type="tax_reconciliation",
    )
    db_session.add(calculation)
    db_session.flush()
    _, raw_token = issue_session(db_session, user_id=user.id)
    return organization, calculation, raw_token


def _path(organization: Organization, calculation: Calculation) -> str:
    return (
        f"/organizations/{organization.id}/calculations/"
        f"{calculation.id}/execute/tax_reconciliation"
    )


def _payload() -> dict[str, object]:
    return {
        "accounting_profit_before_tax": "100000.00",
        "adjustments": [
            {"key": "non_deductible", "amount": "5000.00", "treatment": "addition"},
            {"key": "exemption", "amount": "2000.00", "treatment": "deduction"},
        ],
    }


def test_authenticated_tax_reconciliation_is_persisted_immutably(
    app_db_session: Session,
) -> None:
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
    assert body.engine_key == "tax_reconciliation"
    assert body.engine_version == "tax-reconciliation-v1"
    assert body.output_snapshot["reconciled_taxable_base"] == "103000.00"
    assert body.output_snapshot["taxable_base_inferred_from_accounting_profit"] is False
    assert "current_tax_expense" not in body.output_snapshot

    version = app_db_session.scalar(
        select(CalculationVersion).where(CalculationVersion.id == body.calculation_version_id)
    )
    assert version is not None
    assert version.input_snapshot == _payload()
    assert version.ruleset_snapshot == {
        "rule_versions": [],
        "regulatory_rules_applied": False,
        "current_rules_resolved": False,
    }
    assert version.output_sha256 == body.output_sha256


def test_tax_reconciliation_rejects_numeric_money_before_persistence(
    app_db_session: Session,
) -> None:
    organization, calculation, raw_token = _tenant_calculation(
        app_db_session,
        suffix="numeric-json",
    )
    payload = _payload()
    payload["accounting_profit_before_tax"] = 100000.0

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
