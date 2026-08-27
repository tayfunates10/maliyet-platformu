"""Deterministic, dependency-free report exports for immutable calculation versions."""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from html import escape as html_escape
from typing import Literal
from xml.sax.saxutils import escape as xml_escape

ReportFormat = Literal["web", "xlsx", "docx", "pdf"]


@dataclass(frozen=True)
class CalculationReportSnapshot:
    calculation_name: str
    calculation_type: str
    version: int
    engine_key: str | None
    engine_version: str
    created_at: datetime
    input_sha256: str | None
    ruleset_sha256: str | None
    output_sha256: str | None
    input_snapshot: dict[str, object]
    ruleset_snapshot: dict[str, object]
    output_snapshot: dict[str, object]


@dataclass(frozen=True)
class ReportArtifact:
    content: bytes
    media_type: str
    extension: str


def _scalar_text(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _flatten(prefix: str, value: object) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        rows: list[tuple[str, str]] = []
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else key
            rows.extend(_flatten(child, value[key]))
        return rows
    if isinstance(value, list):
        rows = []
        for index, item in enumerate(value):
            rows.extend(_flatten(f"{prefix}[{index}]", item))
        return rows
    return [(prefix, _scalar_text(value))]


def report_rows(snapshot: CalculationReportSnapshot) -> list[tuple[str, str]]:
    rows = [
        ("calculation.name", snapshot.calculation_name),
        ("calculation.type", snapshot.calculation_type),
        ("version.number", str(snapshot.version)),
        ("version.engine_key", snapshot.engine_key or ""),
        ("version.engine_version", snapshot.engine_version),
        ("version.created_at", snapshot.created_at.isoformat()),
        ("provenance.input_sha256", snapshot.input_sha256 or ""),
        ("provenance.ruleset_sha256", snapshot.ruleset_sha256 or ""),
        ("provenance.output_sha256", snapshot.output_sha256 or ""),
    ]
    rows.extend(_flatten("input", snapshot.input_snapshot))
    rows.extend(_flatten("rules", snapshot.ruleset_snapshot))
    rows.extend(_flatten("output", snapshot.output_snapshot))
    return rows


def _html(snapshot: CalculationReportSnapshot) -> bytes:
    rows = report_rows(snapshot)
    body = "".join(
        f"<tr><th>{html_escape(key)}</th><td>{html_escape(value)}</td></tr>" for key, value in rows
    )
    document = (
        "<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\">"
        "<title>Maliyet Platformu Raporu</title>"
        "<meta name=\"robots\" content=\"noindex,nofollow\">"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;"
        "padding:.5rem;text-align:left;vertical-align:top}th{width:34%;background:#f5f5f5}"
        "td{overflow-wrap:anywhere}</style></head><body><h1>Maliyet Platformu Raporu</h1>"
        f"<p>{html_escape(snapshot.calculation_name)} · v{snapshot.version}</p>"
        f"<table><tbody>{body}</tbody></table></body></html>"
    )
    return document.encode("utf-8")


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[path].encode("utf-8"))
    return buffer.getvalue()


def _xlsx(snapshot: CalculationReportSnapshot) -> bytes:
    cells: list[str] = []
    for row_index, (key, value) in enumerate(report_rows(snapshot), start=1):
        for column, text in (("A", key), ("B", value)):
            safe = xml_escape(text)
            cells.append(
                f'<c r="{column}{row_index}" t="inlineStr"><is><t xml:space="preserve">'
                f"{safe}</t></is></c>"
            )
    sheet_rows = "".join(
        f'<row r="{row}">{cells[(row - 1) * 2]}{cells[(row - 1) * 2 + 1]}</row>'
        for row in range(1, len(cells) // 2 + 1)
    )
    return _zip_bytes(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>'
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/workbook.xml"/></Relationships>'
            ),
            "xl/workbook.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Rapor" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/></Relationships>'
            ),
            "xl/worksheets/sheet1.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{sheet_rows}</sheetData></worksheet>"
            ),
        }
    )


def _docx(snapshot: CalculationReportSnapshot) -> bytes:
    paragraphs = [
        '<w:p><w:r><w:t>Maliyet Platformu Raporu</w:t></w:r></w:p>',
        f'<w:p><w:r><w:t>{xml_escape(snapshot.calculation_name)} · v{snapshot.version}</w:t></w:r></w:p>',
    ]
    for key, value in report_rows(snapshot):
        paragraphs.append(
            '<w:p><w:r><w:t xml:space="preserve">'
            f"{xml_escape(key)}: {xml_escape(value)}"
            "</w:t></w:r></w:p>"
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(paragraphs)}<w:sectPr/></w:body></w:document>"
    )
    return _zip_bytes(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '</Types>'
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/></Relationships>'
            ),
            "word/document.xml": document,
        }
    )


def _pdf_escape(text: str) -> str:
    ascii_text = text.encode("ascii", "backslashreplace").decode("ascii")
    return ascii_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(snapshot: CalculationReportSnapshot) -> bytes:
    lines = ["Maliyet Platformu Raporu", f"{snapshot.calculation_name} - v{snapshot.version}"]
    lines.extend(f"{key}: {value}" for key, value in report_rows(snapshot))
    commands = ["BT", "/F1 9 Tf", "50 790 Td", "11 TL"]
    for index, line in enumerate(lines[:65]):
        if index:
            commands.append("T*")
        commands.append(f"({_pdf_escape(line[:150])}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def render_report(snapshot: CalculationReportSnapshot, report_format: ReportFormat) -> ReportArtifact:
    renderers = {
        "web": (_html, "text/html; charset=utf-8", "html"),
        "xlsx": (
            _xlsx,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        ),
        "docx": (
            _docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        "pdf": (_pdf, "application/pdf", "pdf"),
    }
    renderer, media_type, extension = renderers[report_format]
    return ReportArtifact(content=renderer(snapshot), media_type=media_type, extension=extension)


def safe_report_filename(name: str, version: int, extension: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-._") or "calculation"
    return f"{slug[:80]}-v{version}.{extension}"
