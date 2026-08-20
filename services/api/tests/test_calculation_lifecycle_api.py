"""Tenant-scoped calculation lifecycle API integration tests."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import CalculationResponse, CalculationVersionResponse, app
from app.models import (
    AuditEvent,
    Calculation,
    Organization,
    OrganizationMembership,
    User,
)


def _tenant(
    session: Session,
    *,
    suffix: str,
    role: str = "owner",
) -> tuple[User, Organization, str]:
    user = User(email=f"lifecycle-{suffix}@example.test", display_name=f"Lifecycle {suffix}")
    organization = Organization(slug=f"lifecycle-{suffix}", legal_name=f"Lifecycle {suffix} Org")
    session.add_all([user, organization])
    session.flush()
    session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
        )
    )
    session.flush()
    _, raw_token = issue_session(session, user_id=user.id)
    return user, organization, raw_token


def _add_member(
    session: Session,
    *,
    organization: Organization,
    suffix: str,
    role: str,
) -> tuple[User, str]:
    user = User(email=f"lifecycle-{suffix}@example.test", display_name=f"Lifecycle {suffix}")
    session.add(user)
    session.flush()
    session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
        )
    )
    session.flush()
    _, raw_token = issue_session(session, user_id=user.id)
    return user, raw_token


def _headers(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


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


def test_create_calculation_requires_authentication(app_db_session: Session) -> None:
    _, organization, _ = _tenant(app_db_session, suffix="unauth")

    response = TestClient(app).post(
        f"/organizations/{organization.id}/calculations",
        json={"name": "Order", "calculation_type": "trade"},
    )

    assert response.status_code == 401
    assert app_db_session.scalar(select(func.count()).select_from(Calculation)) == 0


def test_authenticated_writer_creates_calculation_and_audit(app_db_session: Session) -> None:
    user, organization, raw_token = _tenant(app_db_session, suffix="create", role="analyst")

    response = TestClient(app).post(
        f"/organizations/{organization.id}/calculations",
        json={"name": "Trade order", "calculation_type": "trade"},
        headers=_headers(raw_token),
    )

    assert response.status_code == 201
    body = CalculationResponse.model_validate(response.json())
    assert body.organization_id == organization.id
    assert body.created_by_user_id == user.id
    assert body.name == "Trade order"
    assert body.calculation_type == "trade"

    persisted = app_db_session.scalar(select(Calculation).where(Calculation.id == body.id))
    assert persisted is not None
    assert persisted.created_by_user_id == user.id

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.entity_id == body.id,
            AuditEvent.event_type == "calculation.created",
        )
    )
    assert audit is not None
    assert audit.actor_user_id == user.id


def test_viewer_is_read_only_but_can_list_and_get(app_db_session: Session) -> None:
    owner, organization, _ = _tenant(app_db_session, suffix="viewer-owner", role="owner")
    _, viewer_token = _add_member(
        app_db_session,
        organization=organization,
        suffix="viewer",
        role="viewer",
    )
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="Visible calculation",
        calculation_type="trade",
    )
    app_db_session.add(calculation)
    app_db_session.flush()

    create_response = TestClient(app).post(
        f"/organizations/{organization.id}/calculations",
        json={"name": "Forbidden", "calculation_type": "trade"},
        headers=_headers(viewer_token),
    )
    list_response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations",
        headers=_headers(viewer_token),
    )
    get_response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations/{calculation.id}",
        headers=_headers(viewer_token),
    )

    assert create_response.status_code == 403
    assert list_response.status_code == 200
    listed = [CalculationResponse.model_validate(item) for item in list_response.json()]
    assert [item.id for item in listed] == [calculation.id]
    assert get_response.status_code == 200
    assert CalculationResponse.model_validate(get_response.json()).id == calculation.id


def test_cross_tenant_reads_fail_closed(app_db_session: Session) -> None:
    _, organization_a, token_a = _tenant(app_db_session, suffix="tenant-a", role="owner")
    owner_b, organization_b, _ = _tenant(app_db_session, suffix="tenant-b", role="owner")
    calculation_b = Calculation(
        organization_id=organization_b.id,
        created_by_user_id=owner_b.id,
        name="Tenant B private",
        calculation_type="trade",
    )
    app_db_session.add(calculation_b)
    app_db_session.flush()

    list_response = TestClient(app).get(
        f"/organizations/{organization_b.id}/calculations",
        headers=_headers(token_a),
    )
    get_response = TestClient(app).get(
        f"/organizations/{organization_b.id}/calculations/{calculation_b.id}",
        headers=_headers(token_a),
    )

    assert organization_a.id != organization_b.id
    assert list_response.status_code == 403
    assert get_response.status_code == 403


def test_unsupported_calculation_type_is_rejected_before_persistence(
    app_db_session: Session,
) -> None:
    _, organization, raw_token = _tenant(app_db_session, suffix="unsupported", role="owner")

    response = TestClient(app).post(
        f"/organizations/{organization.id}/calculations",
        json={"name": "Unknown", "calculation_type": "caller_supplied_engine"},
        headers=_headers(raw_token),
    )

    assert response.status_code == 422
    assert app_db_session.scalar(select(func.count()).select_from(Calculation)) == 0


def test_version_history_is_readable_after_authenticated_execution(
    app_db_session: Session,
) -> None:
    owner, organization, raw_token = _tenant(app_db_session, suffix="history", role="owner")
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="History calculation",
        calculation_type="trade",
    )
    app_db_session.add(calculation)
    app_db_session.flush()

    execute_response = TestClient(app).post(
        f"/organizations/{organization.id}/calculations/{calculation.id}/execute/trade",
        json=_trade_payload(),
        headers=_headers(raw_token),
    )
    assert execute_response.status_code == 201

    list_response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions",
        headers=_headers(raw_token),
    )
    get_response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1",
        headers=_headers(raw_token),
    )

    assert list_response.status_code == 200
    history = [CalculationVersionResponse.model_validate(item) for item in list_response.json()]
    assert len(history) == 1
    assert history[0].calculation_id == calculation.id
    assert history[0].version == 1
    assert history[0].input_sha256 is not None
    assert history[0].ruleset_sha256 is not None
    assert history[0].output_sha256 is not None

    assert get_response.status_code == 200
    exact = CalculationVersionResponse.model_validate(get_response.json())
    assert exact.id == history[0].id
    assert exact.output_snapshot == history[0].output_snapshot


def test_list_pagination_is_bounded(app_db_session: Session) -> None:
    _, organization, raw_token = _tenant(app_db_session, suffix="pagination", role="owner")

    response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations?limit=101",
        headers=_headers(raw_token),
    )

    assert response.status_code == 422
