"""Evaluation service — create/enqueue, enriched reads, review + finalize (Phase 7–18)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.api.errors import AppError, ConflictError, NotFoundError, ValidationAppError
from app.confidence.engine import ConfidenceSummary, summarize
from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation, HumanReview, ProbeResult
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_event import (
    EVENT_EVALUATION_CREATED,
    EVENT_EVALUATION_FINALIZED,
    EVENT_EVALUATION_REQUEUED,
    EVENT_HUMAN_REVIEW_SUBMITTED,
    EvaluationEventRepository,
)
from app.db.repositories.final_score import FinalScoreRepository
from app.db.repositories.human_review import HumanReviewRepository
from app.db.repositories.model import ModelRepository
from app.db.repositories.osd_agent_output import OsdAgentOutputRepository
from app.db.repositories.probe_result import ProbeResultRepository
from app.osd.review import (
    build_overrides,
    merge_review_aspects,
    to_finalized_osd_assisted,
)
from app.schemas.evaluations import (
    EvaluationCreate,
    EvaluationRead,
    FinalScoreRead,
    OsdAgentRead,
    ProbeEvidenceRead,
    ProbeProgress,
)
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import (
    METHODOLOGY_STATUS_PROPOSED,
    ModeDisclosure,
    build_mode_disclosure,
    disclaimer_for,
    engine_from_osd_payload,
    fries_status_for,
)
from app.schemas.reviews import HumanReviewRead, HumanReviewRequest
from app.scoring.fries import score_from_finalized_osd
from app.tasks.celery_client import enqueue_evaluate_model

logger = logging.getLogger("trustlens.api")

FRIES_PROBE_TOTAL = 5


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _probe_evidence_from_row(row: ProbeResult) -> ProbeEvidenceRead:
    metrics = row.metric_values or {}
    reliability = metrics.get("reliability")
    failed_gates = None
    if isinstance(reliability, dict):
        raw_gates = reliability.get("failed_gates")
        if isinstance(raw_gates, list):
            failed_gates = [str(g) for g in raw_gates]
    flags_raw = metrics.get("flags")
    flags = [str(f) for f in flags_raw] if isinstance(flags_raw, list) else None
    risks_raw = metrics.get("risks_triggered")
    risks = [str(r) for r in risks_raw] if isinstance(risks_raw, list) else None
    limitations_raw = metrics.get("limitations")
    limitations = (
        [str(item) for item in limitations_raw] if isinstance(limitations_raw, list) else None
    )
    claim = metrics.get("claim_boundary")
    pairing = metrics.get("pairing")
    pairing_id = None
    if isinstance(pairing, dict) and pairing.get("id") is not None:
        pairing_id = str(pairing.get("id"))
    elif isinstance(metrics.get("pairing_id"), str):
        pairing_id = metrics.get("pairing_id")
    n_evaluated = metrics.get("n_evaluated")
    if not isinstance(n_evaluated, (int, float)):
        n_evaluated = None
    coverage = metrics.get("coverage_ratio")
    if not isinstance(coverage, (int, float)):
        coverage = None
    return ProbeEvidenceRead(
        dimension=row.dimension,
        status=_optional_str(metrics.get("probe_status") or metrics.get("status")),
        status_reason=_optional_str(
            metrics.get("probe_status_reason") or metrics.get("status_reason")
        ),
        methodology_version=_optional_str(metrics.get("methodology_version")),
        gates=failed_gates,
        risks_triggered=risks,
        aspect_scoring=_optional_str(metrics.get("aspect_scoring")),
        scored_risk_id=_optional_str(metrics.get("scored_risk_id")),
        claim_boundary=claim if isinstance(claim, dict) else None,
        limitations=limitations,
        flags=flags,
        coverage_ratio=float(coverage) if coverage is not None else None,
        n_evaluated=int(n_evaluated) if n_evaluated is not None else None,
        fairness_mode=_optional_str(metrics.get("fairness_mode")),
        pairing_id=pairing_id,
        confidence=row.confidence,
        evidence_refs=list(row.evidence_refs or []),
        model_ref=_optional_str(metrics.get("model_ref")),
        model_revision=_optional_str(metrics.get("model_revision")),
        dataset_key=_optional_str(metrics.get("dataset_key")),
        dataset_revision=_optional_str(metrics.get("dataset_revision")),
        evaluation_class=_optional_str(metrics.get("evaluation_class")),
        inference_executed=(
            bool(metrics["inference_executed"])
            if isinstance(metrics.get("inference_executed"), bool)
            else None
        ),
        metric_values=metrics or None,
    )


class EvaluationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._evals = EvaluationRepository(session)
        self._events = EvaluationEventRepository(session)
        self._models = ModelRepository(session)
        self._probes = ProbeResultRepository(session)
        self._osd_outputs = OsdAgentOutputRepository(session)
        self._final_scores = FinalScoreRepository(session)
        self._human_reviews = HumanReviewRepository(session)

    def create_evaluation(self, data: EvaluationCreate) -> Evaluation:
        """Bare, contract-free creation (Phase 7) — no dataset/contract
        selection of any kind. The resulting evaluation carries no
        ``evaluation_contract`` at all, so Fairness/Robustness both resolve
        NOT_APPLICABLE. Use ``EvaluationServiceV2.create_from_draft`` for a
        real Fairness/Robustness configuration."""
        model = self._models.get_by_id(data.model_id)
        if model is None:
            raise NotFoundError(
                f"Model {data.model_id} not found",
                details={"model_id": data.model_id},
            )
        probe_config = dict(data.probe_config or {})
        if probe_config.get("assessment_engine") is None:
            probe_config["assessment_engine"] = "deterministic"
        row = self._evals.create(
            model_id=data.model_id,
            evaluation_mode=data.evaluation_mode,
            status=EvaluationStatus.PENDING,
            probe_config=probe_config,
            task=data.task,
            dataset=data.dataset,
            config=data.config,
            model_revision=model.revision,
            trustlens_version=data.trustlens_version,
        )
        payload = EvaluateModelPayload(
            evaluation_id=row.id,
            model_ref=model.hf_repo_id,
            evaluation_mode=row.evaluation_mode,
            probe_config=row.probe_config or {},
            model_revision=row.model_revision,
        )
        task_id = enqueue_evaluate_model(payload)
        logger.info(
            "evaluation_created evaluation_id=%s model_ref=%s enqueue_task_id=%s",
            row.id,
            model.hf_repo_id,
            task_id,
        )
        # enqueue_evaluate_model silently returns None on a broker failure,
        # leaving the row at PENDING with no other visible signal — recording
        # enqueued/task_id here is what makes that state observable at all.
        self._events.create(
            evaluation_id=row.id,
            event_type=EVENT_EVALUATION_CREATED,
            detail={"enqueued": task_id is not None, "task_id": task_id},
        )
        return row

    def reconcile_enqueue_failure(self, evaluation_id: uuid.UUID) -> Evaluation:
        """Operator-triggered recovery for a confirmed Celery enqueue failure
        (audit P1-4) — NOT an automatic/self-healing background process.

        Eligibility is decided only from the confirmed ``enqueued`` signal
        already recorded on this evaluation's own event trail (never an age
        heuristic, which could misclassify a legitimate slow-running
        evaluation): the evaluation must still be PENDING, and its most
        recent enqueue-related event (``evaluation_created`` or a prior
        ``evaluation_requeued``) must have ``enqueued: false``. Anything else
        — already enqueued, already running, already terminal — is refused.

        Re-enqueuing is safe to retry here without bypassing the lifecycle:
        the payload is reconstructed byte-identical to the original from the
        persisted row, and the worker's own PENDING->RUNNING CAS
        (evaluate_pipeline.py) admits only one execution even if this ever
        races with a delivery that actually succeeded — this call only ever
        records what happened, it never changes ``status`` itself.
        """
        row = self._evals.get_by_id(evaluation_id)
        if row is None:
            raise NotFoundError(
                f"Evaluation {evaluation_id} not found",
                details={"evaluation_id": str(evaluation_id)},
            )
        if row.status != EvaluationStatus.PENDING:
            raise ConflictError(
                "Only a PENDING evaluation can be reconciled",
                details={"evaluation_id": str(evaluation_id), "status": row.status.value},
            )
        events = self._events.list_for_evaluation(evaluation_id)
        enqueue_events = [
            e for e in events if e.event_type in (EVENT_EVALUATION_CREATED, EVENT_EVALUATION_REQUEUED)
        ]
        last_enqueue_event = enqueue_events[-1] if enqueue_events else None
        confirmed_failed = bool(
            last_enqueue_event is not None
            and (last_enqueue_event.detail or {}).get("enqueued") is False
        )
        if not confirmed_failed:
            raise ConflictError(
                "No confirmed enqueue failure to reconcile for this evaluation",
                details={"evaluation_id": str(evaluation_id)},
            )
        model = self._models.get_by_id(row.model_id)
        if model is None:
            raise ConflictError(
                "Cannot reconcile — the evaluation's model no longer exists",
                details={"evaluation_id": str(evaluation_id), "model_id": row.model_id},
            )
        probe_config = row.probe_config or {}
        payload = EvaluateModelPayload(
            evaluation_id=row.id,
            model_ref=model.hf_repo_id,
            evaluation_mode=row.evaluation_mode,
            probe_config=probe_config,
            model_revision=row.model_revision,
            evaluation_contract=probe_config.get("evaluation_contract", {}),
            methodology_version=row.methodology_version,
        )
        task_id = enqueue_evaluate_model(payload)
        logger.info(
            "evaluation_requeued evaluation_id=%s enqueue_task_id=%s",
            row.id,
            task_id,
        )
        self._events.create(
            evaluation_id=row.id,
            event_type=EVENT_EVALUATION_REQUEUED,
            detail={"enqueued": task_id is not None, "task_id": task_id},
        )
        return row

    def get_evaluation(self, evaluation_id: uuid.UUID) -> Evaluation:
        row = self._evals.get_by_id(evaluation_id)
        if row is None:
            raise NotFoundError(
                f"Evaluation {evaluation_id} not found",
                details={"evaluation_id": str(evaluation_id)},
            )
        return row

    def get_probe_progress(self, evaluation_id: uuid.UUID) -> ProbeProgress:
        completed = self._probes.count_for_evaluation(evaluation_id)
        return ProbeProgress(completed=completed, total=FRIES_PROBE_TOTAL)

    def get_probe_evidence(self, evaluation_id: uuid.UUID) -> list[ProbeEvidenceRead]:
        """Detail-only probe summaries from persisted rows (insertion order)."""
        return [
            _probe_evidence_from_row(row) for row in self._probes.list_for_evaluation(evaluation_id)
        ]

    def get_confidence_summary(self, evaluation_id: uuid.UUID) -> ConfidenceSummary | None:
        """Phase 15: aggregate persisted probe confidences; None until ≥1 probe row."""
        rows = self._probes.list_for_evaluation(evaluation_id)
        if not rows:
            return None
        evaluation = self.get_evaluation(evaluation_id)
        return summarize(
            [(row.dimension, row.confidence, row.metric_values or {}) for row in rows],
            methodology_version=evaluation.methodology_version,
        )

    def get_osd_agent(self, evaluation_id: uuid.UUID) -> OsdAgentRead | None:
        """Phase 16: latest PROPOSED O/S/D suggestion; None until the agent ran."""
        row = self._osd_outputs.latest_for_evaluation(evaluation_id)
        if row is None:
            return None
        suggestion = row.ai_suggestion or {}
        return OsdAgentRead(
            ai_suggestion=suggestion,
            ai_confidence=row.ai_confidence,
            methodology_status=str(
                suggestion.get("methodology_status", "PROPOSED_REQUIRES_VALIDATION")
            ),
            rationale=row.rationale,
        )

    @staticmethod
    def _review_to_read(row: HumanReview) -> HumanReviewRead:
        overrides = row.overrides or {}
        return HumanReviewRead(
            id=row.id,
            evaluation_id=row.evaluation_id,
            human_changed=row.human_changed,
            accept_all=bool(overrides.get("accept_all", False)),
            approved_osd=overrides.get("approved_osd") or {},
            review_rationale=overrides.get("review_rationale"),
            notes=row.notes,
            created_at=row.created_at,
        )

    def get_human_review(self, evaluation_id: uuid.UUID) -> HumanReviewRead | None:
        """Phase 18: latest human review ("latest wins"); None until one exists."""
        row = self._human_reviews.latest_for_evaluation(evaluation_id)
        if row is None:
            return None
        return self._review_to_read(row)

    def submit_human_review(
        self,
        evaluation_id: uuid.UUID,
        body: HumanReviewRequest,
    ) -> HumanReviewRead:
        """Phase 18: structured accept/edit of the agent O/S/D suggestion.

        Assisted-only, and only at ``AWAITING_REVIEW``. Each POST appends a new
        ``human_reviews`` row; finalize uses the latest (audit trail preserved).
        """
        evaluation = self.get_evaluation(evaluation_id)
        details = {
            "evaluation_id": str(evaluation.id),
            "status": evaluation.status.value,
            "evaluation_mode": evaluation.evaluation_mode.value,
        }
        if evaluation.evaluation_mode == EvaluationMode.AI_AUTONOMOUS:
            raise AppError(
                "ASSISTED_ONLY",
                "Human review applies to AI_ASSISTED evaluations only; Autonomous "
                "evaluations are finalized by the pipeline without review",
                status_code=409,
                details=details,
            )
        if evaluation.status == EvaluationStatus.FINALIZED:
            raise AppError(
                "ALREADY_FINALIZED",
                "Evaluation is already finalized — the human-approved O/S/D is locked",
                status_code=409,
                details=details,
            )
        if evaluation.status == EvaluationStatus.FAILED:
            raise AppError(
                "FAILED_EVALUATION",
                "Evaluation failed — there is nothing to review; re-run the evaluation",
                status_code=409,
                details=details,
            )
        if evaluation.status != EvaluationStatus.AWAITING_REVIEW:
            raise AppError(
                "NOT_READY",
                "Assisted evaluation has not reached AWAITING_REVIEW yet — the agent "
                "suggestion is not ready for review",
                status_code=409,
                details=details,
            )
        agent_row = self._osd_outputs.latest_for_evaluation(evaluation.id)
        suggestion = (agent_row.ai_suggestion or {}) if agent_row is not None else {}
        if not suggestion.get("aspects"):
            raise AppError(
                "NOT_READY",
                "No agent O/S/D suggestion found to review",
                status_code=409,
                details=details,
            )
        edits = [
            edit.model_dump(mode="json", exclude_none=True) for edit in body.aspects or []
        ]
        try:
            approved, human_changed = merge_review_aspects(
                suggestion, edits, accept_all=body.accept_all
            )
        except ValueError as exc:
            raise ValidationAppError(str(exc), details=details) from exc
        overrides = build_overrides(
            accept_all=body.accept_all,
            approved_aspects=approved,
            agent_suggestion=suggestion,
            review_rationale=body.review_rationale,
        )
        row = self._human_reviews.create(
            evaluation_id=evaluation.id,
            overrides=overrides,
            human_changed=human_changed,
            notes=body.notes,
        )
        logger.info(
            "human_review_created evaluation_id=%s review_id=%s "
            "accept_all=%s human_changed=%s",
            evaluation.id,
            row.id,
            body.accept_all,
            human_changed,
        )
        # A real, legitimate fact each time — Phase 3 explicitly supports
        # multiple reviews before finalize ("latest wins"), so this event may
        # recur; O/S/D values themselves stay solely in human_reviews.overrides.
        self._events.create(
            evaluation_id=evaluation.id,
            event_type=EVENT_HUMAN_REVIEW_SUBMITTED,
            detail={"accept_all": body.accept_all, "human_changed": human_changed},
        )
        return self._review_to_read(row)

    def get_final_score(self, evaluation_id: uuid.UUID) -> FinalScoreRead | None:
        """Phase 16/17: FRIES result + denormalized disclosure once finalized."""
        row = self._final_scores.get_for_evaluation(evaluation_id)
        if row is None:
            return None
        finalized = row.finalized_osd or {}
        # Pre-Phase-17 rows lack disclosure keys — derive from mode with .get fallbacks.
        human_reviewed = bool(finalized.get("human_reviewed", False))
        disclaimer = finalized.get("disclaimer") or disclaimer_for(
            row.evaluation_mode,
            human_reviewed=human_reviewed,
            assessment_engine=engine_from_osd_payload(finalized),
            methodology_status=str(finalized.get("methodology_status") or "") or None,
            scoring_withheld=finalized.get("scoring_withheld"),
        )
        read = FinalScoreRead.model_validate(row)
        return read.model_copy(
            update={"human_reviewed": human_reviewed, "disclaimer": disclaimer}
        )

    def get_mode_disclosure(self, evaluation: Evaluation) -> ModeDisclosure:
        """Phase 17: always present on detail reads; derived from mode + score + agent."""
        final_row = self._final_scores.get_for_evaluation(evaluation.id)
        # The human_reviews table is the authoritative record of whether a
        # review was actually submitted — never derived from final_scores,
        # which has no row at all when FRIES is withheld (incomplete O/S/D)
        # even though a genuine review happened (audit: mode_disclosure
        # defect found in item 8 live validation).
        human_reviewed = self._human_reviews.latest_for_evaluation(evaluation.id) is not None
        osd_row = self._osd_outputs.latest_for_evaluation(evaluation.id)
        suggestion = (osd_row.ai_suggestion or {}) if osd_row else {}
        methodology_status = str(
            suggestion.get("methodology_status", METHODOLOGY_STATUS_PROPOSED)
        )
        assessment_engine = engine_from_osd_payload(suggestion)
        if assessment_engine is None:
            cfg = evaluation.probe_config or {}
            raw_engine = cfg.get("assessment_engine")
            assessment_engine = raw_engine if isinstance(raw_engine, str) else None
        # Prefer the authoritative, human-reviewed completion state from
        # final_scores.finalized_osd (real state, set by
        # to_finalized_osd_assisted/to_finalized_osd from the actual
        # completed aspect count) over the agent's own pre-review suggestion
        # — the latter is always incomplete for the deterministic engine and
        # goes stale the moment a human finishes supplying O/S/D, since the
        # agent itself never revisits its abstention.
        if final_row is not None:
            scoring_withheld = bool((final_row.finalized_osd or {}).get("scoring_withheld", False))
        else:
            scoring_withheld = suggestion.get("scoring_withheld")
            if scoring_withheld is None and evaluation.status == EvaluationStatus.FINALIZED:
                scoring_withheld = True
            scoring_withheld = bool(scoring_withheld) if scoring_withheld is not None else None
        has_score = final_row is not None
        return build_mode_disclosure(
            evaluation_mode=evaluation.evaluation_mode,
            human_reviewed=human_reviewed,
            methodology_status=methodology_status,
            assessment_engine=assessment_engine,
            scoring_withheld=scoring_withheld,
            fries_status=fries_status_for(
                scoring_withheld=scoring_withheld,
                has_final_score=has_score,
                osd_present=bool(suggestion),
            ),
        )

    def build_detail(self, evaluation: Evaluation) -> EvaluationRead:
        """Enriched detail body shared by GET /{id} and POST /{id}/finalize."""
        read = EvaluationRead.model_validate(evaluation)
        return read.model_copy(
            update={
                "probe_progress": self.get_probe_progress(evaluation.id),
                "probes": self.get_probe_evidence(evaluation.id),
                "confidence_summary": self.get_confidence_summary(evaluation.id),
                "osd_agent": self.get_osd_agent(evaluation.id),
                "final_score": self.get_final_score(evaluation.id),
                "mode_disclosure": self.get_mode_disclosure(evaluation),
                "human_review": self.get_human_review(evaluation.id),
            }
        )

    def finalize_evaluation(self, evaluation: Evaluation) -> Evaluation:
        """Finalize policy (ADR 0011; Phase 18 adds the Assisted write path).

        - Any mode, ``FINALIZED`` with a ``final_scores`` row → idempotent success.
        - ``FAILED`` → 409 FAILED_EVALUATION.
        - Autonomous otherwise → 409 NOT_READY: the pipeline is the sole
          ``final_scores`` writer; no recompute recovery here (re-enqueue instead).
        - Assisted before ``AWAITING_REVIEW`` → 409 NOT_READY; at
          ``AWAITING_REVIEW`` without a ``human_reviews`` row → 409
          REVIEW_REQUIRED; with a review → human-approved O/S/D → FRIES →
          ``final_scores`` (``human_reviewed=true``) → ``FINALIZED``.
        """
        details = {
            "evaluation_id": str(evaluation.id),
            "status": evaluation.status.value,
            "evaluation_mode": evaluation.evaluation_mode.value,
        }
        final_row = self._final_scores.get_for_evaluation(evaluation.id)
        if evaluation.status == EvaluationStatus.FINALIZED:
            return evaluation
        if evaluation.status == EvaluationStatus.FAILED:
            raise AppError(
                "FAILED_EVALUATION",
                "Evaluation failed — there is nothing to finalize; re-run the evaluation",
                status_code=409,
                details=details,
            )
        if evaluation.evaluation_mode == EvaluationMode.AI_AUTONOMOUS:
            raise AppError(
                "NOT_READY",
                "Autonomous evaluations are finalized by the pipeline; final score is "
                "not available yet",
                status_code=409,
                details=details,
            )
        if evaluation.status != EvaluationStatus.AWAITING_REVIEW:
            raise AppError(
                "NOT_READY",
                "Assisted evaluation has not reached AWAITING_REVIEW yet",
                status_code=409,
                details=details,
            )
        review = self._human_reviews.latest_for_evaluation(evaluation.id)
        if review is None:
            raise AppError(
                "REVIEW_REQUIRED",
                "Assisted finalize requires a human review of the agent O/S/D "
                "suggestions first",
                status_code=409,
                details={
                    **details,
                    "next": f"POST /v1/evaluations/{evaluation.id}/human-review",
                    "phase": 18,
                },
            )
        return self._finalize_assisted(evaluation, review, details=details)

    def _finalize_assisted(
        self,
        evaluation: Evaluation,
        review: HumanReview,
        *,
        details: dict[str, str],
    ) -> Evaluation:
        """Phase 18: human-approved O/S/D → FRIES when complete → FINALIZED."""
        approved = ((review.overrides or {}).get("approved_osd") or {}).get("aspects")
        if approved is None:
            raise AppError(
                "REVIEW_REQUIRED",
                "Latest human review has no structured approved O/S/D — submit a "
                "new review",
                status_code=409,
                details={
                    **details,
                    "human_review_id": review.id,
                    "next": f"POST /v1/evaluations/{evaluation.id}/human-review",
                },
            )
        agent_row = self._osd_outputs.latest_for_evaluation(evaluation.id)
        agent_suggestion = (agent_row.ai_suggestion or {}) if agent_row else {}
        finalized_osd = to_finalized_osd_assisted(
            approved,
            human_review_id=review.id,
            human_changed=review.human_changed,
            agent_suggestion=agent_suggestion,
        )
        if finalized_osd.get("scoring_withheld"):
            withheld_transition = self._evals.transition_status(
                evaluation.id,
                expected=EvaluationStatus.AWAITING_REVIEW,
                new=EvaluationStatus.FINALIZED,
            )
            if withheld_transition is not None:
                # scoring_withheld read straight from finalized_osd — already
                # computed by the untouched to_finalized_osd_assisted, never
                # recomputed here.
                self._events.create(
                    evaluation_id=evaluation.id,
                    event_type=EVENT_EVALUATION_FINALIZED,
                    detail={"evaluation_mode": EvaluationMode.AI_ASSISTED.value, "scoring_withheld": True},
                )
            logger.info(
                "evaluation_finalized_assisted_scoring_withheld evaluation_id=%s "
                "human_review_id=%s complete_aspects=%s",
                evaluation.id,
                review.id,
                finalized_osd.get("complete_aspect_count"),
            )
            return self.get_evaluation(evaluation.id)
        result = score_from_finalized_osd(finalized_osd)
        self._final_scores.upsert(
            evaluation_id=evaluation.id,
            fries_score=result.fries_score,
            dimension_scores=result.dimension_scores,
            finalized_osd=finalized_osd,
            overall_confidence=agent_row.ai_confidence if agent_row else None,
            evaluation_mode=EvaluationMode.AI_ASSISTED,
        )
        row = self._evals.transition_status(
            evaluation.id,
            expected=EvaluationStatus.AWAITING_REVIEW,
            new=EvaluationStatus.FINALIZED,
        )
        if row is not None:
            self._events.create(
                evaluation_id=evaluation.id,
                event_type=EVENT_EVALUATION_FINALIZED,
                detail={"evaluation_mode": EvaluationMode.AI_ASSISTED.value, "scoring_withheld": False},
            )
        if row is None:
            row = self.get_evaluation(evaluation.id)
        logger.info(
            "evaluation_finalized_assisted evaluation_id=%s human_review_id=%s "
            "human_changed=%s fries_score=%s",
            evaluation.id,
            review.id,
            review.human_changed,
            result.fries_score,
        )
        return row

    def publish(self, evaluation: Evaluation) -> Evaluation:
        """Opt-in leaderboard publish (Phase 22, ADR 0013).

        Requires ``FINALIZED`` + a ``final_scores`` row; idempotent — an already
        published evaluation keeps its original ``published_at``.
        Pure DB flip: no report generation is triggered (report URIs attach on
        the leaderboard when reports exist). Finalize never auto-publishes.
        """
        if (
            evaluation.status != EvaluationStatus.FINALIZED
            or self._final_scores.get_for_evaluation(evaluation.id) is None
        ):
            raise AppError(
                "NOT_FINALIZED",
                "Only FINALIZED evaluations with a final score can be published — "
                "finalize the evaluation first",
                status_code=409,
                details={
                    "evaluation_id": str(evaluation.id),
                    "status": evaluation.status.value,
                    "evaluation_mode": evaluation.evaluation_mode.value,
                },
            )
        if evaluation.is_published:
            return evaluation
        evaluation.is_published = True
        evaluation.published_at = datetime.now(UTC)
        self._session.flush()
        logger.info("evaluation_published evaluation_id=%s", evaluation.id)
        return evaluation

    def unpublish(self, evaluation: Evaluation) -> Evaluation:
        """Revoke leaderboard publish — idempotent; clears the publish stamp.

        ``published_at`` is cleared rather than kept as history (documented
        choice); republishing restamps it.
        """
        if not evaluation.is_published:
            return evaluation
        evaluation.is_published = False
        evaluation.published_at = None
        self._session.flush()
        logger.info("evaluation_unpublished evaluation_id=%s", evaluation.id)
        return evaluation

    def list_evaluations(
        self,
        *,
        status: EvaluationStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[Evaluation], str | None]:
        rows = self._evals.list_all(status=status, limit=limit, cursor=cursor)
        next_cursor = str(rows[-1].id) if len(rows) == limit and rows else None
        return rows, next_cursor
