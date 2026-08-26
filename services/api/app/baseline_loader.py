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


def _validated_manifest(path: Path) -> BaselineManifest:
    manifest = read_manifest(path)
    if manifest.dataset != "TR-2026-core-baseline" or manifest.dataset_version != 1:
        raise BaselineIntegrityError("unsupported baseline dataset identity")
    return manifest


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


def _source_metadata_from_spec(spec: SourceSpec) -> tuple[object, ...]:
    return (
        spec.authority,
        spec.source_type,
        spec.title,
        spec.official_reference,
        spec.published_on,
        spec.retrieved_at,
    )


def _source_metadata_from_model(source: RuleSource) -> tuple[object, ...]:
    return (
        source.authority,
        source.source_type,
        source.title,
        source.official_reference,
        source.published_on,
        source.retrieved_at,
    )


def _get_or_create_source(session: Session, spec: SourceSpec) -> RuleSource:
    verify_source_capture(spec)
    existing = session.scalar(
        select(RuleSource).where(
            RuleSource.canonical_url == spec.canonical_url,
            RuleSource.content_sha256 == spec.content_sha256,
        )
    )
    if existing is not None:
        if _source_metadata_from_model(existing) != _source_metadata_from_spec(spec):
            raise BaselineIntegrityError(f"source metadata drift for {spec.key}")
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

    manifest = _validated_manifest(path)
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


def verify_tr_2026_baseline_state(
    session: Session,
    path: Path = DEFAULT_MANIFEST_PATH,
) -> BaselineLoadResult:
    """Read-only verification that persisted rules exactly match the curated baseline."""

    manifest = _validated_manifest(path)
    sources_by_key: dict[str, RuleSource] = {}
    for source_spec in manifest.sources:
        verify_source_capture(source_spec)
        matches = session.scalars(
            select(RuleSource).where(RuleSource.canonical_url == source_spec.canonical_url)
        ).all()
        if len(matches) != 1 or matches[0].content_sha256 != source_spec.content_sha256:
            raise BaselineIntegrityError(f"persisted source drift for {source_spec.key}")
        persisted_source = matches[0]
        if _source_metadata_from_model(persisted_source) != _source_metadata_from_spec(source_spec):
            raise BaselineIntegrityError(f"persisted source metadata drift for {source_spec.key}")
        sources_by_key[source_spec.key] = persisted_source

    definition_count = 0
    version_count = 0
    for rule_spec in manifest.rules:
        definitions = session.scalars(
            select(RuleDefinition).where(
                RuleDefinition.jurisdiction == "TR",
                RuleDefinition.code == rule_spec.code,
            )
        ).all()
        if len(definitions) != 1:
            raise BaselineIntegrityError(f"persisted rule definition missing for {rule_spec.code}")
        definition = definitions[0]
        expected_definition = (rule_spec.category, rule_spec.description, rule_spec.value_kind)
        actual_definition = (definition.category, definition.description, definition.value_kind)
        if actual_definition != expected_definition:
            raise BaselineIntegrityError(f"persisted rule definition drift for {rule_spec.code}")
        definition_count += 1

        persisted_versions = session.scalars(
            select(RuleVersion).where(RuleVersion.rule_definition_id == definition.id)
        ).all()
        expected_revisions = {version_spec.revision for version_spec in rule_spec.versions}
        persisted_revisions = {version.revision for version in persisted_versions}
        revisions_drifted = persisted_revisions != expected_revisions
        duplicate_revisions = len(persisted_versions) != len(expected_revisions)
        if revisions_drifted or duplicate_revisions:
            raise BaselineIntegrityError(
                f"persisted rule revision set drift for {rule_spec.code}"
            )
        versions_by_revision = {version.revision: version for version in persisted_versions}

        for version_spec in rule_spec.versions:
            version_source = sources_by_key.get(version_spec.source_key)
            if version_source is None:
                raise BaselineIntegrityError(
                    f"unknown source key {version_spec.source_key} for {rule_spec.code}"
                )
            version = versions_by_revision[version_spec.revision]
            expected_version = (
                version_source.id,
                version_spec.effective_from,
                version_spec.effective_to,
                version_spec.applicability,
                version_spec.payload,
                rule_payload_sha256(version_spec.payload),
            )
            actual_version = (
                version.source_id,
                version.effective_from,
                version.effective_to,
                version.applicability,
                version.payload,
                version.payload_sha256,
            )
            if actual_version != expected_version:
                raise BaselineIntegrityError(
                    "persisted rule version drift for "
                    f"{rule_spec.code} revision {version_spec.revision}"
                )
            version_count += 1

    return BaselineLoadResult(
        sources=len(sources_by_key),
        definitions=definition_count,
        versions=version_count,
    )
