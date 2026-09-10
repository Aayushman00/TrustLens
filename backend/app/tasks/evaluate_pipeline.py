"""Evaluation pipeline — probes → O/S/D agent → mode terminal (Phase 9–16).

No Celery dependency. The worker task wraps this; backend tests call it directly.
Does not download HF weights.

Phase 16+: after PROBES_COMPLETED the O/S/D mapper proposes per-aspect
representation. Default ``assessment_engine=deterministic`` abstains O/S/D;
``legacy_heuristic`` uses HeuristicOSDAgent (versioned legacy).

- ``AI_ASSISTED``  → AWAITING_REVIEW; **no** ``final_scores`` (human finalize
  is Phase 18).
- ``AI_AUTONOMOUS`` → when all five aspects have complete O/S/D, treat the
  agent output as finalized → pure FRIESScorer → upsert ``final_scores`` →
  FINALIZED. If any aspect abstained (null O/S/D), scoring is withheld:
  no ``final_scores`` row and no overall FRIES number; the evaluation still
  reaches FINALIZED so the run is complete. Partial/withheld is recorded on
  ``osd_agent_outputs.ai_suggestion``.

Logic errors anywhere (missing eval, model_ref mismatch, probe/agent/scorer
failure) set FAILED and return without raising so Celery does not retry them.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.confidence.engine import summarize
from app.core.config import get_settings
from app.db.enums import (
    EvaluationMode,
    EvaluationStatus,
    FriesDimension,
    ProbeEvaluationStatus,
)
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_event import (
    EVENT_AGENT_COMPLETED,
    EVENT_AWAITING_REVIEW,
    EVENT_EVALUATION_FAILED,
    EVENT_EVALUATION_FINALIZED,
    EVENT_EVALUATION_STARTED,
    EVENT_PROBES_COMPLETED,
    REASON_MODEL_REF_MISMATCH,
    REASON_NO_EVIDENCE_STORE,
    REASON_OSD_AGENT_ERROR,
    REASON_PROBE_ERROR,
    REASON_SCORING_ERROR,
    REASON_WORKER_RETRIES_EXHAUSTED,
    EvaluationEventRepository,
)
from app.db.repositories.final_score import FinalScoreRepository
from app.db.repositories.model import ModelRepository
from app.db.repositories.osd_agent_output import OsdAgentOutputRepository
from app.db.repositories.probe_result import ProbeResultRepository
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, AgentResult, ProbeSnapshot
from app.osd.deterministic import DeterministicOSDMapper, resolve_assessment_engine
from app.osd.serialize import (
    FRIES_ASPECT_COUNT,
    to_ai_suggestion,
    to_evidence_used,
    to_finalized_osd,
    to_rationale,
)
from app.probes.base import ProbeOutput
from app.probes.errors import ProbeError
from app.probes.runner import run_all_probes
from app.schemas.internal import EvaluateModelPayload
from app.scoring.fries import score_from_finalized_osd
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION
from app.storage.evidence_store import (
    EvidenceStore,
    EvidenceStoreError,
    get_dataset_content_store,
    get_dataset_store,
    get_evidence_store,
)

logger = logging.getLogger("trustlens.pipeline")

# Only these probes ever invoke LocalHFBackend and report real device_info;
# checked in this order since Fairness runs first in FRIES_PROBE_ORDER.
_INFERENCE_CAPABLE_DIMENSIONS = (FriesDimension.FAIRNESS, FriesDimension.ROBUSTNESS)


def _extract_execution_metadata(outputs: list[ProbeOutput]) -> dict | None:
    """Real device/GPU evidence from whichever probe actually ran inference.

    Reads the ``inference`` block each inference-capable probe already
    persists in its own ``metric_values`` (see ``fairness.py``/
    ``robustness.py``) — never recomputes or invents device state. Returns
    ``None`` when no probe executed inference (e.g. documentation-only
    contract, or inference failed before a device was selected).
    """
    by_dimension = {output.dimension: output for output in outputs}
    for dimension in _INFERENCE_CAPABLE_DIMENSIONS:
        output = by_dimension.get(dimension)
        if output is None:
            continue
        inference = (output.metric_values or {}).get("inference")
        if isinstance(inference, dict) and inference.get("execution_device"):
            return inference
    return None


def _run_osd_agent(
    session: Session,
    payload: EvaluateModelPayload,
    *,
    model_metadata: dict,
    probe_config: dict | None = None,
) -> AgentResult:
    """Propose O/S/D representation from persisted probe rows and persist."""
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
    not_applicable_dimension_count = (
        sum(
            1
            for row in probe_rows
            if (row.metric_values or {}).get("probe_status")
            == ProbeEvaluationStatus.NOT_APPLICABLE.value
        )
        if payload.methodology_version != LEGACY_METHODOLOGY_VERSION
        else 0
    )
    confidence_summary = (
        summarize(
            [(row.dimension, row.confidence, row.metric_values or {}) for row in probe_rows],
            methodology_version=payload.methodology_version,
        ).model_dump()
        if probe_rows
        else None
    )
    engine = resolve_assessment_engine(probe_config)
    mapper = HeuristicOSDAgent() if engine == "legacy_heuristic" else DeterministicOSDMapper()
    result = mapper.propose(
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
        ai_suggestion=to_ai_suggestion(
            result,
            required_aspect_count=FRIES_ASPECT_COUNT - not_applicable_dimension_count,
        ),
        ai_confidence=result.overall_confidence,
        evidence_used=to_evidence_used(result),
        rationale=to_rationale(result),
    )
    return result


def _fail_transition(
    evals: EvaluationRepository,
    events: EvaluationEventRepository,
    evaluation_id: uuid.UUID,
    *,
    expected: EvaluationStatus | set[EvaluationStatus],
    reason_code: str,
    from_status: str,
) -> None:
    """Shared shape for every FAILED transition inside
    ``run_evaluation_pipeline`` — same CAS-then-conditionally-record-event
    pattern repeated at each failure point, differing only in which
    status(es) the CAS expects and the reason/from_status recorded.

    Event insertion happens only after ``transition_status`` succeeds
    (returns non-None) — a stale/retried invocation whose CAS fails here
    (the evaluation already moved on) inserts no event, by construction,
    never by a special-case dedup check. This invariant applies at every
    call site below, not just the first.
    """
    if evals.transition_status(evaluation_id, expected=expected, new=EvaluationStatus.FAILED) is not None:
        events.create(
            evaluation_id=evaluation_id,
            event_type=EVENT_EVALUATION_FAILED,
            detail={"reason_code": reason_code, "from_status": from_status},
        )


def fail_stuck_running_evaluation(
    session: Session,
    evaluation_id: uuid.UUID,
    *,
    reason_code: str = REASON_WORKER_RETRIES_EXHAUSTED,
) -> bool:
    """Transition a RUNNING evaluation straight to FAILED via the same atomic
    CAS (``transition_status``) used everywhere else in the lifecycle.

    Called only from the worker's ``Task.on_failure`` — i.e. only once the
    Celery task itself has permanently failed (autoretry_for exhausted its
    max_retries on a transient ConnectionError/TimeoutError, or any other
    unhandled exception escaped the task body). This is not a second status
    mutation path: it is the exact same CAS, invoked from one more call site.

    Idempotent and safe by construction: the CAS only applies (and only then
    is an event recorded) if the evaluation is still RUNNING. If the pipeline
    itself already reached a terminal state (FAILED/AWAITING_REVIEW/
    FINALIZED) before the task-level exception surfaced, or if this fires
    twice for a redelivered/duplicate failure signal, this is a clean no-op —
    never overwrites another terminal state, never records a second event.
    """
    updated = EvaluationRepository(session).transition_status(
        evaluation_id,
        expected=EvaluationStatus.RUNNING,
        new=EvaluationStatus.FAILED,
    )
    if updated is None:
        return False
    EvaluationEventRepository(session).create(
        evaluation_id=evaluation_id,
        event_type=EVENT_EVALUATION_FAILED,
        detail={"reason_code": reason_code, "from_status": EvaluationStatus.RUNNING.value},
    )
    return True


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
    events = EvaluationEventRepository(session)

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
        _fail_transition(
            evals,
            events,
            payload.evaluation_id,
            expected={
                EvaluationStatus.PENDING,
                EvaluationStatus.RUNNING,
                EvaluationStatus.PROBES_COMPLETED,
                EvaluationStatus.AGENT_COMPLETED,
            },
            reason_code=REASON_MODEL_REF_MISMATCH,
            from_status=evaluation.status.value,
        )
        return

    started = evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.PENDING,
        new=EvaluationStatus.RUNNING,
    )
    if started is None:
        logger.info(
            "pipeline_skip_not_pending evaluation_id=%s status=%s",
            payload.evaluation_id,
            evaluation.status,
        )
        return
    events.create(evaluation_id=payload.evaluation_id, event_type=EVENT_EVALUATION_STARTED)

    store = evidence_store if evidence_store is not None else get_evidence_store(get_settings())
    if store is None:
        logger.error(
            "pipeline_no_evidence_store evaluation_id=%s",
            payload.evaluation_id,
        )
        _fail_transition(
            evals,
            events,
            payload.evaluation_id,
            expected=EvaluationStatus.RUNNING,
            reason_code=REASON_NO_EVIDENCE_STORE,
            from_status=EvaluationStatus.RUNNING.value,
        )
        return

    try:
        outputs = run_all_probes(
            session,
            payload,
            model_metadata=model.model_metadata or {},
            evidence_store=store,
            # Phase 7: the evaluation's frozen revision is authoritative — never
            # re-read the (possibly re-imported/drifted) live Model row here.
            model_revision=payload.model_revision,
            model_checksum=model.checksum,
            dataset_store=get_dataset_store(get_settings()),
            dataset_content_store=get_dataset_content_store(get_settings()),
        )
    except (ProbeError, EvidenceStoreError):
        logger.exception(
            "pipeline_probes_failed evaluation_id=%s",
            payload.evaluation_id,
        )
        _fail_transition(
            evals,
            events,
            payload.evaluation_id,
            expected=EvaluationStatus.RUNNING,
            reason_code=REASON_PROBE_ERROR,
            from_status=EvaluationStatus.RUNNING.value,
        )
        return

    if evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.RUNNING,
        new=EvaluationStatus.PROBES_COMPLETED,
    ) is not None:
        events.create(
            evaluation_id=payload.evaluation_id,
            event_type=EVENT_PROBES_COMPLETED,
            detail={"probe_count": len(outputs)},
        )

    execution_metadata = _extract_execution_metadata(outputs)
    if execution_metadata is not None:
        evals.set_execution_metadata(payload.evaluation_id, execution_metadata)

    session.refresh(evaluation)
    osd_probe_config = payload.probe_config or evaluation.probe_config or {}

    # Phase 16: O/S/D agent stage — persists a PROPOSED suggestion row.
    try:
        agent_result = _run_osd_agent(
            session,
            payload,
            model_metadata=model.model_metadata or {},
            probe_config=osd_probe_config,
        )
    except Exception:
        logger.exception(
            "pipeline_osd_agent_failed evaluation_id=%s",
            payload.evaluation_id,
        )
        _fail_transition(
            evals,
            events,
            payload.evaluation_id,
            expected=EvaluationStatus.PROBES_COMPLETED,
            reason_code=REASON_OSD_AGENT_ERROR,
            from_status=EvaluationStatus.PROBES_COMPLETED.value,
        )
        return

    if evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.PROBES_COMPLETED,
        new=EvaluationStatus.AGENT_COMPLETED,
    ) is not None:
        events.create(evaluation_id=payload.evaluation_id, event_type=EVENT_AGENT_COMPLETED)

    if payload.evaluation_mode == EvaluationMode.AI_ASSISTED:
        # Human finalize (Phase 18) reviews the agent suggestion; no final_scores.
        if evals.transition_status(
            payload.evaluation_id,
            expected=EvaluationStatus.AGENT_COMPLETED,
            new=EvaluationStatus.AWAITING_REVIEW,
        ) is not None:
            events.create(evaluation_id=payload.evaluation_id, event_type=EVENT_AWAITING_REVIEW)
        logger.info(
            "pipeline_complete evaluation_id=%s mode=%s terminal=%s probe_count=%s",
            payload.evaluation_id,
            payload.evaluation_mode.value,
            EvaluationStatus.AWAITING_REVIEW.value,
            len(outputs),
        )
        return

    # Autonomous: complete O/S/D → FRIES; incomplete evidence → withhold score.
    try:
        finalized_osd = to_finalized_osd(agent_result)
        complete_n = int(finalized_osd.get("complete_aspect_count") or 0)
        if complete_n < FRIES_ASPECT_COUNT:
            if evals.transition_status(
                payload.evaluation_id,
                expected=EvaluationStatus.AGENT_COMPLETED,
                new=EvaluationStatus.FINALIZED,
            ) is not None:
                # scoring_withheld is read from finalized_osd — already computed
                # by the untouched to_finalized_osd/FRIES-completeness logic,
                # never recomputed here. The event references, never decides.
                events.create(
                    evaluation_id=payload.evaluation_id,
                    event_type=EVENT_EVALUATION_FINALIZED,
                    detail={
                        "evaluation_mode": EvaluationMode.AI_AUTONOMOUS.value,
                        "scoring_withheld": True,
                    },
                )
            logger.info(
                "pipeline_fries_scoring_withheld evaluation_id=%s "
                "complete_aspects=%s/%s probe_count=%s",
                payload.evaluation_id,
                complete_n,
                FRIES_ASPECT_COUNT,
                len(outputs),
            )
            return
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
        _fail_transition(
            evals,
            events,
            payload.evaluation_id,
            expected=EvaluationStatus.AGENT_COMPLETED,
            reason_code=REASON_SCORING_ERROR,
            from_status=EvaluationStatus.AGENT_COMPLETED.value,
        )
        return

    if evals.transition_status(
        payload.evaluation_id,
        expected=EvaluationStatus.AGENT_COMPLETED,
        new=EvaluationStatus.FINALIZED,
    ) is not None:
        events.create(
            evaluation_id=payload.evaluation_id,
            event_type=EVENT_EVALUATION_FINALIZED,
            detail={"evaluation_mode": EvaluationMode.AI_AUTONOMOUS.value, "scoring_withheld": False},
        )
    logger.info(
        "pipeline_complete evaluation_id=%s mode=%s terminal=%s probe_count=%s fries=%s",
        payload.evaluation_id,
        payload.evaluation_mode.value,
        EvaluationStatus.FINALIZED.value,
        len(outputs),
        fries.fries_score,
    )
