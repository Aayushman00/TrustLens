"""Canonical report_v1 assembly from persisted evaluation rows (Phase 19).

Reads only what earlier phases persisted — final_scores, probe_results,
osd_agent_outputs, human_reviews — and reuses the EvaluationService getters so
the report carries exactly the same disclosure/score shapes as detail reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation
from app.db.repositories.documentation import DocumentationSourceRepository
from app.db.repositories.final_score import FinalScoreRepository
from app.db.repositories.probe_result import ProbeResultRepository
from app.schemas.documentation import DocumentationSourceRead
from app.schemas.modes import osd_provenance_bullet, score_note_for
from app.schemas.reports import (
    ExecutiveSummary,
    ReportEvaluation,
    ReportProbe,
    ReportScore,
    ReportTraceabilityEntry,
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
    fries_score: float | None,
    dimension_scores: dict[str, Any],
    probe_flags: list[str],
    model_ref: str,
    assessment_engine: str | None = None,
    methodology_status: str | None = None,
    scoring_withheld: bool | None = None,
) -> ExecutiveSummary:
    label = MODE_LABELS[mode]
    reviewed_phrase = (
        "human-reviewed (accept/edit of O/S/D representation)"
        if human_reviewed
        else "not human-reviewed"
    )
    # fries_score is None exactly when scoring is withheld (required O/S/D
    # incomplete) — never a fabricated 0 or placeholder standing in for it.
    score_phrase = f"{fries_score}/10" if fries_score is not None else "FRIES withheld"
    headline = (
        f"TrustLens FRIES report for {model_ref}: {score_phrase} "
        f"({label}, {reviewed_phrase})"
    )
    bullets = [
        f"Evaluation mode: {label} (workflow — not LLM interpretation)",
        (
            f"Original FRIES score: {fries_score}/10 (not FRIES2)"
            if fries_score is not None
            else "Original FRIES score: withheld — required human O/S/D is incomplete for at least one aspect"
        ),
        (
            "Human reviewed: yes — finalized O/S/D was human accepted/edited"
            if human_reviewed
            else "Human reviewed: no"
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
        osd_provenance_bullet(
            assessment_engine=assessment_engine,
            methodology_status=methodology_status,
            scoring_withheld=scoring_withheld,
        )
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

    Raises ``ValueError`` if the evaluation is not yet ``FINALIZED`` — the
    service layer guards with a 409 before calling; there is nothing
    meaningful to report before that point.

    A ``FINALIZED`` evaluation whose FRIES scoring was withheld (no
    ``final_scores`` row — required O/S/D incomplete for at least one
    aspect) still produces a complete evidentiary report: every probe's
    evidence, gates, and status: the documentation/execution/reproducibility
    context; and an explicit withheld score section. Nothing is fabricated
    to fill the gap — the score section is simply ``None``/``withheld``.
    """
    if evaluation.status != EvaluationStatus.FINALIZED:
        raise ValueError(
            f"evaluation {evaluation.id} is not finalized yet "
            f"(status={evaluation.status.value}) — nothing to report"
        )
    final_row = FinalScoreRepository(session).get_for_evaluation(evaluation.id)

    service = EvaluationService(session)
    disclosure = service.get_mode_disclosure(evaluation)
    confidence_summary = service.get_confidence_summary(evaluation.id)
    osd_agent = service.get_osd_agent(evaluation.id)
    human_review = service.get_human_review(evaluation.id)
    # Same extraction EvaluationDetailPage's DimensionCard/EvidenceDossier
    # already render from — reused here, not re-derived, so the report's
    # traceability entries can never drift from what the live UI shows.
    probe_evidence = service.get_probe_evidence(evaluation.id)

    # scoring_withheld already computed once, authoritatively, by
    # get_mode_disclosure (which itself prefers final_scores.finalized_osd
    # when it exists — see the Phase 3 P3-A fix). Reused here verbatim.
    scoring_withheld = (
        bool(disclosure.scoring_withheld)
        if disclosure.scoring_withheld is not None
        else final_row is None
    )
    fries_score = final_row.fries_score if final_row is not None else None
    dimension_scores: dict[str, Any] = (final_row.dimension_scores or {}) if final_row is not None else {}
    finalized_osd: dict[str, Any] = (final_row.finalized_osd or {}) if final_row is not None else {}
    overall_confidence = (
        final_row.overall_confidence
        if final_row is not None
        else (osd_agent.ai_confidence if osd_agent is not None else None)
    )
    finalized_aspects_by_dim: dict[str, dict[str, Any]] = {
        str(a.get("aspect")): a for a in (finalized_osd.get("aspects") or [])
    }

    probes: list[ReportProbe] = []
    all_flags: list[str] = []
    all_limitations: list[str] = []
    for row in ProbeResultRepository(session).list_for_evaluation(evaluation.id):
        metric_values = row.metric_values or {}
        flags = [str(flag) for flag in metric_values.get("flags") or []]
        all_flags.extend(flags)
        limitations_raw = metric_values.get("limitations")
        if isinstance(limitations_raw, list):
            all_limitations.extend(str(item) for item in limitations_raw)
        probes.append(
            ReportProbe(
                dimension=row.dimension,
                metric_values=metric_values,
                confidence=row.confidence,
                flags=flags,
                evidence_refs=list(row.evidence_refs or []),
            )
        )

    evidence_traceability: list[ReportTraceabilityEntry] = []
    for pe in probe_evidence:
        dim_key = pe.dimension.value if hasattr(pe.dimension, "value") else str(pe.dimension)
        human_entry = finalized_aspects_by_dim.get(dim_key)
        human_osd = (
            {
                "O": human_entry.get("O"),
                "S": human_entry.get("S"),
                "D": human_entry.get("D"),
                "O_source": human_entry.get("O_source"),
                "S_source": human_entry.get("S_source"),
                "D_source": human_entry.get("D_source"),
            }
            if human_entry is not None
            else None
        )
        dim_score = dimension_scores.get(dim_key)
        evidence_traceability.append(
            ReportTraceabilityEntry(
                dimension=pe.dimension,
                status=pe.status,
                status_reason=pe.status_reason,
                aspect_scoring=pe.aspect_scoring,
                scored_risk_id=pe.scored_risk_id,
                risks_triggered=pe.risks_triggered,
                gates=pe.gates,
                coverage_ratio=pe.coverage_ratio,
                confidence=pe.confidence,
                evidence_refs=pe.evidence_refs,
                limitations=pe.limitations,
                human_osd=human_osd,
                fries_dimension_score=(
                    float(dim_score) if isinstance(dim_score, (int, float)) else None
                ),
            )
        )

    # Documentation Sources (Phase 2) — read-only list for the evaluated
    # model; no re-fetch, no re-hashing.
    documentation_sources = [
        DocumentationSourceRead.model_validate(row)
        for row in DocumentationSourceRepository(session).list_for_model(evaluation.model_id)
    ]

    # Reproducibility Information — the already-frozen evaluation contract
    # (Phase 7), never re-resolved.
    contract = (evaluation.probe_config or {}).get("evaluation_contract") or {}
    reproducibility = {
        "model_ref": evaluation.model.hf_repo_id,
        "model_revision": evaluation.model_revision,
        "trustlens_version": evaluation.trustlens_version,
        "contract_kind": contract.get("kind"),
        "dataset_key": contract.get("dataset_key"),
        "dataset_revision": contract.get("dataset_revision"),
        "pairing_id": contract.get("pairing_id"),
        "user_dataset_id": contract.get("user_dataset_id"),
        "dataset_content_hash": contract.get("dataset_content_hash"),
    }

    report = ReportV1(
        report_version=report_version,
        generated_at=generated_at or datetime.now(UTC),
        # Copied verbatim from the Evaluation row (stamped at creation time,
        # Task 4.4) — never recomputed or reinterpreted here.
        methodology_version=evaluation.methodology_version,
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
            fries_score=fries_score,
            dimension_scores=dimension_scores,
            finalized_osd=finalized_osd,
            overall_confidence=overall_confidence,
            scoring_withheld=scoring_withheld,
            note=score_note_for(
                assessment_engine=disclosure.assessment_engine,
                methodology_status=disclosure.methodology_status,
                scoring_withheld=scoring_withheld,
            ),
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
            fries_score=fries_score,
            dimension_scores=dimension_scores,
            probe_flags=all_flags,
            model_ref=evaluation.model.hf_repo_id,
            assessment_engine=disclosure.assessment_engine,
            methodology_status=disclosure.methodology_status,
            scoring_withheld=scoring_withheld,
        ),
        evidence_traceability=evidence_traceability,
        execution_environment=evaluation.execution_metadata,
        documentation_sources=documentation_sources,
        reproducibility=reproducibility,
        limitations=sorted(set(all_limitations)),
    )
    return report.model_dump(mode="json")
