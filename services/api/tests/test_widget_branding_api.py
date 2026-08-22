"""PostgreSQL integration tests for tenant branding and immutable widget publication."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
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
    WidgetUsageBucket,
)
from app.widget_api import WidgetDeploymentResponse
from app.widget_branding_models import (
    WidgetBrandingProfile,
    WidgetPresentationSnapshot,
    WidgetPublishedPresentation,
)

_PRIVATE_SENTINEL = "PRIVATE-BRANDING-COST-991"
_ALLOWED_ORIGIN = "https://shop.example.test"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tenant_projection(
    session: Session,
    *,
    suffix: str,
    role: str = "owner",
) -> tuple[User, Organization, PublicCalculationProjection, str]:
    user = User(email=f"branding-{suffix}@example.test", display_name=f"Branding {suffix}")
    organization = Organization(slug=f"branding-{suffix}", legal_name=f"Branding {suffix} Org")
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
        name="Branding private source",
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
        engine_version="branding-test-v1",
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
) -> WidgetDeploymentResponse:
    response = client.post(
        f"/organizations/{organization.id}/widget-deployments",
        headers=_headers(token),
        json={
            "public_projection_id": str(projection.id),
            "name": "Checkout estimate",
            "hourly_request_limit": 20,
            "allowed_origins": [_ALLOWED_ORIGIN],
        },
    )
    assert response.status_code == 201, response.text
    return WidgetDeploymentResponse.model_validate(response.json())


def _create_profile(
    client: TestClient,
    *,
    organization: Organization,
    token: str,
    name: str = "Primary brand",
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {"name": name, **overrides}
    response = client.post(
        f"/organizations/{organization.id}/widget-branding-profiles",
        headers=_headers(token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _publish(
    client: TestClient,
    *,
    organization: Organization,
    deployment_id: UUID,
    profile_id: str,
    token: str,
):
    response = client.post(
        f"/organizations/{organization.id}/widget-deployments/{deployment_id}/presentation",
        headers=_headers(token),
        json={"branding_profile_id": profile_id},
    )
    assert response.status_code == 201, response.text
    return response


def _public_projection(client: TestClient, deployment_id: UUID):
    return client.get(
        f"/organizations/widget/deployments/{deployment_id}/projection",
        headers={"Origin": _ALLOWED_ORIGIN},
    )


def test_owner_creates_normalized_profile_and_audit(app_db_session: Session) -> None:
    _, organization, _, token = _tenant_projection(app_db_session, suffix="create")
    client = TestClient(app)

    profile = _create_profile(
        client,
        organization=organization,
        token=token,
        theme="dark",
        light_background_color="#aabbcc",
        error_color="#cc0011",
    )

    assert profile["revision"] == 1
    assert profile["theme"] == "dark"
    assert profile["light_background_color"] == "#AABBCC"
    assert profile["error_color"] == "#CC0011"
    assert profile["font_family"] == "system"

    stored = app_db_session.get(WidgetBrandingProfile, UUID(str(profile["id"])))
    assert stored is not None
    assert stored.organization_id == organization.id

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "widget_branding_profile.created",
            AuditEvent.entity_id == stored.id,
        )
    )
    assert audit is not None
    assert audit.payload == {"revision": 1}
    assert _PRIVATE_SENTINEL not in str(audit.payload)


def test_profile_update_does_not_change_public_snapshot_until_republish(
    app_db_session: Session,
) -> None:
    _, organization, projection, token = _tenant_projection(app_db_session, suffix="immutable")
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
    )
    profile = _create_profile(
        client,
        organization=organization,
        token=token,
        theme="light",
        light_background_color="#112233",
        border_radius_px=8,
    )

    first_publish = _publish(
        client,
        organization=organization,
        deployment_id=deployment.id,
        profile_id=str(profile["id"]),
        token=token,
    )
    assert first_publish.json()["profile_revision"] == 1

    first_public = _public_projection(client, deployment.id)
    assert first_public.status_code == 200
    first_payload = first_public.json()
    assert first_payload["presentation"]["theme"] == "light"
    assert first_payload["presentation"]["light_background_color"] == "#112233"
    assert first_payload["presentation"]["border_radius_px"] == 8
    usage = app_db_session.scalar(
        select(WidgetUsageBucket).where(WidgetUsageBucket.widget_deployment_id == deployment.id)
    )
    assert usage is not None
    assert usage.request_count == 1
    assert _PRIVATE_SENTINEL not in first_public.text
    assert str(organization.id) not in first_public.text
    assert str(profile["id"]) not in first_public.text

    update_response = client.put(
        f"/organizations/{organization.id}/widget-branding-profiles/{profile['id']}",
        headers=_headers(token),
        json={
            "name": "Primary brand",
            "theme": "dark",
            "light_background_color": "#445566",
            "dark_background_color": "#101820",
            "border_radius_px": 16,
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["revision"] == 2

    still_first = _public_projection(client, deployment.id)
    assert still_first.status_code == 200
    assert still_first.json()["presentation"]["theme"] == "light"
    assert still_first.json()["presentation"]["light_background_color"] == "#112233"
    assert still_first.json()["presentation"]["border_radius_px"] == 8

    second_publish = _publish(
        client,
        organization=organization,
        deployment_id=deployment.id,
        profile_id=str(profile["id"]),
        token=token,
    )
    assert second_publish.json()["profile_revision"] == 2

    second_public = _public_projection(client, deployment.id)
    assert second_public.status_code == 200
    assert second_public.json()["presentation"]["theme"] == "dark"
    assert second_public.json()["presentation"]["light_background_color"] == "#445566"
    assert second_public.json()["presentation"]["dark_background_color"] == "#101820"
    assert second_public.json()["presentation"]["border_radius_px"] == 16

    snapshots = app_db_session.scalars(
        select(WidgetPresentationSnapshot)
        .where(WidgetPresentationSnapshot.organization_id == organization.id)
        .order_by(WidgetPresentationSnapshot.profile_revision)
    ).all()
    assert [snapshot.profile_revision for snapshot in snapshots] == [1, 2]
    assert [snapshot.light_background_color for snapshot in snapshots] == [
        "#112233",
        "#445566",
    ]


def test_unpublished_deployment_preserves_legacy_public_payload(app_db_session: Session) -> None:
    _, organization, projection, token = _tenant_projection(app_db_session, suffix="legacy")
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
    )

    response = _public_projection(client, deployment.id)

    assert response.status_code == 200
    assert set(response.json()) == {
        "title",
        "currency",
        "estimate_min",
        "estimate_max",
        "published_at",
    }


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("light_background_color", "red; background:url(https://evil.test/x)"),
        ("dark_text_color", "#12345G"),
        ("border_radius_px", 99),
        ("font_family", "url(https://evil.test/font.woff2)"),
        ("theme", "<script>alert(1)</script>"),
    ],
)
def test_profile_rejects_arbitrary_presentation_inputs(
    app_db_session: Session,
    field: str,
    invalid_value: object,
) -> None:
    _, organization, _, token = _tenant_projection(
        app_db_session,
        suffix=f"invalid-{field}",
    )
    client = TestClient(app)

    response = client.post(
        f"/organizations/{organization.id}/widget-branding-profiles",
        headers=_headers(token),
        json={"name": "Unsafe", field: invalid_value},
    )

    assert response.status_code == 422
    assert app_db_session.scalar(select(func.count()).select_from(WidgetBrandingProfile)) == 0


def test_non_admin_cannot_manage_branding_profiles(app_db_session: Session) -> None:
    _, organization, _, token = _tenant_projection(
        app_db_session,
        suffix="viewer",
        role="viewer",
    )
    client = TestClient(app)

    create_response = client.post(
        f"/organizations/{organization.id}/widget-branding-profiles",
        headers=_headers(token),
        json={"name": "Denied"},
    )
    list_response = client.get(
        f"/organizations/{organization.id}/widget-branding-profiles",
        headers=_headers(token),
    )

    assert create_response.status_code == 403
    assert list_response.status_code == 403
    assert app_db_session.scalar(select(func.count()).select_from(WidgetBrandingProfile)) == 0


def test_revoked_projection_blocks_branding_publication(app_db_session: Session) -> None:
    _, organization, projection, token = _tenant_projection(
        app_db_session,
        suffix="revoked",
    )
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
    )
    profile = _create_profile(
        client,
        organization=organization,
        token=token,
    )
    projection.revoked_at = datetime.now(UTC)
    app_db_session.flush()

    response = client.post(
        f"/organizations/{organization.id}/widget-deployments/{deployment.id}/presentation",
        headers=_headers(token),
        json={"branding_profile_id": profile["id"]},
    )

    assert response.status_code == 404
    assert app_db_session.get(WidgetPublishedPresentation, deployment.id) is None
    assert app_db_session.scalar(select(func.count()).select_from(WidgetPresentationSnapshot)) == 0


def test_cross_tenant_profile_cannot_be_published_to_deployment(
    app_db_session: Session,
) -> None:
    _, organization_a, _, token_a = _tenant_projection(app_db_session, suffix="tenant-a")
    _, organization_b, projection_b, token_b = _tenant_projection(
        app_db_session,
        suffix="tenant-b",
    )
    client = TestClient(app)
    profile_a = _create_profile(
        client,
        organization=organization_a,
        token=token_a,
    )
    deployment_b = _create_deployment(
        client,
        organization=organization_b,
        projection=projection_b,
        token=token_b,
    )

    response = client.post(
        f"/organizations/{organization_b.id}/widget-deployments/{deployment_b.id}/presentation",
        headers=_headers(token_b),
        json={"branding_profile_id": profile_a["id"]},
    )

    assert response.status_code == 404
    assert app_db_session.get(WidgetPublishedPresentation, deployment_b.id) is None


def test_database_rejects_cross_tenant_published_snapshot_pointer(
    app_db_session: Session,
) -> None:
    user_a, organization_a, projection_a, token_a = _tenant_projection(
        app_db_session,
        suffix="db-a",
    )
    user_b, organization_b, projection_b, token_b = _tenant_projection(
        app_db_session,
        suffix="db-b",
    )
    client = TestClient(app)
    deployment_a = _create_deployment(
        client,
        organization=organization_a,
        projection=projection_a,
        token=token_a,
    )
    deployment_b = _create_deployment(
        client,
        organization=organization_b,
        projection=projection_b,
        token=token_b,
    )
    profile_a = _create_profile(
        client,
        organization=organization_a,
        token=token_a,
    )
    _publish(
        client,
        organization=organization_a,
        deployment_id=deployment_a.id,
        profile_id=str(profile_a["id"]),
        token=token_a,
    )
    published_snapshot_a = app_db_session.scalar(
        select(WidgetPresentationSnapshot).where(
            WidgetPresentationSnapshot.organization_id == organization_a.id
        )
    )
    assert published_snapshot_a is not None
    unreferenced_snapshot_a = WidgetPresentationSnapshot(
        organization_id=organization_a.id,
        branding_profile_id=UUID(str(profile_a["id"])),
        created_by_user_id=user_a.id,
        profile_revision=1,
        theme=published_snapshot_a.theme,
        locale=published_snapshot_a.locale,
        density=published_snapshot_a.density,
        show_title=published_snapshot_a.show_title,
        light_background_color=published_snapshot_a.light_background_color,
        light_text_color=published_snapshot_a.light_text_color,
        light_border_color=published_snapshot_a.light_border_color,
        dark_background_color=published_snapshot_a.dark_background_color,
        dark_text_color=published_snapshot_a.dark_text_color,
        dark_border_color=published_snapshot_a.dark_border_color,
        error_color=published_snapshot_a.error_color,
        border_radius_px=published_snapshot_a.border_radius_px,
        font_family=published_snapshot_a.font_family,
    )
    app_db_session.add(unreferenced_snapshot_a)
    app_db_session.flush()

    forged = WidgetPublishedPresentation(
        widget_deployment_id=deployment_b.id,
        organization_id=organization_b.id,
        presentation_snapshot_id=unreferenced_snapshot_a.id,
        published_by_user_id=user_b.id,
        published_at=published_snapshot_a.created_at,
    )
    app_db_session.add(forged)
    with pytest.raises(IntegrityError):
        app_db_session.flush()


def test_publish_audit_contains_internal_ids_only_in_authenticated_audit_log(
    app_db_session: Session,
) -> None:
    _, organization, projection, token = _tenant_projection(app_db_session, suffix="audit")
    client = TestClient(app)
    deployment = _create_deployment(
        client,
        organization=organization,
        projection=projection,
        token=token,
    )
    profile = _create_profile(
        client,
        organization=organization,
        token=token,
    )
    _publish(
        client,
        organization=organization,
        deployment_id=deployment.id,
        profile_id=str(profile["id"]),
        token=token,
    )

    audit = app_db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.event_type == "widget_presentation.published",
            AuditEvent.entity_id == deployment.id,
        )
    )
    assert audit is not None
    assert audit.payload["branding_profile_id"] == str(profile["id"])
    assert audit.payload["profile_revision"] == 1

    public_response = _public_projection(client, deployment.id)
    assert public_response.status_code == 200
    assert str(audit.payload["presentation_snapshot_id"]) not in public_response.text
    assert str(profile["id"]) not in public_response.text
