"""HTTP regression tests for persisted asset-depreciation execution."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import CalculationExecutionResponse, app
from app.models import Calculation, CalculationVersion, Organization, OrganizationMembership, User


def _tenant_asset_calculation(
    db_session: Session,
    *,
    suffix: str,
) -> tuple[Organization, Calculation, str]:
    user = User(email=f"asset-{suffix}@example.test", display_name="Asset Analyst")
    organization = Organization(slug=f"asset-{suffix}", legal_name=f"Asset {suffix} Org")
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
        name="Machine depreciation",
        calculation_type="asset_depreciation",
    )
    db_session.add(calculation)
    db_session.flush()
    _, raw_token = issue_session(db_session, user_id=user.id)
    return organization, calculation, raw_token


def _path(organization: Organization, calculation: Calculation) -> str:
    return (
        f"/organizations/{organization.id}/calculations/{calculation.id}/execute/asset_depreciation"
    )


def _payload() -> dict[str, object]:
    return {
        "asset_key": "machine-1",
        "acquisition_cost": "120000.00",
        "residual_value": "12000.00",
        "useful_life_months": 60,
        "elapsed_months": 12,
    }


def test_authenticated_asset_depreciation_is_persisted_immutably(
    app_db_session: Session,
) -> None:
    organization, calculation, raw_token = _tenant_asset_calculation(
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
    assert body.engine_key == "asset_depreciation"
    assert body.engine_version == "asset-depreciation-v1"
    assert body.output_snapshot["depreciation_for_period"] == "1800.00"
    assert body.output_snapshot["accumulated_depreciation"] == "21600.00"
    assert body.output_snapshot["carrying_amount"] == "98400.00"
    assert body.output_snapshot["statutory_tax_rate_inferred"] is False

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


def test_asset_execution_rejects_numeric_money_before_persistence(
    app_db_session: Session,
) -> None:
    organization, calculation, raw_token = _tenant_asset_calculation(
        app_db_session,
        suffix="numeric-json",
    )
    payload = _payload()
    payload["acquisition_cost"] = 120000.0

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
