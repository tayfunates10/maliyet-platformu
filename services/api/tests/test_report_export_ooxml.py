"""OOXML escaped-string regression tests for calculation XLSX export."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from xml.etree import ElementTree

from app.report_export import build_calculation_report_xlsx


def test_xlsx_export_encodes_xml_forbidden_and_literal_escape_sequences() -> None:
    calculation = SimpleNamespace(
        id="calc-xml",
        organization_id="org-xml",
        name="control-\x01-literal-_x0001_",
        calculation_type="trade",
    )
    version = SimpleNamespace(
        calculation_id="calc-xml",
        organization_id="org-xml",
        version=1,
        engine_key="trade",
        engine_version="1.0.0",
        input_sha256="a" * 64,
        ruleset_sha256="b" * 64,
        output_sha256="c" * 64,
        created_at=datetime(2026, 8, 23, tzinfo=UTC),
        output_snapshot={"control": "value-\x0b-end"},
    )

    report = build_calculation_report_xlsx(calculation, version)
    with zipfile.ZipFile(io.BytesIO(report)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml")

    root = ElementTree.fromstring(sheet)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values = [node.text or "" for node in root.findall(".//x:t", namespace)]

    assert "control-_x0001_-literal-_x005F_x0001_" in values
    assert "value-_x000B_-end" in values
