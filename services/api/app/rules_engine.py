"""Fail-closed selection and snapshot helpers for regulatory rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.rules_models import RuleDefinition, RuleSource, RuleVersion


class RuleNotFound(LookupError):
    """Raised when no effective rule exists for the requested date."""


class RuleConfigurationError(RuntimeError):
    """Raised when rule data is ambiguous or internally inconsistent."""


class RulePayloadError(ValueError):
    """Raised when a rule payload cannot be represented deterministically."""


@dataclass(frozen=True)
class ResolvedRule:
    """A deterministic rule resolution including exact source provenance."""

    definition: RuleDefinition
    version: RuleVersion
    source: RuleSource


def validate_rule_payload(value: object, *, path: str = "$") -> None:
    """Reject binary floating point and non-JSON payload values recursively."""

    if isinstance(value, float):
        raise RulePayloadError(f"binary float is forbidden at {path}; use a decimal string")
    if isinstance(value, Decimal):
        raise RulePayloadError(f"Decimal must be serialized as a string at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RulePayloadError(f"rule payload key must be a string at {path}")
            validate_rule_payload(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_rule_payload(item, path=f"{path}[{index}]")
        return
    if value is None or isinstance(value, (str, int, bool)):
        return
    raise RulePayloadError(f"unsupported rule payload value at {path}: {type(value).__name__}")


def rule_payload_sha256(payload: dict[str, object]) -> str:
    """Return a stable hash after enforcing the Decimal-safe JSON contract."""

    validate_rule_payload(payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _intervals_overlap(
    left_start: date,
    left_end: date | None,
    right_start: date,
    right_end: date | None,
) -> bool:
    left_before_right_end = right_end is None or left_start < right_end
    right_before_left_end = left_end is None or right_start < left_end
    return left_before_right_end and right_before_left_end


def create_rule_version(
    session: Session,
    *,
    definition: RuleDefinition,
    source: RuleSource,
    revision: int,
    effective_from: date,
    effective_to: date | None,
    applicability: dict[str, object],
    payload: dict[str, object],
) -> RuleVersion:
    """Create a version only when its interval is valid and non-overlapping."""

    if effective_to is not None and effective_to <= effective_from:
        raise RuleConfigurationError("effective_to must be later than effective_from")
    validate_rule_payload(applicability)
    payload_hash = rule_payload_sha256(payload)

    existing_versions = session.scalars(
        select(RuleVersion).where(RuleVersion.rule_definition_id == definition.id)
    ).all()
    for existing in existing_versions:
        if _intervals_overlap(
            effective_from,
            effective_to,
            existing.effective_from,
            existing.effective_to,
        ):
            raise RuleConfigurationError("rule version effective ranges overlap")

    version = RuleVersion(
        rule_definition_id=definition.id,
        source_id=source.id,
        revision=revision,
        effective_from=effective_from,
        effective_to=effective_to,
        applicability=applicability,
        payload=payload,
        payload_sha256=payload_hash,
    )
    session.add(version)
    return version


def resolve_rule(
    session: Session,
    *,
    code: str,
    at_date: date,
    jurisdiction: str = "TR",
) -> ResolvedRule:
    """Resolve exactly one effective rule; ambiguity fails closed."""

    definition = session.scalar(
        select(RuleDefinition).where(
            RuleDefinition.jurisdiction == jurisdiction,
            RuleDefinition.code == code,
        )
    )
    if definition is None:
        raise RuleNotFound(f"rule not found: {jurisdiction}/{code}")

    candidates = session.scalars(
        select(RuleVersion).where(
            RuleVersion.rule_definition_id == definition.id,
            RuleVersion.effective_from <= at_date,
            or_(RuleVersion.effective_to.is_(None), at_date < RuleVersion.effective_to),
        )
    ).all()
    if not candidates:
        raise RuleNotFound(f"no effective rule for {jurisdiction}/{code} at {at_date.isoformat()}")
    if len(candidates) != 1:
        raise RuleConfigurationError(
            f"ambiguous effective rules for {jurisdiction}/{code} at {at_date.isoformat()}"
        )

    version = candidates[0]
    validate_rule_payload(version.applicability)
    expected_payload_hash = rule_payload_sha256(version.payload)
    if version.payload_sha256 != expected_payload_hash:
        raise RuleConfigurationError("rule payload hash mismatch")

    source = session.get(RuleSource, version.source_id)
    if source is None:
        raise RuleConfigurationError("rule source is missing")

    return ResolvedRule(definition=definition, version=version, source=source)


def build_rule_snapshot(resolved: ResolvedRule) -> dict[str, object]:
    """Build calculation-safe provenance without consulting mutable current rules."""

    definition = resolved.definition
    version = resolved.version
    source = resolved.source
    return {
        "jurisdiction": definition.jurisdiction,
        "code": definition.code,
        "rule_definition_id": str(definition.id),
        "rule_version_id": str(version.id),
        "revision": version.revision,
        "effective_from": version.effective_from.isoformat(),
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "applicability": version.applicability,
        "payload": version.payload,
        "payload_sha256": version.payload_sha256,
        "source": {
            "source_id": str(source.id),
            "authority": source.authority,
            "source_type": source.source_type,
            "title": source.title,
            "canonical_url": source.canonical_url,
            "official_reference": source.official_reference,
            "published_on": source.published_on.isoformat() if source.published_on else None,
            "retrieved_at": source.retrieved_at.isoformat(),
            "content_sha256": source.content_sha256,
        },
    }
