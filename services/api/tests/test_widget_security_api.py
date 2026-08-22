"""PostgreSQL integration tests for widget origin lock and atomic quota enforcement."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import (
    AuditEvent,
    Calculation,
    CalculationVersion,
    Organization,
    OrganizationMembership,
    PublicCalculationProjection,
    User,
    WidgetAllowedOrigin,
    WidgetDeployment,
    WidgetUsageBucket,
)
from app.widget_api import WidgetAllowedOriginResponse, WidgetDeploymentResponse
from app.widget_security import WidgetQuotaExceeded, consume_widget_projection

_PRIVATE_SENTINEL = "PRIVATE-WIDGET-COST-883"
_ALLOWED_ORIGIN = "https://shop.example.test"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tenant_projection(
    session: Session,
    *,
    suffix: str,
    role: str = "owner",
) -> tuple[User, Organization, PublicCalculationProjection, str]:
    user = User(email=f"widget-{suffix}@example.test", display_name=f"Widget {suffix}")
    organization = Organization(slug=f"widget-{suffix}", legal_name=f"Widget {suffix} Org")
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
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=user.id,
        name="Widget private source",
        calculation_type="trade",
    )
    session.add(calculation)
    session.flush()
    version = CalculationVersion(
        organization_id=organization.id,
        calculation_id=calculation.id,
        created_by_user_id=user.id,
        version=1,
        engine_key="trade",
        engine_version="widget-test-v1",
        input_snapshot={"private_cost": _PRIVATE_SENTINEL},
        input_sha256=_digest(f"input-{suffix}"),
        ruleset_snapshot={"private_rules": _PRIVATE_SENTINEL},
        ruleset_sha256=_digest(f"rules-{suffix}"),
        output_snapshot={"private_margin": _PRIVATE_SENTINEL},
        output_sha256=_digest(f"output-{suffix}"),
    )
    session.add(version)
    session.flush()
    projection = PublicCalculationProjection(
        organization_id=organization.id,
        calculation_version_id=version.id,
        created_by_user_id=user.id,
        token_sha256=_digest(f"public-token-{suffix}"),
        title="Musteri fiyat araligi",
        currency="TRY",
        estimate_min="1200.50",
        estimate_max="1500.75",
    )
    session.add(projection)
    session.flush()
    _, auth_token = issue_session(session, user_id=user.id)
    return user, organization, projection, auth_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_deployment(
    client: TestClient,
    *,
    organization: Organization,
    projection: PublicCalculationProjection,
    token: str,
    hourly_request_limit: int = 10,
    allowed_origins: list[str] | None = None,
) -> WidgetDeploymentResponse:
    response = client.post(
        f"/organizations/{organization.id}/widget-deployments",
        headers=_headers(token),
        json={
            "public_projection_id": str(projection.id),
            "name": "Checkout estimate",
            "hourly_request_limit": hourly_request_limit,
            "allowed_origins": allowed_origins or [_ALLOWED_ORIGIN],
        },
    )
    assert response.status_code == 201, response.text
    return WidgetDeploymentResponse.model_validate(response.json())


def _public_path(deployment_id: UUID) -> str:
    return f"/organizations/widget/deployments/{deployment_id}/projection"


def test_owner_creates_deployment_with_normalized_origins_and_audit(
    app_db_session: Session,
) -> None:
    _, organization, projection, token = _tenant_projection(
        app_db_session,
        suffix="create",
    )
    client = TestClient(app)

    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
        hourly_request_limit=25,
        allowed_origins=["https://Shop.Example.Test/", "https://portal.example.test:8443"],
    )

    assert deployment.public_projection_id == projection.id
    assert deployment.hourly_request_limit == 25
    assert [item.origin for item in deployment.allowed_origins] == [
        "https://shop.example.test",
        "https://portal.example.test:8443",
    ]
    stored = app_db_session.get(WidgetDeployment, deployment.id)
    assert stored is not None
    assert stored.organization_id == organization.id

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "widget_deployment.created",
            AuditEvent.entity_id == deployment.id,
        )
    )
    assert audit is not None
    assert audit.payload["hourly_request_limit"] == 25
    assert "token_sha256" not in str(audit.payload)


def test_public_widget_requires_exact_origin_and_never_trusts_referer(
    app_db_session: Session,
) -> None:
    _, organization, projection, token = _tenant_projection(
        app_db_session,
        suffix="origin",
    )
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
    )
    path = _public_path(deployment.id)

    valid = client.get(path, headers={"Origin": _ALLOWED_ORIGIN})
    assert valid.status_code == 200
    assert valid.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
    assert valid.headers["vary"] == "Origin"
    assert valid.headers["cache-control"] == "no-store"
    assert valid.headers["x-ratelimit-limit"] == "10"
    assert valid.headers["x-ratelimit-remaining"] == "9"
    assert set(valid.json()) == {
        "title",
        "currency",
        "estimate_min",
        "estimate_max",
        "published_at",
    }
    assert _PRIVATE_SENTINEL not in valid.text
    assert str(organization.id) not in valid.text
    assert str(projection.id) not in valid.text

    missing_origin = client.get(path, headers={"Referer": f"{_ALLOWED_ORIGIN}/checkout"})
    assert missing_origin.status_code == 403
    subdomain = client.get(path, headers={"Origin": "https://sub.shop.example.test"})
    assert subdomain.status_code == 403
    insecure = client.get(path, headers={"Origin": "http://shop.example.test"})
    assert insecure.status_code == 403

    usage = app_db_session.scalar(
        select(WidgetUsageBucket).where(WidgetUsageBucket.widget_deployment_id == deployment.id)
    )
    assert usage is not None
    assert usage.request_count == 1


@pytest.mark.parametrize(
    "origins",
    [
        ["http://shop.example.test"],
        ["https://*.example.test"],
        ["https://127.0.0.1"],
        ["https://shop.example.test/path"],
        ["https://shop.example.test", "https://SHOP.EXAMPLE.TEST/"],
    ],
)
def test_deployment_rejects_non_exact_or_duplicate_origins(
    app_db_session: Session,
    origins: list[str],
) -> None:
    suffix_hash = hashlib.sha256(str(origins).encode()).hexdigest()[:8]
    _, organization, projection, token = _tenant_projection(
        app_db_session,
        suffix=f"invalid-{suffix_hash}",
    )
    response = TestClient(app).post(
        f"/organizations/{organization.id}/widget-deployments",
        headers=_headers(token),
        json={
            "public_projection_id": str(projection.id),
            "name": "Invalid widget",
            "hourly_request_limit": 10,
            "allowed_origins": origins,
        },
    )
    assert response.status_code == 422
    assert app_db_session.scalar(select(WidgetDeployment.id)) is None


def test_origin_add_remove_takes_effect_immediately(app_db_session: Session) -> None:
    _, organization, projection, token = _tenant_projection(
        app_db_session,
        suffix="origin-mutation",
    )
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
    )
    second_origin = "https://portal.example.test"
    add_response = client.post(
        f"/organizations/{organization.id}/widget-deployments/{deployment.id}/allowed-origins",
        headers=_headers(token),
        json={"origin": second_origin},
    )
    assert add_response.status_code == 201
    added = WidgetAllowedOriginResponse.model_validate(add_response.json())
    assert added.origin == second_origin
    assert (
        client.get(
            _public_path(deployment.id),
            headers={"Origin": second_origin},
        ).status_code
        == 200
    )

    remove_response = client.delete(
        f"/organizations/{organization.id}/widget-deployments/{deployment.id}"
        f"/allowed-origins/{added.id}",
        headers=_headers(token),
    )
    assert remove_response.status_code == 204
    assert (
        client.get(
            _public_path(deployment.id),
            headers={"Origin": second_origin},
        ).status_code
        == 403
    )
    assert (
        client.get(
            _public_path(deployment.id),
            headers={"Origin": _ALLOWED_ORIGIN},
        ).status_code
        == 200
    )


def test_http_quota_and_domain_bucket_reset_are_enforced(app_db_session: Session) -> None:
    _, organization, projection, token = _tenant_projection(
        app_db_session,
        suffix="quota",
    )
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
        hourly_request_limit=2,
    )
    path = _public_path(deployment.id)

    first = client.get(path, headers={"Origin": _ALLOWED_ORIGIN})
    second = client.get(path, headers={"Origin": _ALLOWED_ORIGIN})
    third = client.get(path, headers={"Origin": _ALLOWED_ORIGIN})
    assert first.status_code == 200
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.status_code == 200
    assert second.headers["x-ratelimit-remaining"] == "0"
    assert third.status_code == 429
    assert third.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
    assert third.headers["vary"] == "Origin"
    assert third.headers["cache-control"] == "no-store"
    assert third.headers["x-ratelimit-limit"] == "2"
    assert third.headers["x-ratelimit-remaining"] == "0"
    assert int(third.headers["retry-after"]) >= 1

    fixed_hour = datetime(2030, 1, 1, 10, 5, tzinfo=UTC)
    separate = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
        hourly_request_limit=1,
        allowed_origins=["https://reset.example.test"],
    )
    first_bucket = consume_widget_projection(
        app_db_session,
        deployment_id=separate.id,
        raw_origin="https://reset.example.test",
        now=fixed_hour,
    )
    assert first_bucket.request_count == 1
    with pytest.raises(WidgetQuotaExceeded):
        consume_widget_projection(
            app_db_session,
            deployment_id=separate.id,
            raw_origin="https://reset.example.test",
            now=fixed_hour + timedelta(minutes=10),
        )
    next_bucket = consume_widget_projection(
        app_db_session,
        deployment_id=separate.id,
        raw_origin="https://reset.example.test",
        now=fixed_hour + timedelta(hours=1),
    )
    assert next_bucket.request_count == 1


def test_only_owner_admin_manage_and_cross_tenant_projection_fails_closed(
    app_db_session: Session,
) -> None:
    owner, organization, projection, owner_token = _tenant_projection(
        app_db_session,
        suffix="roles-owner",
    )
    accountant, _, _, accountant_token = _tenant_projection(
        app_db_session,
        suffix="roles-accountant",
        role="accountant",
    )
    admin, _, _, admin_token = _tenant_projection(
        app_db_session,
        suffix="roles-admin",
        role="admin",
    )
    app_db_session.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=accountant.id,
                role="accountant",
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=admin.id,
                role="admin",
            ),
        ]
    )
    app_db_session.flush()
    client = TestClient(app)
    path = f"/organizations/{organization.id}/widget-deployments"
    payload = {
        "public_projection_id": str(projection.id),
        "name": "Role widget",
        "hourly_request_limit": 10,
        "allowed_origins": [_ALLOWED_ORIGIN],
    }

    assert client.post(path, headers=_headers(accountant_token), json=payload).status_code == 403
    assert client.post(path, headers=_headers(admin_token), json=payload).status_code == 201

    _, other_org, other_projection, other_token = _tenant_projection(
        app_db_session,
        suffix="roles-other",
    )
    assert other_org.id != organization.id
    assert client.post(path, headers=_headers(other_token), json=payload).status_code == 403

    cross_payload = dict(payload)
    cross_payload["public_projection_id"] = str(other_projection.id)
    assert client.post(path, headers=_headers(owner_token), json=cross_payload).status_code == 404
    assert owner.id != accountant.id


def test_disable_and_projection_revoke_stop_widget_resolution(app_db_session: Session) -> None:
    _, organization, projection, token = _tenant_projection(
        app_db_session,
        suffix="disable",
    )
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
    )
    path = _public_path(deployment.id)
    assert client.get(path, headers={"Origin": _ALLOWED_ORIGIN}).status_code == 200

    disable_path = f"/organizations/{organization.id}/widget-deployments/{deployment.id}"
    assert client.delete(disable_path, headers=_headers(token)).status_code == 204
    assert client.delete(disable_path, headers=_headers(token)).status_code == 204
    assert client.get(path, headers={"Origin": _ALLOWED_ORIGIN}).status_code == 404
    disable_audits = app_db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "widget_deployment.disabled",
            AuditEvent.entity_id == deployment.id,
        )
    ).all()
    assert len(disable_audits) == 1

    second = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
        allowed_origins=["https://revoked.example.test"],
    )
    projection.revoked_at = datetime.now(UTC)
    app_db_session.flush()
    assert (
        client.get(
            _public_path(second.id),
            headers={"Origin": "https://revoked.example.test"},
        ).status_code
        == 404
    )


def test_database_rejects_cross_tenant_widget_projection(app_db_session: Session) -> None:
    user_a, _, projection_a, _ = _tenant_projection(app_db_session, suffix="fk-a")
    _, organization_b, _, _ = _tenant_projection(app_db_session, suffix="fk-b")
    app_db_session.add(
        OrganizationMembership(
            organization_id=organization_b.id,
            user_id=user_a.id,
            role="owner",
        )
    )
    app_db_session.flush()
    invalid = WidgetDeployment(
        organization_id=organization_b.id,
        public_projection_id=projection_a.id,
        created_by_user_id=user_a.id,
        name="Invalid cross tenant",
        hourly_request_limit=10,
    )
    app_db_session.add(invalid)
    with pytest.raises(IntegrityError):
        app_db_session.flush()
    app_db_session.rollback()


def test_atomic_quota_allows_only_one_concurrent_request(db_engine) -> None:
    suffix = "quota-concurrency"
    fixed_hour = datetime(2031, 2, 3, 12, 15, tzinfo=UTC)
    with Session(db_engine, expire_on_commit=False) as setup:
        user, organization, projection, _ = _tenant_projection(setup, suffix=suffix)
        deployment = WidgetDeployment(
            organization_id=organization.id,
            public_projection_id=projection.id,
            created_by_user_id=user.id,
            name="Concurrent quota",
            hourly_request_limit=1,
        )
        setup.add(deployment)
        setup.flush()
        setup.add(
            WidgetAllowedOrigin(
                organization_id=organization.id,
                widget_deployment_id=deployment.id,
                created_by_user_id=user.id,
                origin="https://concurrent.example.test",
            )
        )
        setup.commit()
        deployment_id = deployment.id
        organization_id = organization.id
        projection_id = projection.id
        user_id = user.id

    barrier = Barrier(2)

    def consume_once() -> str:
        with Session(db_engine) as worker:
            barrier.wait()
            try:
                consume_widget_projection(
                    worker,
                    deployment_id=deployment_id,
                    raw_origin="https://concurrent.example.test",
                    now=fixed_hour,
                )
                worker.commit()
            except WidgetQuotaExceeded:
                worker.rollback()
                return "quota"
            return "ok"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume_once(), range(2)))
    assert sorted(results) == ["ok", "quota"]

    with Session(db_engine) as verify:
        bucket = verify.scalar(
            select(WidgetUsageBucket).where(
                WidgetUsageBucket.widget_deployment_id == deployment_id,
                WidgetUsageBucket.bucket_start
                == fixed_hour.replace(minute=0, second=0, microsecond=0),
            )
        )
        assert bucket is not None
        assert bucket.request_count == 1

        verify.execute(delete(WidgetDeployment).where(WidgetDeployment.id == deployment_id))
        verify.execute(
            delete(PublicCalculationProjection).where(
                PublicCalculationProjection.id == projection_id
            )
        )
        calculation_ids = verify.scalars(
            select(Calculation.id).where(Calculation.organization_id == organization_id)
        ).all()
        if calculation_ids:
            verify.execute(
                delete(CalculationVersion).where(
                    CalculationVersion.calculation_id.in_(calculation_ids)
                )
            )
            verify.execute(delete(Calculation).where(Calculation.id.in_(calculation_ids)))
        verify.execute(
            delete(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        verify.execute(delete(Organization).where(Organization.id == organization_id))
        verify.execute(delete(User).where(User.id == user_id))
        verify.commit()
