"""HTTP regression tests for persisted target-profit pricing execution."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import CalculationExecutionResponse, app
from app.models import Calculation, CalculationVersion, Organization, OrganizationMembership, User


def _tenant_target_profit_calculation(
    db_session: Session,
    *,
    suffix: str,
) -> tuple[Organization, Calculation, str]:
    user = User(email=f"target-profit-{suffix}@example.test", display_name="Target Profit Analyst")
    organization = Organization(
        slug=f"target-profit-{suffix}",
        legal_name=f"Target Profit {suffix} Org",
    )
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
        name="Target profit price",
        calculation_type="target_profit_pricing",
    )
    db_session.add(calculation)
    db_session.flush()
    _, raw_token = issue_session(db_session, user_id=user.id)
    return organization, calculation, raw_token


def _path(organization: Organization, calculation: Calculation) -> str:
    return (
        f"/organizations/{organization.id}/calculations/{calculation.id}"
        "/execute/target_profit_pricing"
    )


def _payload() -> dict[str, object]:
    return {
        "variable_cost_per_unit": "40.00",
        "fixed_costs": "1000.00",
        "target_profit": "500.00",
        "expected_units": "100",
    }


def test_authenticated_target_profit_execution_is_persisted_immutably(
    app_db_session: Session,
) -> None:
    organization, calculation, raw_token = _tenant_target_profit_calculation(
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
    assert body.engine_key == "target_profit_pricing"
    assert body.engine_version == "target-profit-pricing-v2"
    assert body.output_snapshot["required_price_per_unit"] == "55.00"
    assert body.output_snapshot["required_revenue"] == "5500.00"
    assert body.output_snapshot["tax_inferred"] is False

    version = app_db_session.scalar(
        select(CalculationVersion).where(CalculationVersion.id == body.calculation_version_id)
    )
    assert version is not None
    assert version.input_snapshot == _payload()
    assert version.engine_version == "target-profit-pricing-v2"
    assert version.ruleset_snapshot == {
        "rule_versions": [],
        "regulatory_rules_applied": False,
        "current_rules_resolved": False,
    }
    assert version.output_sha256 == body.output_sha256


def test_target_profit_execution_rejects_numeric_json_before_persistence(
    app_db_session: Session,
) -> None:
    organization, calculation, raw_token = _tenant_target_profit_calculation(
        app_db_session,
        suffix="numeric-json",
    )
    payload = _payload()
    payload["variable_cost_per_unit"] = 40.0

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
