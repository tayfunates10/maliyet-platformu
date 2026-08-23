"""Deterministic, tenant-private calculation report export primitives."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.models import Calculation, CalculationVersion

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


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


def build_calculation_report_csv(
    calculation: Calculation,
    version: CalculationVersion,
) -> str:
    """Build a stable CSV report from one immutable calculation version.

    The exporter never recalculates results and never converts Decimal strings
    through binary floating point. Structured output values are emitted as
    canonical JSON text. Every cell is quoted and spreadsheet formula prefixes
    are neutralized.
    """

    if version.calculation_id != calculation.id:
        raise ValueError("calculation version does not belong to calculation")
    if version.organization_id != calculation.organization_id:
        raise ValueError("calculation version tenant mismatch")

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(("section", "key", "value"))

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
    for section, key, value in metadata:
        writer.writerow((section, key, _canonical_text(value)))

    for key in sorted(version.output_snapshot):
        writer.writerow(("output", key, _canonical_text(version.output_snapshot[key])))

    return buffer.getvalue()
