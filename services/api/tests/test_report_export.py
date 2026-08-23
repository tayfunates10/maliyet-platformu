"""Calculation report export security and determinism tests."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from xml.etree import ElementTree

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_context import issue_session
from app.main import app
from app.models import Calculation, CalculationVersion, Organization, OrganizationMembership, User
from app.report_export import build_calculation_report_csv, build_calculation_report_xlsx


def _tenant(
    session: Session,
    *,
    suffix: str,
    role: str = "owner",
) -> tuple[User, Organization, str]:
    user = User(email=f"report-{suffix}@example.test", display_name=f"Report {suffix}")
    organization = Organization(slug=f"report-{suffix}", legal_name=f"Report {suffix} Org")
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
) -> str:
    user = User(email=f"report-{suffix}@example.test", display_name=f"Report {suffix}")
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


def _execute_trade(
    session: Session,
    *,
    suffix: str,
) -> tuple[Organization, Calculation, str]:
    owner, organization, owner_token = _tenant(session, suffix=suffix)
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="Trade report",
        calculation_type="trade",
    )
    session.add(calculation)
    session.flush()
    response = TestClient(app).post(
        f"/organizations/{organization.id}/calculations/{calculation.id}/execute/trade",
        json=_trade_payload(),
        headers=_headers(owner_token),
    )
    assert response.status_code == 201
    return organization, calculation, owner_token


def _simple_report_source() -> tuple[SimpleNamespace, SimpleNamespace]:
    calculation = SimpleNamespace(
        id="calc-1",
        organization_id="org-1",
        name="=SUM(A1:A2)",
        calculation_type="trade",
    )
    version = SimpleNamespace(
        calculation_id="calc-1",
        organization_id="org-1",
        version=3,
        engine_key="trade",
        engine_version="1.0.0",
        input_sha256="a" * 64,
        ruleset_sha256="b" * 64,
        output_sha256="c" * 64,
        created_at=datetime(2026, 8, 23, 0, 0, tzinfo=UTC),
        output_snapshot={
            "z_decimal": "123.4500",
            "a_formula": "@SUM(1,2)",
            "nested": {"z": "2", "a": "1"},
        },
    )
    return calculation, version


def test_csv_export_is_deterministic_decimal_safe_and_formula_safe() -> None:
    calculation, version = _simple_report_source()

    report = build_calculation_report_csv(calculation, version)
    rows = list(csv.reader(io.StringIO(report)))

    assert rows[0] == ["section", "key", "value"]
    assert [row[1] for row in rows if row[0] == "output"] == [
        "a_formula",
        "nested",
        "z_decimal",
    ]
    values = {(row[0], row[1]): row[2] for row in rows[1:]}
    assert values[("calculation", "name")] == "'=SUM(A1:A2)"
    assert values[("output", "a_formula")] == "'@SUM(1,2)"
    assert values[("output", "z_decimal")] == "123.4500"
    assert values[("output", "nested")] == '{"a":"1","z":"2"}'


def test_xlsx_export_is_deterministic_decimal_safe_and_formula_safe() -> None:
    calculation, version = _simple_report_source()

    first = build_calculation_report_xlsx(calculation, version)
    second = build_calculation_report_xlsx(calculation, version)

    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        sheet = archive.read("xl/worksheets/sheet1.xml")

    root = ElementTree.fromstring(sheet)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cells = root.findall(".//x:c", namespace)
    assert cells
    assert all(cell.attrib.get("t") == "inlineStr" for cell in cells)
    assert root.find(".//x:f", namespace) is None
    text_values = [
        node.text or ""
        for node in root.findall(".//x:t", namespace)
    ]
    assert "'=SUM(A1:A2)" in text_values
    assert "'@SUM(1,2)" in text_values
    assert "123.4500" in text_values
    assert '{"a":"1","z":"2"}' in text_values


def test_authorized_member_can_download_immutable_version_csv(app_db_session: Session) -> None:
    owner, organization, owner_token = _tenant(app_db_session, suffix="download")
    viewer_token = _add_member(
        app_db_session,
        organization=organization,
        suffix="viewer",
        role="viewer",
    )
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="Trade report",
        calculation_type="trade",
    )
    app_db_session.add(calculation)
    app_db_session.flush()

    execute = TestClient(app).post(
        f"/organizations/{organization.id}/calculations/{calculation.id}/execute/trade",
        json=_trade_payload(),
        headers=_headers(owner_token),
    )
    assert execute.status_code == 201

    response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.csv",
        headers=_headers(viewer_token),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].endswith('v1.csv"')
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    assert '"provenance","output_sha256"' in text
    assert '"calculation","name","Trade report"' in text
    assert '"output","contribution_profit"' in text


def test_authorized_member_can_download_immutable_version_xlsx(app_db_session: Session) -> None:
    owner, organization, owner_token = _tenant(app_db_session, suffix="xlsx-download")
    viewer_token = _add_member(
        app_db_session,
        organization=organization,
        suffix="xlsx-viewer",
        role="viewer",
    )
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="Trade XLSX report",
        calculation_type="trade",
    )
    app_db_session.add(calculation)
    app_db_session.flush()
    execute = TestClient(app).post(
        f"/organizations/{organization.id}/calculations/{calculation.id}/execute/trade",
        json=_trade_payload(),
        headers=_headers(owner_token),
    )
    assert execute.status_code == 201

    response = TestClient(app).get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.xlsx",
        headers=_headers(viewer_token),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].endswith('v1.xlsx"')
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "xl/worksheets/sheet1.xml" in archive.namelist()


def test_report_export_rejects_tampered_version(app_db_session: Session) -> None:
    organization, calculation, owner_token = _execute_trade(
        app_db_session,
        suffix="tampered",
    )
    version = (
        app_db_session.query(CalculationVersion)
        .filter_by(
            organization_id=organization.id,
            calculation_id=calculation.id,
            version=1,
        )
        .one()
    )
    version.output_snapshot = {**version.output_snapshot, "contribution_profit": "999999.00"}
    app_db_session.flush()

    client = TestClient(app)
    csv_response = client.get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.csv",
        headers=_headers(owner_token),
    )
    xlsx_response = client.get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.xlsx",
        headers=_headers(owner_token),
    )

    expected = {"detail": "calculation version integrity verification failed"}
    assert csv_response.status_code == 409
    assert csv_response.json() == expected
    assert xlsx_response.status_code == 409
    assert xlsx_response.json() == expected


def test_cross_tenant_report_export_fails_closed(app_db_session: Session) -> None:
    owner, organization, owner_token = _tenant(app_db_session, suffix="private")
    _, other_organization, other_token = _tenant(app_db_session, suffix="outsider")
    calculation = Calculation(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="Private report",
        calculation_type="trade",
    )
    app_db_session.add(calculation)
    app_db_session.flush()
    execute = TestClient(app).post(
        f"/organizations/{organization.id}/calculations/{calculation.id}/execute/trade",
        json=_trade_payload(),
        headers=_headers(owner_token),
    )
    assert execute.status_code == 201

    client = TestClient(app)
    csv_response = client.get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.csv",
        headers=_headers(other_token),
    )
    xlsx_response = client.get(
        f"/organizations/{organization.id}/calculations/{calculation.id}/versions/1/report.xlsx",
        headers=_headers(other_token),
    )

    assert other_organization.id != organization.id
    assert csv_response.status_code == 403
    assert xlsx_response.status_code == 403
