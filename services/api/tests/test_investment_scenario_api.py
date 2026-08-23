"""HTTP integration tests for tenant-scoped investment/scenario decision analysis."""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.decision_analysis_models import DecisionAnalysisArtifact
from app.main import app
from app.models import AuditEvent, Organization, OrganizationMembership, User


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_decision_analysis_requires_authentication(app_db_session: Session) -> None:
    _, organization, _ = _tenant(app_db_session, suffix="no-auth")

    response = TestClient(app).post(_path(organization), json=_payload())

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_viewer_member_calculation_is_persisted_with_provenance_and_audit(
    app_db_session: Session,
) -> None:
    user, organization, token = _tenant(app_db_session, suffix="viewer")

    response = TestClient(app).post(
        _path(organization),
        json=_payload(),
        headers=_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    snapshot = body["snapshot"]
    assert snapshot["engine_version"] == "investment-scenario-v1"
    assert snapshot["investment"]["roi_ratio"] == "0.25"
    assert snapshot["investment"]["roe_ratio"] == "0.2"
    assert snapshot["investment"]["roic_ratio"] == "0.15"
    assert [item["profit"] for item in snapshot["scenarios"]] == ["50", "200", "350"]
    assert snapshot["policy"]["scenario_shocks_inferred"] is False
    assert snapshot["inputs"] == _payload()
    assert len(body["input_sha256"]) == 64
    assert len(body["output_sha256"]) == 64

    artifact = app_db_session.get(DecisionAnalysisArtifact, UUID(body["artifact_id"]))
    assert artifact is not None
    assert artifact.organization_id == organization.id
    assert artifact.created_by_user_id == user.id
    assert artifact.engine_version == "investment-scenario-v1"
    assert artifact.input_snapshot == _payload()
    assert artifact.output_snapshot == snapshot
    assert artifact.input_sha256 == body["input_sha256"]
    assert artifact.output_sha256 == body["output_sha256"]

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "decision_analysis.recorded",
            AuditEvent.entity_id == artifact.id,
        )
    )
    assert audit is not None
    assert audit.actor_user_id == user.id
    assert audit.payload["input_sha256"] == artifact.input_sha256
    assert audit.payload["output_sha256"] == artifact.output_sha256


def test_history_list_and_detail_return_persisted_artifacts(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="history")
    client = TestClient(app)
    created_ids: set[str] = set()
    for _ in range(2):
        response = client.post(_path(organization), json=_payload(), headers=_headers(token))
        assert response.status_code == 200
        created_ids.add(response.json()["artifact_id"])

    listed = client.get(
        f"{_path(organization)}?limit=50&offset=0",
        headers=_headers(token),
    )
    assert listed.status_code == 200
    listed_ids = {item["artifact_id"] for item in listed.json()}
    assert created_ids <= listed_ids

    artifact_id = next(iter(created_ids))
    detail = client.get(
        f"{_path(organization)}/{artifact_id}",
        headers=_headers(token),
    )
    assert detail.status_code == 200
    assert detail.json()["artifact_id"] == artifact_id
    assert detail.json()["snapshot"]["inputs"] == _payload()


def test_persisted_artifact_detail_is_tenant_scoped(app_db_session: Session) -> None:
    _, first_org, first_token = _tenant(app_db_session, suffix="artifact-first")
    _, second_org, second_token = _tenant(app_db_session, suffix="artifact-second")
    created = TestClient(app).post(
        _path(first_org),
        json=_payload(),
        headers=_headers(first_token),
    )
    assert created.status_code == 200

    response = TestClient(app).get(
        f"{_path(second_org)}/{created.json()['artifact_id']}",
        headers=_headers(second_token),
    )

    assert response.status_code == 404


def test_direct_artifact_tamper_fails_closed_on_historical_read(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="tamper")
    created = TestClient(app).post(
        _path(organization),
        json=_payload(),
        headers=_headers(token),
    )
    assert created.status_code == 200
    artifact = app_db_session.get(
        DecisionAnalysisArtifact,
        UUID(created.json()["artifact_id"]),
    )
    assert artifact is not None
    artifact.output_snapshot = {"tampered": True}
    app_db_session.flush()

    response = TestClient(app).get(
        f"{_path(organization)}/{artifact.id}",
        headers=_headers(token),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "analysis integrity check failed"


def test_authenticated_user_cannot_cross_tenant_boundary(app_db_session: Session) -> None:
    _, first_org, token = _tenant(app_db_session, suffix="first", role="owner")
    _, second_org, _ = _tenant(app_db_session, suffix="second", role="owner")

    response = TestClient(app).post(
        _path(second_org),
        json=_payload(),
        headers=_headers(token),
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
        headers=_headers(token),
    )

    assert response.status_code == 422


def test_non_finite_decimal_string_is_rejected(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="non-finite")
    payload = _payload()
    payload["net_return"] = "NaN"

    response = TestClient(app).post(
        _path(organization),
        json=payload,
        headers=_headers(token),
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
        headers=_headers(token),
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
        headers=_headers(token),
    )

    assert response.status_code == 200
    profits = [item["profit"] for item in response.json()["snapshot"]["scenarios"]]
    expected_profit = (
        "999999999999999999999999999999999999999999999999999999999999"
        "999999999999999999999999999999999999999999999999999999999999"
    )
    assert profits[0] == expected_profit


def test_mislabeled_scenario_profit_order_fails_closed(app_db_session: Session) -> None:
    _, organization, token = _tenant(app_db_session, suffix="ordering")
    payload = _payload()
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    scenarios[0] = {"key": "pessimistic", "revenue": "1400", "costs": "900"}

    response = TestClient(app).post(
        _path(organization),
        json=payload,
        headers=_headers(token),
    )

    assert response.status_code == 422
    assert "scenario profit ordering" in response.json()["detail"]
