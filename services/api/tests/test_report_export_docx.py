"""DOCX calculation report determinism, safety, and endpoint tests."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from xml.etree import ElementTree

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import Calculation, Organization, OrganizationMembership, User
from app.report_export import build_calculation_report_docx


def _simple_report_source() -> tuple[SimpleNamespace, SimpleNamespace]:
    calculation = SimpleNamespace(
        id="calc-docx",
        organization_id="org-docx",
        name="=SUM(A1:A2)-Türkçe-\x01",
        calculation_type="trade",
    )
    version = SimpleNamespace(
        calculation_id="calc-docx",
        organization_id="org-docx",
        version=2,
        engine_key="trade",
        engine_version="1.0.0",
        input_sha256="a" * 64,
        ruleset_sha256="b" * 64,
        output_sha256="c" * 64,
        created_at=datetime(2026, 8, 23, tzinfo=UTC),
        output_snapshot={"decimal": "123.4500", "literal": "_x0001_"},
    )
    return calculation, version


def test_docx_export_is_deterministic_unicode_and_xml_safe() -> None:
    calculation, version = _simple_report_source()

    first = build_calculation_report_docx(calculation, version)
    second = build_calculation_report_docx(calculation, version)

    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert archive.namelist() == [
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
        ]
        document = archive.read("word/document.xml")

    root = ElementTree.fromstring(document)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    text_values = [node.text or "" for node in root.findall(".//w:t", namespace)]
    assert "'=SUM(A1:A2)-Türkçe-_x0001_" in text_values
    assert "123.4500" in text_values
    assert "_x005F_x0001_" in text_values


def _tenant(
    session: Session,
    *,
    suffix: str,
) -> tuple[User, Organization, str]:
    user = User(email=f"docx-{suffix}@example.test", display_name=f"DOCX {suffix}")
    organization = Organization(slug=f"docx-{suffix}", legal_name=f"DOCX {suffix} Org")
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
    user = User(email=f"docx-{suffix}@example.test", display_name=f"DOCX {suffix}")
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


def test_authorized_viewer_can_download_docx(app_db_session: Session) -> None:
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
        name="DOCX report",
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
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.docx",
        headers=_headers(viewer_token),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].endswith('v1.docx"')
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "word/document.xml" in archive.namelist()
