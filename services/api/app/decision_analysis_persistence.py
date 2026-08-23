"""Persistence and integrity checks for tenant decision-analysis artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculation_orchestration import (
    CalculationOrchestrationError,
    canonicalize_snapshot,
)
from app.decision_analysis_models import DecisionAnalysisArtifact
from app.models import AuditEvent
from app.tenancy import TenantResourceNotFound


class DecisionAnalysisIntegrityError(RuntimeError):
    """Raised when persisted decision-analysis material no longer matches its digests."""


@dataclass(frozen=True)
class DecisionAnalysisReplay:
    """Verified historical artifact independent of current engine execution."""

    artifact_id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    engine_version: str
    input_snapshot: dict[str, object]
    output_snapshot: dict[str, object]
    input_sha256: str
    output_sha256: str
    created_at: datetime


def record_decision_analysis(
    session: Session,
    *,
    organization_id: UUID,
    created_by_user_id: UUID,
    engine_version: str,
    input_snapshot: dict[str, object],
    output_snapshot: dict[str, object],
) -> DecisionAnalysisArtifact:
    """Append one tamper-evident decision-analysis artifact and its audit event."""

    normalized_engine_version = engine_version.strip()
    if not normalized_engine_version:
        raise ValueError("engine_version must not be blank")
    try:
        input_copy, input_digest = canonicalize_snapshot(
            input_snapshot,
            field="decision_analysis_input",
        )
        output_copy, output_digest = canonicalize_snapshot(
            output_snapshot,
            field="decision_analysis_output",
        )
    except CalculationOrchestrationError as exc:
        raise ValueError(str(exc)) from exc

    artifact = DecisionAnalysisArtifact(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        engine_version=normalized_engine_version,
        input_snapshot=input_copy,
        input_sha256=input_digest,
        output_snapshot=output_copy,
        output_sha256=output_digest,
    )
    session.add(artifact)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=created_by_user_id,
            event_type="decision_analysis.recorded",
            entity_type="decision_analysis_artifact",
            entity_id=artifact.id,
            payload={
                "engine_version": normalized_engine_version,
                "input_sha256": input_digest,
                "output_sha256": output_digest,
            },
        )
    )
    session.flush()
    return artifact


def verify_decision_analysis_integrity(artifact: DecisionAnalysisArtifact) -> None:
    """Fail closed when an artifact snapshot or digest has drifted."""

    try:
        _, input_digest = canonicalize_snapshot(
            artifact.input_snapshot,
            field="decision_analysis_input",
        )
        _, output_digest = canonicalize_snapshot(
            artifact.output_snapshot,
            field="decision_analysis_output",
        )
    except CalculationOrchestrationError as exc:
        raise DecisionAnalysisIntegrityError(str(exc)) from exc
    if input_digest != artifact.input_sha256:
        raise DecisionAnalysisIntegrityError("decision analysis input digest mismatch")
    if output_digest != artifact.output_sha256:
        raise DecisionAnalysisIntegrityError("decision analysis output digest mismatch")


def load_decision_analysis(
    session: Session,
    *,
    organization_id: UUID,
    artifact_id: UUID,
) -> DecisionAnalysisReplay:
    """Load one verified tenant artifact without executing the current engine."""

    artifact = session.scalar(
        select(DecisionAnalysisArtifact).where(
            DecisionAnalysisArtifact.id == artifact_id,
            DecisionAnalysisArtifact.organization_id == organization_id,
        )
    )
    if artifact is None:
        raise TenantResourceNotFound("decision analysis artifact not found")
    verify_decision_analysis_integrity(artifact)
    input_copy, _ = canonicalize_snapshot(
        artifact.input_snapshot,
        field="decision_analysis_input",
    )
    output_copy, _ = canonicalize_snapshot(
        artifact.output_snapshot,
        field="decision_analysis_output",
    )
    return DecisionAnalysisReplay(
        artifact_id=artifact.id,
        organization_id=artifact.organization_id,
        created_by_user_id=artifact.created_by_user_id,
        engine_version=artifact.engine_version,
        input_snapshot=input_copy,
        output_snapshot=output_copy,
        input_sha256=artifact.input_sha256,
        output_sha256=artifact.output_sha256,
        created_at=artifact.created_at,
    )
