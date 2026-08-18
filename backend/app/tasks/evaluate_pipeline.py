"""Evaluation pipeline — probes → O/S/D agent → mode terminal (Phase 9–16).

No Celery dependency. The worker task wraps this; backend tests call it directly.
Does not download HF weights.

Phase 16: after PROBES_COMPLETED the HeuristicOSDAgent proposes per-aspect
O/S/D (**PROPOSED / REQUIRES VALIDATION** — never presented as validated
science) and persists ``osd_agent_outputs``. Mode branch:

- ``AI_ASSISTED``  → AWAITING_REVIEW; **no** ``final_scores`` (human finalize
  is Phase 18).
- ``AI_AUTONOMOUS`` → agent O/S/D treated as finalized for the product path →
  pure FRIESScorer → upsert ``final_scores`` → FINALIZED.

Logic errors anywhere (missing eval, model_ref mismatch, probe/agent/scorer
failure) set FAILED and return without raising so Celery does not retry them.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.confidence.engine import summarize
from app.core.config import get_settings
from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.final_score import FinalScoreRepository
from app.db.repositories.model import ModelRepository
from app.db.repositories.osd_agent_output import OsdAgentOutputRepository
from app.db.repositories.probe_result import ProbeResultRepository
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, AgentResult, ProbeSnapshot
from app.osd.serialize import (
    to_ai_suggestion,
    to_evidence_used,
    to_finalized_osd,
    to_rationale,
)
from app.probes.errors import ProbeError
from app.probes.runner import run_all_probes
from app.schemas.internal import EvaluateModelPayload
from app.scoring.fries import score_from_finalized_osd
from app.storage.evidence_store import EvidenceStore, EvidenceStoreError, get_evidence_store

logger = logging.getLogger("trustlens.pipeline")


def _run_osd_agent(
    session: Session,
    payload: EvaluateModelPayload,
    *,
    model_metadata: dict,
) -> AgentResult:
    """Propose PROPOSED O/S/D from persisted probe rows and persist the row."""
    probe_rows = ProbeResultRepository(session).list_for_evaluation(payload.evaluation_id)
    snapshots = [
        ProbeSnapshot(
            dimension=row.dimension,
            metric_values=row.metric_values or {},
            confidence=row.confidence,
            evidence_refs=list(row.evidence_refs or []),
        )
        for row in probe_rows
    ]
    confidence_summary = (
        summarize(
            [(row.dimension, row.confidence, row.metric_values or {}) for row in probe_rows]
        ).model_dump()
        if probe_rows
        else None
    )
    result = HeuristicOSDAgent().propose(
        AgentContext(
            evaluation_id=payload.evaluation_id,
            model_ref=payload.model_ref,
            model_metadata=model_metadata,
            probe_results=snapshots,
            confidence_summary=confidence_summary,
        )
    )
    OsdAgentOutputRepository(session).create(
        evaluation_id=payload.evaluation_id,
        ai_suggestion=to_ai_suggestion(result),
        ai_confidence=result.overall_confidence,
        evidence_used=to_evidence_used(result),
        rationale=to_rationale(result),
    )
    return result


def run_evaluation_pipeline(
    session: Session,
    payload: EvaluateModelPayload,
    *,
    evidence_store: EvidenceStore | None = None,
) -> None:
    """Drive PENDING → … → AWAITING_REVIEW | FINALIZED (or FAILED).

    All writes flush only; the caller commits (Celery ``get_session`` or test
    fixture).
    """
    evals = EvaluationRepository(session)
    models = ModelRepository(session)

    evaluation = evals.get_by_id(payload.evaluation_id)
    if evaluation is None:
        logger.error(
            "pipeline_missing_evaluation evaluation_id=%s",
            payload.evaluation_id,
        )
        return

    model = models.get_by_id(evaluation.model_id)
    if model is None or model.hf_repo_id != payload.model_ref:
        logger.error(
            "pipeline_model_ref_mismatch evaluation_id=%s expected=%s got=%s",
            payload.evaluation_id,
            payload.model_ref,
            None if model is None else model.hf_repo_id,
        )
        evals.transition_status(
            payload.evaluation_id,
            expected={
                EvaluationStatus.PENDING,
                EvaluationStatus.RUNNING,
                EvaluationStatus.PROBES_COMPLETED,
                EvaluationStatus.AGENT_COMPLETED,
            },
            new=EvaluationStatus.FAILED,
        )
        return

    if evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.PENDING,
        new=EvaluationStatus.RUNNING,
    ) is None:
        logger.info(
            "pipeline_skip_not_pending evaluation_id=%s status=%s",
            payload.evaluation_id,
            evaluation.status,
        )
        return

    store = evidence_store if evidence_store is not None else get_evidence_store(get_settings())
    if store is None:
        logger.error(
            "pipeline_no_evidence_store evaluation_id=%s",
            payload.evaluation_id,
        )
        evals.transition_status(
            payload.evaluation_id,
            expected=EvaluationStatus.RUNNING,
            new=EvaluationStatus.FAILED,
        )
        return

    try:
        outputs = run_all_probes(
            session,
            payload,
            model_metadata=model.model_metadata or {},
            evidence_store=store,
            model_revision=model.revision,
            model_checksum=model.checksum,
        )
    except (ProbeError, EvidenceStoreError):
        logger.exception(
            "pipeline_probes_failed evaluation_id=%s",
            payload.evaluation_id,
        )
        evals.transition_status(
            payload.evaluation_id,
            expected=EvaluationStatus.RUNNING,
            new=EvaluationStatus.FAILED,
        )
        return

    evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.RUNNING,
        new=EvaluationStatus.PROBES_COMPLETED,
    )

    # Phase 16: O/S/D agent stage — persists a PROPOSED suggestion row.
    try:
        agent_result = _run_osd_agent(
            session,
            payload,
            model_metadata=model.model_metadata or {},
        )
    except Exception:
        logger.exception(
            "pipeline_osd_agent_failed evaluation_id=%s",
            payload.evaluation_id,
        )
        evals.transition_status(
            payload.evaluation_id,
            expected=EvaluationStatus.PROBES_COMPLETED,
            new=EvaluationStatus.FAILED,
        )
        return

    evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.PROBES_COMPLETED,
        new=EvaluationStatus.AGENT_COMPLETED,
    )

    if payload.evaluation_mode == EvaluationMode.AI_ASSISTED:
        # Human finalize (Phase 18) reviews the agent suggestion; no final_scores.
        evals.transition_status(
            payload.evaluation_id,
            expected=EvaluationStatus.AGENT_COMPLETED,
            new=EvaluationStatus.AWAITING_REVIEW,
        )
        logger.info(
            "pipeline_complete evaluation_id=%s mode=%s terminal=%s probe_count=%s",
            payload.evaluation_id,
            payload.evaluation_mode.value,
            EvaluationStatus.AWAITING_REVIEW.value,
            len(outputs),
        )
        return

    # Autonomous: agent suggestion becomes the finalized O/S/D for the product
    # path (still labeled PROPOSED_REQUIRES_VALIDATION) → pure FRIES scorer.
    try:
        finalized_osd = to_finalized_osd(agent_result)
        fries = score_from_finalized_osd(finalized_osd)
        FinalScoreRepository(session).upsert(
            evaluation_id=payload.evaluation_id,
            fries_score=fries.fries_score,
            dimension_scores=fries.dimension_scores,
            finalized_osd=finalized_osd,
            overall_confidence=agent_result.overall_confidence,
            evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        )
    except Exception:
        logger.exception(
            "pipeline_fries_scoring_failed evaluation_id=%s",
            payload.evaluation_id,
        )
        evals.transition_status(
            payload.evaluation_id,
            expected=EvaluationStatus.AGENT_COMPLETED,
            new=EvaluationStatus.FAILED,
        )
        return

    evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.AGENT_COMPLETED,
        new=EvaluationStatus.FINALIZED,
    )
    logger.info(
        "pipeline_complete evaluation_id=%s mode=%s terminal=%s probe_count=%s fries=%s",
        payload.evaluation_id,
        payload.evaluation_mode.value,
        EvaluationStatus.FINALIZED.value,
        len(outputs),
        fries.fries_score,
    )
