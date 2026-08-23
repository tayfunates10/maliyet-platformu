"""Deterministic PDF calculation report export primitives."""

from __future__ import annotations

import json
from typing import Any

from app.models import Calculation, CalculationVersion

_PDF_PAGE_WIDTH = 595
_PDF_PAGE_HEIGHT = 842
_PDF_LEFT_MARGIN = 42
_PDF_RIGHT_MARGIN = 595 - 42
_PDF_LINES_PER_PAGE = 54
_PDF_FONT_SIZE = 9
# Helvetica's widest printable ASCII glyph used here is W at 944/1000 em.
# 65 * 9 * 0.944 = 552.24pt, which fits inside the 553pt text width.
_PDF_LINE_WIDTH = 65


def _pdf_canonical_text(value: Any) -> str:
    """Serialize values exactly, without spreadsheet formula-prefix escaping."""

    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _pdf_report_rows(
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
    rows.extend(
        (section, key, _pdf_canonical_text(value))
        for section, key, value in metadata
    )
    rows.extend(
        ("output", key, _pdf_canonical_text(version.output_snapshot[key]))
        for key in sorted(version.output_snapshot)
    )
    return rows


def _pdf_ascii_text(value: str) -> str:
    """Return a reversible ASCII representation independent of installed fonts."""

    return json.dumps(value, ensure_ascii=True)[1:-1]


def _pdf_report_lines(rows: list[tuple[str, str, str]]) -> list[str]:
    lines = ["Maliyet Platformu Calculation Report", ""]
    for section, key, value in rows:
        text = _pdf_ascii_text(f"{section} | {key} | {value}")
        while len(text) > _PDF_LINE_WIDTH:
            lines.append(text[:_PDF_LINE_WIDTH])
            text = text[_PDF_LINE_WIDTH:]
        lines.append(text)
    return lines


def _pdf_content_stream(lines: list[str]) -> bytes:
    commands = [
        "BT",
        f"/F1 {_PDF_FONT_SIZE} Tf",
        f"{_PDF_LEFT_MARGIN} 800 Td",
        "12 TL",
    ]
    for line in lines:
        commands.append(f"<{line.encode('ascii').hex().upper()}> Tj")
        commands.append("T*")
    commands.append("ET")
    return ("\n".join(commands) + "\n").encode("ascii")


def _pdf_object(object_id: int, payload: bytes) -> bytes:
    return f"{object_id} 0 obj\n".encode() + payload + b"\nendobj\n"


def build_calculation_report_pdf(
    calculation: Calculation,
    version: CalculationVersion,
) -> bytes:
    """Build a deterministic, bounded-width PDF from an immutable version."""

    lines = _pdf_report_lines(_pdf_report_rows(calculation, version))
    pages = [
        lines[index : index + _PDF_LINES_PER_PAGE]
        for index in range(0, len(lines), _PDF_LINES_PER_PAGE)
    ]
    if not pages:
        pages = [["Maliyet Platformu Calculation Report"]]

    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Count {len(page_ids)} /Kids ["
            + " ".join(f"{page_id} 0 R" for page_id in page_ids)
            + "] >>"
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for page_index, page_lines in enumerate(pages):
        page_id = page_ids[page_index]
        content_id = page_id + 1
        content = _pdf_content_stream(page_lines)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PDF_PAGE_WIDTH} "
            f"{_PDF_PAGE_HEIGHT}] /Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"endstream"
        )

    header = b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n"
    body = bytearray(header)
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(body))
        body.extend(_pdf_object(object_id, objects[object_id]))

    xref_offset = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    body.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(body)
