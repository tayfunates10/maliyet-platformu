"""PostgreSQL integration tests for customer-safe public calculation projections."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
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
)
from app.public_projection_api import PublicProjectionCreateResponse, PublicProjectionResponse

_PRIVATE_SENTINEL = "SECRET-COST-991"


def _tenant_source(
    session: Session,
    *,
    suffix: str,
    role: str = "owner",
    complete_provenance: bool = True,
) -> tuple[User, Organization, Calculation, CalculationVersion, str]:
    user = User(email=f"public-{suffix}@example.test", display_name=f"Public {suffix}")
    organization = Organization(slug=f"public-{suffix}", legal_name=f"Public {suffix} Org")
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
        name="Private trade economics",
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
        engine_version="test-private-v1",
        input_snapshot={
            "unit_acquisition_cost": _PRIVATE_SENTINEL,
            "supplier": "PRIVATE-SUPPLIER",
        },
        input_sha256="a" * 64 if complete_provenance else None,
        ruleset_snapshot={"private_rule_context": "DO-NOT-PUBLISH"},
        ruleset_sha256="b" * 64 if complete_provenance else None,
        output_snapshot={
            "contribution_profit": _PRIVATE_SENTINEL,
            "contribution_margin_ratio": "0.42",
            "operating_cost": "777.00",
        },
        output_sha256="c" * 64 if complete_provenance else None,
    )
    session.add(version)
    session.flush()
    _, raw_token = issue_session(session, user_id=user.id)
    return user, organization, calculation, version, raw_token


def _headers(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


def _publish_path(
    organization: Organization,
    calculation: Calculation,
    *,
    version_number: int = 1,
) -> str:
    return (
        f"/organizations/{organization.id}/calculations/{calculation.id}"
        f"/versions/{version_number}/public-projections"
    )


def _public_path(share_token: str) -> str:
    return f"/organizations/public/calculation-projections/{share_token}"


def _payload() -> dict[str, object]:
    return {
        "title": "Tahmini musteri fiyati",
        "currency": "try",
        "estimate_min": "1200.50",
        "estimate_max": "1500.75",
    }


def test_owner_can_publish_and_anonymous_response_contains_only_safe_fields(
    app_db_session: Session,
) -> None:
    _, organization, calculation, version, auth_token = _tenant_source(
        app_db_session,
        suffix="safe",
    )
    client = TestClient(app)

    publish_response = client.post(
        _publish_path(organization, calculation),
        headers=_headers(auth_token),
        json=_payload(),
    )

    assert publish_response.status_code == 201
    assert publish_response.headers["cache-control"] == "no-store"
    created = PublicProjectionCreateResponse.model_validate(publish_response.json())
    assert created.currency == "TRY"
    assert created.estimate_min == "1200.5"
    assert created.estimate_max == "1500.75"

    stored = app_db_session.get(PublicCalculationProjection, created.projection_id)
    assert stored is not None
    assert stored.calculation_version_id == version.id
    assert stored.token_sha256 == hashlib.sha256(created.share_token.encode("utf-8")).hexdigest()
    assert stored.token_sha256 != created.share_token

    public_response = client.get(_public_path(created.share_token))
    assert public_response.status_code == 200
    assert public_response.headers["cache-control"] == "no-store"
    public_body = public_response.json()
    assert set(public_body) == {
        "title",
        "currency",
        "estimate_min",
        "estimate_max",
        "published_at",
    }
    public_projection = PublicProjectionResponse.model_validate(public_body)
    assert public_projection.title == "Tahmini musteri fiyati"
    assert public_projection.currency == "TRY"
    serialized = public_response.text
    assert _PRIVATE_SENTINEL not in serialized
    assert "PRIVATE-SUPPLIER" not in serialized
    assert "contribution_profit" not in serialized
    assert "contribution_margin_ratio" not in serialized
    assert "operating_cost" not in serialized
    assert str(organization.id) not in serialized
    assert str(calculation.id) not in serialized
    assert str(version.id) not in serialized

    created_audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "public_projection.created",
            AuditEvent.entity_id == created.projection_id,
        )
    )
    assert created_audit is not None
    assert "share_token" not in created_audit.payload
    assert created.share_token not in str(created_audit.payload)


def test_revoke_invalidates_public_token_and_is_idempotent(app_db_session: Session) -> None:
    _, organization, calculation, _, auth_token = _tenant_source(
        app_db_session,
        suffix="revoke",
    )
    client = TestClient(app)
    published = client.post(
        _publish_path(organization, calculation),
        headers=_headers(auth_token),
        json=_payload(),
    )
    assert published.status_code == 201
    created = PublicProjectionCreateResponse.model_validate(published.json())

    assert client.get(_public_path(created.share_token)).status_code == 200
    revoke_path = (
        f"/organizations/{organization.id}/public-calculation-projections/{created.projection_id}"
    )
    first_revoke = client.delete(revoke_path, headers=_headers(auth_token))
    assert first_revoke.status_code == 204
    assert client.get(_public_path(created.share_token)).status_code == 404
    assert client.get(_public_path("not-a-real-token")).status_code == 404

    second_revoke = client.delete(revoke_path, headers=_headers(auth_token))
    assert second_revoke.status_code == 204
    revoke_audits = app_db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "public_projection.revoked",
            AuditEvent.entity_id == created.projection_id,
        )
    ).all()
    assert len(revoke_audits) == 1


def test_only_owner_or_admin_can_publish_and_cross_tenant_fails_closed(
    app_db_session: Session,
) -> None:
    _, owner_org, owner_calculation, _, owner_token = _tenant_source(
        app_db_session,
        suffix="publisher-owner",
    )
    accountant, _, _, _, accountant_token = _tenant_source(
        app_db_session,
        suffix="publisher-accountant",
        role="accountant",
    )
    admin, _, _, _, admin_token = _tenant_source(
        app_db_session,
        suffix="publisher-admin",
        role="admin",
    )
    app_db_session.add_all(
        [
            OrganizationMembership(
                organization_id=owner_org.id,
                user_id=accountant.id,
                role="accountant",
            ),
            OrganizationMembership(
                organization_id=owner_org.id,
                user_id=admin.id,
                role="admin",
            ),
        ]
    )
    app_db_session.flush()
    client = TestClient(app)
    path = _publish_path(owner_org, owner_calculation)

    accountant_response = client.post(path, headers=_headers(accountant_token), json=_payload())
    assert accountant_response.status_code == 403

    admin_response = client.post(path, headers=_headers(admin_token), json=_payload())
    assert admin_response.status_code == 201

    _, other_org, _, _, other_owner_token = _tenant_source(
        app_db_session,
        suffix="publisher-cross",
    )
    assert other_org.id != owner_org.id
    cross_response = client.post(path, headers=_headers(other_owner_token), json=_payload())
    assert cross_response.status_code == 403

    owner_response = client.post(path, headers=_headers(owner_token), json=_payload())
    assert owner_response.status_code == 201


def test_publication_payload_is_strict_and_private_fields_are_rejected(
    app_db_session: Session,
) -> None:
    _, organization, calculation, _, auth_token = _tenant_source(
        app_db_session,
        suffix="validation",
    )
    client = TestClient(app)
    path = _publish_path(organization, calculation)

    private_payload = _payload()
    private_payload["output_snapshot"] = {"contribution_profit": "9999"}
    assert client.post(path, headers=_headers(auth_token), json=private_payload).status_code == 422

    numeric_payload = _payload()
    numeric_payload["estimate_min"] = 1000
    assert client.post(path, headers=_headers(auth_token), json=numeric_payload).status_code == 422

    invalid_currency = _payload()
    invalid_currency["currency"] = "TR1"
    assert client.post(path, headers=_headers(auth_token), json=invalid_currency).status_code == 422

    reversed_range = _payload()
    reversed_range["estimate_min"] = "2000"
    reversed_range["estimate_max"] = "1000"
    assert client.post(path, headers=_headers(auth_token), json=reversed_range).status_code == 422

    excessive_scale = _payload()
    excessive_scale["estimate_min"] = "1.1234567890123"
    assert client.post(path, headers=_headers(auth_token), json=excessive_scale).status_code == 422

    assert app_db_session.scalar(select(PublicCalculationProjection.id)) is None


def test_incomplete_or_foreign_source_version_cannot_be_published(app_db_session: Session) -> None:
    _, organization, calculation, _, auth_token = _tenant_source(
        app_db_session,
        suffix="incomplete",
        complete_provenance=False,
    )
    client = TestClient(app)

    incomplete = client.post(
        _publish_path(organization, calculation),
        headers=_headers(auth_token),
        json=_payload(),
    )
    assert incomplete.status_code == 409

    missing = client.post(
        _publish_path(organization, calculation, version_number=999),
        headers=_headers(auth_token),
        json=_payload(),
    )
    assert missing.status_code == 404
    assert app_db_session.scalar(select(PublicCalculationProjection.id)) is None


def test_database_rejects_cross_tenant_projection_reference(app_db_session: Session) -> None:
    user_a, _, _, version_a, _ = _tenant_source(
        app_db_session,
        suffix="fk-a",
    )
    _, organization_b, _, _, _ = _tenant_source(
        app_db_session,
        suffix="fk-b",
    )
    app_db_session.add(
        OrganizationMembership(
            organization_id=organization_b.id,
            user_id=user_a.id,
            role="owner",
        )
    )
    app_db_session.flush()

    invalid = PublicCalculationProjection(
        organization_id=organization_b.id,
        calculation_version_id=version_a.id,
        created_by_user_id=user_a.id,
        token_sha256="d" * 64,
        title="Invalid cross-tenant projection",
        currency="TRY",
        estimate_min="1",
        estimate_max="2",
    )
    app_db_session.add(invalid)
    with pytest.raises(IntegrityError):
        app_db_session.flush()
    app_db_session.rollback()
