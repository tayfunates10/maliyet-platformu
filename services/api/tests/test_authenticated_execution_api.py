"""HTTP integration tests for authenticated tenant calculation execution."""

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.http_dependencies import get_database_session
from app.main import app
from app.models import (
    AuditEvent,
    Calculation,
    CalculationVersion,
    Organization,
    OrganizationMembership,
    User,
)


def _install_database_override(db_session: Session) -> None:
    """Inject the real test Session through FastAPI's generator dependency protocol."""

    def override_database() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_database_session] = override_database


def _trade_payload() -> dict[str, object]:
    return {
        "sales": [
            {
                "key": "sale",
                "quantity": "2",
                "unit_sale_price": "100.00",
                "unit_acquisition_cost": "40.00",
            }
        ]
    }


def _tenant_calculation(
    db_session: Session,
    *,
    suffix: str,
    role: str,
) -> tuple[User, Organization, Calculation, str]:
    user = User(email=f"exec-{suffix}@example.test", display_name=f"Exec {suffix}")
    organization = Organization(slug=f"exec-{suffix}", legal_name=f"Exec {suffix} Org")
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
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="Trade order",
        calculation_type="trade",
    )
    db_session.add(calculation)
    db_session.flush()
    _, raw_token = issue_session(db_session, user_id=user.id)
    return user, organization, calculation, raw_token


def _path(organization: Organization, calculation: Calculation) -> str:
    return f"/organizations/{organization.id}/calculations/{calculation.id}/execute/trade"


def test_execution_requires_bearer_authentication(db_session: Session) -> None:
    _, organization, calculation, _ = _tenant_calculation(
        db_session,
        suffix="no-auth",
        role="owner",
    )
    _install_database_override(db_session)
    try:
        response = TestClient(app).post(_path(organization, calculation), json=_trade_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert db_session.scalar(select(CalculationVersion.id)) is None


def test_viewer_membership_cannot_execute_calculation(db_session: Session) -> None:
    _, organization, calculation, raw_token = _tenant_calculation(
        db_session,
        suffix="viewer",
        role="viewer",
    )
    _install_database_override(db_session)
    try:
        response = TestClient(app).post(
            _path(organization, calculation),
            json=_trade_payload(),
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert db_session.scalar(select(CalculationVersion.id)) is None


def test_authenticated_writer_is_the_persisted_actor(db_session: Session) -> None:
    user, organization, calculation, raw_token = _tenant_calculation(
        db_session,
        suffix="writer",
        role="analyst",
    )
    _install_database_override(db_session)
    try:
        response = TestClient(app).post(
            _path(organization, calculation),
            json=_trade_payload(),
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["calculation_id"] == str(calculation.id)
    assert body["engine_key"] == "trade"
    assert body["version"] == 1
    assert body["output_snapshot"]["contribution_profit"] == "120.00"

    version = db_session.scalar(
        select(CalculationVersion).where(CalculationVersion.calculation_id == calculation.id)
    )
    assert version is not None
    assert version.created_by_user_id == user.id
    assert version.id == body["calculation_version_id"]

    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.entity_id == version.id,
        )
    )
    assert audit is not None
    assert audit.actor_user_id == user.id


def test_request_body_cannot_spoof_actor_identity(db_session: Session) -> None:
    user, organization, calculation, raw_token = _tenant_calculation(
        db_session,
        suffix="spoof",
        role="owner",
    )
    other = User(email="other-actor@example.test", display_name="Other actor")
    db_session.add(other)
    db_session.flush()

    payload = _trade_payload()
    payload["created_by_user_id"] = str(other.id)
    _install_database_override(db_session)
    try:
        response = TestClient(app).post(
            _path(organization, calculation),
            json=payload,
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert user.id != other.id
    assert db_session.scalar(select(CalculationVersion.id)) is None


def test_authenticated_user_cannot_cross_tenant_boundary(db_session: Session) -> None:
    _, organization, _, raw_token = _tenant_calculation(
        db_session,
        suffix="tenant-a",
        role="owner",
    )
    _, other_org, other_calculation, _ = _tenant_calculation(
        db_session,
        suffix="tenant-b",
        role="owner",
    )
    path = f"/organizations/{other_org.id}/calculations/{other_calculation.id}/execute/trade"
    _install_database_override(db_session)
    try:
        response = TestClient(app).post(
            path,
            json=_trade_payload(),
            headers={"Authorization": f"Bearer {raw_token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert organization.id != other_org.id
    assert db_session.scalar(select(CalculationVersion.id)) is None
