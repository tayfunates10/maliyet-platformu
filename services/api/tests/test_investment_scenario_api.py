"""HTTP integration tests for tenant-scoped investment/scenario decision analysis."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import Organization, OrganizationMembership, User


def _tenant(
    db_session: Session,
    *,
    suffix: str,
    role: str = "viewer",
) -> tuple[User, Organization, str]:
    user = User(email=f"decision-{suffix}@example.test", display_name=f"Decision {suffix}")
    organization = Organization(slug=f"decision-{suffix}", legal_name=f"Decision {suffix} Org")
    db_session.add_all([user, organization])
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
        )
    )
    db_session.flush()
    _, token = issue_session(db_session, user_id=user.id)
    return user, organization, token


def _payload() -> dict[str, object]:
    return {
        "initial_investment": "1000",
        "net_return": "250",
        "equity": "500",
        "net_income": "100",
        "invested_capital": "800",
        "net_operating_profit_after_tax": "120",
        "scenarios": [
            {"key": "pessimistic", "revenue": "900", "costs": "850"},
            {"key": "normal", "revenue": "1100", "costs": "900"},
            {"key": "optimistic", "revenue": "1300", "costs": "950"},
        ],
    }


def _path(organization: Organization) -> str:
    return f"/organizations/{organization.id}/decision-analysis/investment-scenarios"


def test_decision_analysis_requires_authentication(app_db_session: Session) -> None:
    _, organization, _ = _tenant(app_db_session, suffix="no-auth")

    response = TestClient(app).post(_path(organization), json=_payload())

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_viewer_member_can_calculate_tenant_private_analysis(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="viewer")

    response = TestClient(app).post(
        _path(organization),
        json=_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["engine_version"] == "investment-scenario-v1"
    assert snapshot["investment"]["roi_ratio"] == "0.25"
    assert snapshot["investment"]["roe_ratio"] == "0.2"
    assert snapshot["investment"]["roic_ratio"] == "0.15"
    assert [item["profit"] for item in snapshot["scenarios"]] == ["50", "200", "350"]
    assert snapshot["policy"]["scenario_shocks_inferred"] is False
    assert snapshot["inputs"] == _payload()


def test_authenticated_user_cannot_cross_tenant_boundary(app_db_session: Session) -> None:
    _, first_org, token = _tenant(app_db_session, suffix="first", role="owner")
    _, second_org, _ = _tenant(app_db_session, suffix="second", role="owner")

    response = TestClient(app).post(
        _path(second_org),
        json=_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first_org.id != second_org.id
    assert response.status_code == 403


def test_numeric_json_money_is_rejected_before_engine_execution(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="numeric")
    payload = _payload()
    payload["initial_investment"] = 1000

    response = TestClient(app).post(
        _path(organization),
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_non_finite_decimal_string_is_rejected(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="non-finite")
    payload = _payload()
    payload["net_return"] = "NaN"

    response = TestClient(app).post(
        _path(organization),
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "net_return must be finite"


def test_decimal_exponent_outside_supported_range_is_rejected(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="exponent")
    payload = _payload()
    payload["net_return"] = "1e1000000"

    response = TestClient(app).post(
        _path(organization),
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "net_return exceeds supported decimal exponent range"


def test_large_scenario_values_do_not_use_ambient_decimal_precision(
    app_db_session: Session,
) -> None:
    _, organization, token = _tenant(app_db_session, suffix="large")
    payload = _payload()
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    scenarios[0] = {"key": "pessimistic", "revenue": "1e120", "costs": "1"}
    scenarios[1] = {"key": "normal", "revenue": "2e120", "costs": "1"}
    scenarios[2] = {"key": "optimistic", "revenue": "3e120", "costs": "1"}

    response = TestClient(app).post(
        _path(organization),
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    profits = [item["profit"] for item in response.json()["snapshot"]["scenarios"]]
    assert profits[0] == "999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999"


def test_mislabeled_scenario_profit_order_fails_closed(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="ordering")
    payload = _payload()
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    scenarios[0] = {"key": "pessimistic", "revenue": "1400", "costs": "900"}

    response = TestClient(app).post(
        _path(organization),
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert "scenario profit ordering" in response.json()["detail"]
