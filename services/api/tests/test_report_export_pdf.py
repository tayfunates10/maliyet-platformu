"""PDF calculation report determinism, safety, and endpoint tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import Calculation, Organization, OrganizationMembership, User
from app.report_export import build_calculation_report_pdf


def _simple_report_source() -> tuple[SimpleNamespace, SimpleNamespace]:
    calculation = SimpleNamespace(
        id="calc-pdf",
        organization_id="org-pdf",
        name="Türkçe rapor",
        calculation_type="trade",
    )
    version = SimpleNamespace(
        calculation_id="calc-pdf",
        organization_id="org-pdf",
        version=3,
        engine_key="trade",
        engine_version="1.0.0",
        input_sha256="a" * 64,
        ruleset_sha256="b" * 64,
        output_sha256="c" * 64,
        created_at=datetime(2026, 8, 23, tzinfo=UTC),
        output_snapshot={"decimal": "123.4500", "unicode": "şğİı"},
    )
    return calculation, version


def test_pdf_export_is_deterministic_and_preserves_canonical_text() -> None:
    calculation, version = _simple_report_source()

    first = build_calculation_report_pdf(calculation, version)
    second = build_calculation_report_pdf(calculation, version)

    assert first == second
    assert first.startswith(b"%PDF-1.4")
    assert first.endswith(b"%%EOF\n")
    assert b"xref\n" in first
    assert b"/BaseFont /Helvetica" in first

    decimal_hex = "123.4500".encode("ascii").hex().upper().encode("ascii")
    unicode_ascii = "\\u015f\\u011f\\u0130\\u0131".encode("ascii")
    unicode_hex = unicode_ascii.hex().upper().encode("ascii")
    assert decimal_hex in first
    assert unicode_hex in first


def _tenant(
    session: Session,
    *,
    suffix: str,
) -> tuple[User, Organization, str]:
    user = User(email=f"pdf-{suffix}@example.test", display_name=f"PDF {suffix}")
    organization = Organization(slug=f"pdf-{suffix}", legal_name=f"PDF {suffix} Org")
    session.add_all([user, organization])
    session.flush()
    session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
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
) -> str:
    user = User(email=f"pdf-{suffix}@example.test", display_name=f"PDF {suffix}")
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
    return raw_token


def _headers(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


def test_authorized_viewer_can_download_pdf(app_db_session: Session) -> None:
    owner, organization, owner_token = _tenant(app_db_session, suffix="owner")
    viewer_token = _add_member(
        app_db_session,
        organization=organization,
        suffix="viewer",
        role="viewer",
    )

    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="PDF report",
        calculation_type="trade",
    )
    app_db_session.add(calculation)
    app_db_session.flush()
    execute = TestClient(app).post(
        f"/organizations/{organization.id}/calculations/{calculation.id}/execute/trade",
        json={
            "sales": [
                {
                    "key": "sale",
                    "quantity": "2",
                    "unit_sale_price": "100.00",
                    "unit_acquisition_cost": "40.00",
                }
            ]
        },
        headers=_headers(owner_token),
    )
    assert execute.status_code == 201

    response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.pdf",
        headers=_headers(viewer_token),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].endswith('v1.pdf"')
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF-1.4")
