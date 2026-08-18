"""Canonical report_v1 assembly from persisted evaluation rows (Phase 19).

Reads only what earlier phases persisted — final_scores, probe_results,
osd_agent_outputs, human_reviews — and reuses the EvaluationService getters so
the report carries exactly the same disclosure/score shapes as detail reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.models import Evaluation
from app.db.repositories.final_score import FinalScoreRepository
from app.db.repositories.probe_result import ProbeResultRepository
from app.schemas.reports import (
    ExecutiveSummary,
    ReportEvaluation,
    ReportProbe,
    ReportScore,
    ReportV1,
)
from app.services.evaluation_service import EvaluationService

MODE_LABELS = {
    EvaluationMode.AI_ASSISTED: "AI-ASSISTED",
    EvaluationMode.AI_AUTONOMOUS: "AI-AUTONOMOUS",
}

_MAX_FLAG_BULLET_ITEMS = 8


def build_executive_summary(
    *,
    mode: EvaluationMode,
    human_reviewed: bool,
    fries_score: float,
    dimension_scores: dict[str, Any],
    probe_flags: list[str],
    model_ref: str,
) -> ExecutiveSummary:
    label = MODE_LABELS[mode]
    reviewed_phrase = (
        "human-reviewed (accept/edit of agent suggestions)"
        if human_reviewed
        else "not human-reviewed"
    )
    headline = (
        f"TrustLens FRIES report for {model_ref}: {fries_score}/10 "
        f"({label}, {reviewed_phrase})"
    )
    bullets = [
        f"Evaluation mode: {label}",
        f"Original FRIES score: {fries_score}/10 (not FRIES2)",
        (
            "Human reviewed: yes — finalized O/S/D was human accepted/edited"
            if human_reviewed
            else "Human reviewed: no — automated agent output, not human-reviewed"
        ),
    ]
    vetoed = sorted(
        str(dim) for dim, value in dimension_scores.items() if float(value) == 0.0
    )
    if vetoed:
        bullets.append(f"Vetoed dimensions (score 0): {', '.join(vetoed)}")
    unique_flags = sorted(set(probe_flags))
    if unique_flags:
        shown = unique_flags[:_MAX_FLAG_BULLET_ITEMS]
        suffix = ", …" if len(unique_flags) > len(shown) else ""
        bullets.append(f"Probe flags: {', '.join(shown)}{suffix}")
    bullets.append(
        "AI-proposed O/S/D is not ground truth "
        "(methodology PROPOSED_REQUIRES_VALIDATION)."
    )
    return ExecutiveSummary(headline=headline, bullets=bullets)


def build_report_json(
    session: Session,
    evaluation: Evaluation,
    *,
    report_version: int,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble + validate the canonical report_v1 document.

    Raises ``ValueError`` if the evaluation has no ``final_scores`` row — the
    service layer guards with a 409 before calling.
    """
    final_row = FinalScoreRepository(session).get_for_evaluation(evaluation.id)
    if final_row is None:
        raise ValueError(f"evaluation {evaluation.id} has no final_scores row")

    service = EvaluationService(session)
    disclosure = service.get_mode_disclosure(evaluation)
    confidence_summary = service.get_confidence_summary(evaluation.id)
    osd_agent = service.get_osd_agent(evaluation.id)
    human_review = service.get_human_review(evaluation.id)

    probes: list[ReportProbe] = []
    all_flags: list[str] = []
    for row in ProbeResultRepository(session).list_for_evaluation(evaluation.id):
        metric_values = row.metric_values or {}
        flags = [str(flag) for flag in metric_values.get("flags") or []]
        all_flags.extend(flags)
        probes.append(
            ReportProbe(
                dimension=row.dimension,
                metric_values=metric_values,
                confidence=row.confidence,
                flags=flags,
                evidence_refs=list(row.evidence_refs or []),
            )
        )

    report = ReportV1(
        report_version=report_version,
        generated_at=generated_at or datetime.now(UTC),
        evaluation=ReportEvaluation(
            id=evaluation.id,
            status=evaluation.status,
            evaluation_mode=evaluation.evaluation_mode,
            model_ref=evaluation.model.hf_repo_id,
            model_id=evaluation.model_id,
            created_at=evaluation.created_at,
            finalized_context={
                "task": evaluation.task,
                "dataset": evaluation.dataset,
                "config": evaluation.config,
                "model_revision": evaluation.model_revision,
                "trustlens_version": evaluation.trustlens_version,
            },
        ),
        mode_disclosure=disclosure,
        score=ReportScore(
            fries_score=final_row.fries_score,
            dimension_scores=final_row.dimension_scores or {},
            finalized_osd=final_row.finalized_osd or {},
            overall_confidence=final_row.overall_confidence,
        ),
        confidence_summary=confidence_summary,
        probes=probes,
        osd_agent=osd_agent.model_dump(mode="json") if osd_agent else None,
        human_review=human_review.model_dump(mode="json") if human_review else None,
        attack_flags=[
            {
                "scenario": flag.scenario,
                "severity": flag.severity,
                "detected": flag.detected,
                "details": flag.details or {},
            }
            for flag in evaluation.attack_flags
        ],
        executive_summary=build_executive_summary(
            mode=evaluation.evaluation_mode,
            human_reviewed=disclosure.human_reviewed,
            fries_score=final_row.fries_score,
            dimension_scores=final_row.dimension_scores or {},
            probe_flags=all_flags,
            model_ref=evaluation.model.hf_repo_id,
        ),
    )
    return report.model_dump(mode="json")
