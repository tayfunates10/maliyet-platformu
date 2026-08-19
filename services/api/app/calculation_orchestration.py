"""Tenant-safe persistence orchestration for reproducible calculation versions.

This layer records already-validated engine inputs/outputs together with engine
identity and rule provenance. It never executes arbitrary engines from JSON and
never re-resolves current rules when loading historical replay material.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Calculation,
    CalculationVersion,
    OrganizationMembership,
)
from app.tenancy import TenantResourceNotFound


class CalculationOrchestrationError(ValueError):
    """Raised when a calculation version cannot be recorded safely."""


class CalculationIntegrityError(RuntimeError):
    """Raised when persisted replay material no longer matches its digests."""


@dataclass(frozen=True)
class ReplayMaterial:
    """Verified historical execution material independent of current rules."""

    calculation_id: UUID
    version_id: UUID
    version: int
    engine_key: str
    engine_version: str
    input_snapshot: dict[str, object]
    ruleset_snapshot: dict[str, object]
    output_snapshot: dict[str, object]
    input_sha256: str
    ruleset_sha256: str
    output_sha256: str


def _require_non_blank(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise CalculationOrchestrationError(f"{field} must not be blank")
    return normalized


def _validate_snapshot_value(value: object, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise CalculationOrchestrationError(f"{path} must not contain binary float")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_snapshot_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CalculationOrchestrationError(f"{path} keys must be strings")
            _validate_snapshot_value(item, path=f"{path}.{key}")
        return
    raise CalculationOrchestrationError(
        f"{path} contains unsupported snapshot value type: {type(value).__name__}"
    )


def canonicalize_snapshot(
    snapshot: dict[str, object],
    *,
    field: str,
) -> tuple[dict[str, object], str]:
    """Validate, deep-copy, and digest one JSON-compatible snapshot."""

    _validate_snapshot_value(snapshot, path=field)
    canonical_json = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    copied = cast(dict[str, object], json.loads(canonical_json))
    return copied, digest


def _require_membership(
    session: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
) -> None:
    membership = session.scalar(
        select(OrganizationMembership.id).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise TenantResourceNotFound("organization membership not found")


def record_calculation_version(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
    created_by_user_id: UUID,
    engine_key: str,
    engine_version: str,
    input_snapshot: dict[str, object],
    ruleset_snapshot: dict[str, object],
    output_snapshot: dict[str, object],
) -> CalculationVersion:
    """Atomically append one tamper-evident version to a tenant calculation."""

    normalized_engine_key = _require_non_blank(engine_key, field="engine_key")
    normalized_engine_version = _require_non_blank(engine_version, field="engine_version")
    input_copy, input_digest = canonicalize_snapshot(input_snapshot, field="input_snapshot")
    ruleset_copy, ruleset_digest = canonicalize_snapshot(
        ruleset_snapshot,
        field="ruleset_snapshot",
    )
    output_copy, output_digest = canonicalize_snapshot(output_snapshot, field="output_snapshot")

    calculation = session.scalar(
        select(Calculation)
        .where(
            Calculation.id == calculation_id,
            Calculation.organization_id == organization_id,
        )
        .with_for_update()
    )
    if calculation is None:
        raise TenantResourceNotFound("calculation not found")
    if calculation.calculation_type != normalized_engine_key:
        raise CalculationOrchestrationError(
            "engine_key must match the calculation calculation_type"
        )

    _require_membership(
        session,
        organization_id=organization_id,
        user_id=created_by_user_id,
    )

    latest_version = session.scalar(
        select(func.max(CalculationVersion.version)).where(
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.calculation_id == calculation_id,
        )
    )
    next_version = (latest_version or 0) + 1

    with session.begin_nested():
        version = CalculationVersion(
            organization_id=organization_id,
            calculation_id=calculation_id,
            created_by_user_id=created_by_user_id,
            version=next_version,
            engine_key=normalized_engine_key,
            engine_version=normalized_engine_version,
            input_snapshot=input_copy,
            input_sha256=input_digest,
            ruleset_snapshot=ruleset_copy,
            ruleset_sha256=ruleset_digest,
            output_snapshot=output_copy,
            output_sha256=output_digest,
        )
        session.add(version)
        session.flush()

        session.add(
            AuditEvent(
                organization_id=organization_id,
                actor_user_id=created_by_user_id,
                event_type="calculation.version_recorded",
                entity_type="calculation_version",
                entity_id=version.id,
                payload={
                    "calculation_id": str(calculation_id),
                    "version": next_version,
                    "engine_key": normalized_engine_key,
                    "engine_version": normalized_engine_version,
                    "input_sha256": input_digest,
                    "ruleset_sha256": ruleset_digest,
                    "output_sha256": output_digest,
                },
            )
        )
        session.flush()

    return version


def verify_calculation_version_integrity(version: CalculationVersion) -> None:
    """Fail closed when replay metadata is missing or snapshot bytes have drifted."""

    if version.engine_key is None:
        raise CalculationIntegrityError("calculation version is missing engine_key")
    _require_non_blank(version.engine_key, field="engine_key")
    _require_non_blank(version.engine_version, field="engine_version")

    expected = (
        ("input", version.input_snapshot, version.input_sha256),
        ("ruleset", version.ruleset_snapshot, version.ruleset_sha256),
        ("output", version.output_snapshot, version.output_sha256),
    )
    for label, snapshot, stored_digest in expected:
        if stored_digest is None:
            raise CalculationIntegrityError(f"calculation version is missing {label} digest")
        try:
            _, computed_digest = canonicalize_snapshot(snapshot, field=f"{label}_snapshot")
        except CalculationOrchestrationError as exc:
            raise CalculationIntegrityError(str(exc)) from exc
        if computed_digest != stored_digest:
            raise CalculationIntegrityError(f"{label} snapshot digest mismatch")


def load_replay_material(
    session: Session,
    *,
    organization_id: UUID,
    calculation_id: UUID,
    version_number: int,
) -> ReplayMaterial:
    """Load verified historical material without consulting current rule state."""

    if version_number <= 0:
        raise CalculationOrchestrationError("version_number must be positive")
    version = session.scalar(
        select(CalculationVersion).where(
            CalculationVersion.organization_id == organization_id,
            CalculationVersion.calculation_id == calculation_id,
            CalculationVersion.version == version_number,
        )
    )
    if version is None:
        raise TenantResourceNotFound("calculation version not found")

    verify_calculation_version_integrity(version)
    if (
        version.engine_key is None
        or version.input_sha256 is None
        or version.ruleset_sha256 is None
        or version.output_sha256 is None
    ):
        raise CalculationIntegrityError("calculation replay provenance is incomplete")

    input_copy, _ = canonicalize_snapshot(version.input_snapshot, field="input_snapshot")
    ruleset_copy, _ = canonicalize_snapshot(version.ruleset_snapshot, field="ruleset_snapshot")
    output_copy, _ = canonicalize_snapshot(version.output_snapshot, field="output_snapshot")

    return ReplayMaterial(
        calculation_id=version.calculation_id,
        version_id=version.id,
        version=version.version,
        engine_key=version.engine_key,
        engine_version=version.engine_version,
        input_snapshot=input_copy,
        ruleset_snapshot=ruleset_copy,
        output_snapshot=output_copy,
        input_sha256=version.input_sha256,
        ruleset_sha256=version.ruleset_sha256,
        output_sha256=version.output_sha256,
    )
