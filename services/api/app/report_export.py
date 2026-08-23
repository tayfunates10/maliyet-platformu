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
_OOXML_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


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


def _is_xml_10_character(codepoint: int) -> bool:
    return (
        codepoint in {0x09, 0x0A, 0x0D}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _ooxml_escape_text(value: str) -> str:
    """Encode XML-forbidden characters using OOXML escaped-string syntax."""

    encoded: list[str] = []
    index = 0
    while index < len(value):
        candidate = value[index : index + 7]
        if (
            len(candidate) == 7
            and candidate[0:2].lower() == "_x"
            and candidate[6] == "_"
            and all(character in "0123456789abcdefABCDEF" for character in candidate[2:6])
        ):
            encoded.append("_x005F_")
            encoded.append(candidate[1:])
            index += 7
            continue

        character = value[index]
        codepoint = ord(character)
        if _is_xml_10_character(codepoint):
            encoded.append(character)
        else:
            encoded.append(f"_x{codepoint:04X}_")
        index += 1
    return "".join(encoded)


def _ooxml_text(value: str) -> str:
    escaped = escape(_ooxml_escape_text(value), {'"': "&quot;"})
    preserve = ' xml:space="preserve"' if value != value.strip() else ""
    return f"<w:t{preserve}>{escaped}</w:t>"


def _xlsx_cell(column: str, row_number: int, value: str) -> str:
    """Render one inline-string XLSX cell with no formula execution surface."""

    escaped = escape(_ooxml_escape_text(value), {'"': "&quot;"})
    preserve = ' xml:space="preserve"' if value != value.strip() else ""
    return f'<c r="{column}{row_number}" t="inlineStr"><is><t{preserve}>{escaped}</t></is></c>'


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
        "<sheetData>" + "".join(row_xml) + "</sheetData></worksheet>"
    )
    return document.encode("utf-8")


def _write_ooxml_member(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, _OOXML_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, content)


def build_calculation_report_xlsx(
    calculation: Calculation,
    version: CalculationVersion,
) -> bytes:
    """Build a deterministic XLSX report without recalculation or float coercion."""

    rows = _report_rows(calculation, version)
    files = {
        "[Content_Types].xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            b'content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.'
            b'openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
            b'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            b'<Override PartName="/xl/worksheets/sheet1.xml" '
            b'ContentType="application/vnd.openxmlformats-officedocument.'
            b'spreadsheetml.worksheet+xml"/>'
            b"</Types>"
        ),
        "_rels/.rels": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            b'2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/officeDocument" '
            b'Target="xl/workbook.xml"/>'
            b"</Relationships>"
        ),
        "xl/workbook.xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
            b'2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships">'
            b'<sheets><sheet name="Calculation" sheetId="1" r:id="rId1"/>'
            b"</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            b'2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/worksheet" '
            b'Target="worksheets/sheet1.xml"/>'
            b"</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": _xlsx_sheet(rows),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for path in sorted(files):
            _write_ooxml_member(archive, path, files[path])
    return buffer.getvalue()


def _docx_document(rows: list[tuple[str, str, str]]) -> bytes:
    row_xml = []
    for row in rows:
        cells = "".join(f"<w:tc><w:p><w:r>{_ooxml_text(value)}</w:r></w:p></w:tc>" for value in row)
        row_xml.append(f"<w:tr>{cells}</w:tr>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:tbl>" + "".join(row_xml) + "</w:tbl></w:body></w:document>"
    )
    return document.encode("utf-8")


def build_calculation_report_docx(
    calculation: Calculation,
    version: CalculationVersion,
) -> bytes:
    """Build a deterministic DOCX report from an immutable calculation version."""

    rows = _report_rows(calculation, version)
    files = {
        "[Content_Types].xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            b'content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.'
            b'openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/word/document.xml" ContentType="application/vnd.'
            b'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b"</Types>"
        ),
        "_rels/.rels": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            b'2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/officeDocument" '
            b'Target="word/document.xml"/>'
            b"</Relationships>"
        ),
        "word/document.xml": _docx_document(rows),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for path in sorted(files):
            _write_ooxml_member(archive, path, files[path])
    return buffer.getvalue()
