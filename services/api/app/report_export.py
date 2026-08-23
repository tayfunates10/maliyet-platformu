"""Deterministic, tenant-private calculation report export primitives."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from typing import Any
from xml.sax.saxutils import escape

from app.models import Calculation, CalculationVersion

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_XLSX_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _canonical_text(value: Any) -> str:
    """Serialize report values without numeric coercion or hidden rounding."""

    if isinstance(value, str):
        text = value
    elif value is None:
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = str(value)
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _report_rows(
    calculation: Calculation,
    version: CalculationVersion,
) -> list[tuple[str, str, str]]:
    if version.calculation_id != calculation.id:
        raise ValueError("calculation version does not belong to calculation")
    if version.organization_id != calculation.organization_id:
        raise ValueError("calculation version tenant mismatch")

    rows: list[tuple[str, str, str]] = [("section", "key", "value")]
    metadata = (
        ("calculation", "name", calculation.name),
        ("calculation", "calculation_type", calculation.calculation_type),
        ("version", "version", version.version),
        ("version", "engine_key", version.engine_key),
        ("version", "engine_version", version.engine_version),
        ("provenance", "input_sha256", version.input_sha256),
        ("provenance", "ruleset_sha256", version.ruleset_sha256),
        ("provenance", "output_sha256", version.output_sha256),
        ("provenance", "created_at", version.created_at.isoformat()),
    )
    rows.extend((section, key, _canonical_text(value)) for section, key, value in metadata)
    rows.extend(
        ("output", key, _canonical_text(version.output_snapshot[key]))
        for key in sorted(version.output_snapshot)
    )
    return rows


def build_calculation_report_csv(
    calculation: Calculation,
    version: CalculationVersion,
) -> str:
    """Build a stable CSV report from one immutable calculation version."""

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerows(_report_rows(calculation, version))
    return buffer.getvalue()


def _xlsx_cell(column: str, row_number: int, value: str) -> str:
    """Render one inline-string XLSX cell with no formula execution surface."""

    escaped = escape(value, {'"': "&quot;"})
    preserve = ' xml:space="preserve"' if value != value.strip() else ""
    return (
        f'<c r="{column}{row_number}" t="inlineStr">'
        f"<is><t{preserve}>{escaped}</t></is></c>"
    )


def _xlsx_sheet(rows: list[tuple[str, str, str]]) -> bytes:
    row_xml: list[str] = []
    for index, row in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell(column, index, value)
            for column, value in zip(("A", "B", "C"), row, strict=True)
        )
        row_xml.append(f'<row r="{index}">{cells}</row>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
        + "".join(row_xml)
        + '</sheetData></worksheet>'
    )
    return document.encode("utf-8")


def _write_xlsx_member(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, _XLSX_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, content)


def build_calculation_report_xlsx(
    calculation: Calculation,
    version: CalculationVersion,
) -> bytes:
    """Build a deterministic XLSX report without recalculation or float coercion.

    Every worksheet value is emitted as an OOXML inline string. Decimal strings
    therefore retain their exact representation and formula-looking inputs can
    never become executable spreadsheet formulas.
    """

    rows = _report_rows(calculation, version)
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>'
        ).encode("utf-8"),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ).encode("utf-8"),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Calculation" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        ).encode("utf-8"),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'
        ).encode("utf-8"),
        "xl/worksheets/sheet1.xml": _xlsx_sheet(rows),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for path in sorted(files):
            _write_xlsx_member(archive, path, files[path])
    return buffer.getvalue()
