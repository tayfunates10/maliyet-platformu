"""Validated loader for curated, source-backed regulatory baseline datasets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.rules_engine import create_rule_version, rule_payload_sha256, validate_rule_payload
from app.rules_models import RuleDefinition, RuleSource, RuleVersion


def _discover_repo_root() -> Path:
    """Locate the immutable regulatory dataset in source checkouts and production images."""

    module_path = Path(__file__).resolve()
    for candidate in module_path.parents:
        if (candidate / "data/tr/2026/baseline.json").is_file():
            return candidate
    raise RuntimeError("TR-2026 regulatory baseline is not packaged with the application")


REPO_ROOT = _discover_repo_root()
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data/tr/2026/baseline.json"


class BaselineIntegrityError(RuntimeError):
    """Raised when curated evidence or persisted baseline data does not match."""


class SourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    authority: str
    source_type: str
    title: str
    canonical_url: str
    official_reference: str | None
    published_on: date | None
    retrieved_at: datetime
    capture_kind: Literal["normalized_evidence"]
    capture_path: str
    content_sha256: str


class VersionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str
    revision: int
    effective_from: date
    effective_to: date | None
    applicability: dict[str, object]
    payload: dict[str, object]


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    category: str
    description: str
    value_kind: str
    versions: list[VersionSpec]


class BaselineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    dataset_version: int
    reviewed_on: date
    sources: list[SourceSpec]
    rules: list[RuleSpec]


@dataclass(frozen=True)
class BaselineLoadResult:
    sources: int
    definitions: int
    versions: int


def read_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> BaselineManifest:
    """Parse a baseline manifest using a fail-closed schema."""

    return BaselineManifest.model_validate_json(path.read_text(encoding="utf-8"))


def verify_source_capture(spec: SourceSpec) -> Path:
    """Verify the exact curated evidence capture declared by a source entry."""

    capture_path = (REPO_ROOT / spec.capture_path).resolve()
    try:
        capture_path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise BaselineIntegrityError("source capture escapes repository root") from exc
    if not capture_path.is_file():
        raise BaselineIntegrityError(f"source capture is missing: {spec.capture_path}")
    actual_hash = hashlib.sha256(capture_path.read_bytes()).hexdigest()
    if actual_hash != spec.content_sha256:
        raise BaselineIntegrityError(f"source capture hash mismatch for {spec.key}: {actual_hash}")
    return capture_path


def _get_or_create_source(session: Session, spec: SourceSpec) -> RuleSource:
    verify_source_capture(spec)
    existing = session.scalar(
        select(RuleSource).where(
            RuleSource.canonical_url == spec.canonical_url,
            RuleSource.content_sha256 == spec.content_sha256,
        )
    )
    if existing is not None:
        return existing
    source = RuleSource(
        authority=spec.authority,
        source_type=spec.source_type,
        title=spec.title,
        canonical_url=spec.canonical_url,
        official_reference=spec.official_reference,
        published_on=spec.published_on,
        retrieved_at=spec.retrieved_at,
        content_sha256=spec.content_sha256,
    )
    session.add(source)
    session.flush()
    return source


def _get_or_create_definition(session: Session, spec: RuleSpec) -> RuleDefinition:
    existing = session.scalar(
        select(RuleDefinition).where(
            RuleDefinition.jurisdiction == "TR",
            RuleDefinition.code == spec.code,
        )
    )
    if existing is not None:
        expected = (spec.category, spec.description, spec.value_kind)
        actual = (existing.category, existing.description, existing.value_kind)
        if actual != expected:
            raise BaselineIntegrityError(f"rule definition drift for {spec.code}")
        return existing
    definition = RuleDefinition(
        jurisdiction="TR",
        code=spec.code,
        category=spec.category,
        description=spec.description,
        value_kind=spec.value_kind,
    )
    session.add(definition)
    session.flush()
    return definition


def _ensure_version(
    session: Session,
    *,
    definition: RuleDefinition,
    source: RuleSource,
    spec: VersionSpec,
) -> RuleVersion:
    validate_rule_payload(spec.applicability)
    payload_hash = rule_payload_sha256(spec.payload)
    existing = session.scalar(
        select(RuleVersion).where(
            RuleVersion.rule_definition_id == definition.id,
            RuleVersion.revision == spec.revision,
        )
    )
    if existing is not None:
        expected = (
            source.id,
            spec.effective_from,
            spec.effective_to,
            spec.applicability,
            spec.payload,
            payload_hash,
        )
        actual = (
            existing.source_id,
            existing.effective_from,
            existing.effective_to,
            existing.applicability,
            existing.payload,
            existing.payload_sha256,
        )
        if actual != expected:
            raise BaselineIntegrityError(
                f"rule version drift for {definition.code} revision {spec.revision}"
            )
        return existing
    version = create_rule_version(
        session,
        definition=definition,
        source=source,
        revision=spec.revision,
        effective_from=spec.effective_from,
        effective_to=spec.effective_to,
        applicability=spec.applicability,
        payload=spec.payload,
    )
    session.flush()
    return version


def load_tr_2026_baseline(
    session: Session,
    path: Path = DEFAULT_MANIFEST_PATH,
) -> BaselineLoadResult:
    """Load the reviewed baseline idempotently; any drift fails closed."""

    manifest = read_manifest(path)
    if manifest.dataset != "TR-2026-core-baseline" or manifest.dataset_version != 1:
        raise BaselineIntegrityError("unsupported baseline dataset identity")

    sources_by_key: dict[str, RuleSource] = {}
    for source_spec in manifest.sources:
        if source_spec.key in sources_by_key:
            raise BaselineIntegrityError(f"duplicate source key: {source_spec.key}")
        sources_by_key[source_spec.key] = _get_or_create_source(session, source_spec)

    definition_count = 0
    version_count = 0
    for rule_spec in manifest.rules:
        definition = _get_or_create_definition(session, rule_spec)
        definition_count += 1
        for version_spec in rule_spec.versions:
            source = sources_by_key.get(version_spec.source_key)
            if source is None:
                raise BaselineIntegrityError(
                    f"unknown source key {version_spec.source_key} for {rule_spec.code}"
                )
            _ensure_version(
                session,
                definition=definition,
                source=source,
                spec=version_spec,
            )
            version_count += 1

    return BaselineLoadResult(
        sources=len(sources_by_key),
        definitions=definition_count,
        versions=version_count,
    )
