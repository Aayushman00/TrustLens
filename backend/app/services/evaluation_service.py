"""Evaluation service — create/enqueue, enriched reads, review + finalize (Phase 7–18)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.errors import AppError, NotFoundError, ValidationAppError
from app.confidence.engine import ConfidenceSummary, summarize
from app.datasets.registry import validate_probe_config_datasets
from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation, HumanReview, User
from app.db.repositories.evaluation import EvaluationRepository
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
    ProbeProgress,
)
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import (
    METHODOLOGY_STATUS_PROPOSED,
    ModeDisclosure,
    build_mode_disclosure,
    disclaimer_for,
)
from app.schemas.probe_config import parse_probe_config
from app.schemas.reviews import HumanReviewRead, HumanReviewRequest
from app.scoring.fries import score_from_finalized_osd
from app.tasks.celery_client import enqueue_evaluate_model

logger = logging.getLogger("trustlens.api")

FRIES_PROBE_TOTAL = 5


class EvaluationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._evals = EvaluationRepository(session)
        self._models = ModelRepository(session)
        self._probes = ProbeResultRepository(session)
        self._osd_outputs = OsdAgentOutputRepository(session)
        self._final_scores = FinalScoreRepository(session)
        self._human_reviews = HumanReviewRepository(session)

    def create_evaluation(
        self,
        data: EvaluationCreate,
        *,
        created_by: int | None = None,
    ) -> Evaluation:
        model = self._models.get_by_id(data.model_id)
        if model is None:
            raise NotFoundError(
                f"Model {data.model_id} not found",
                details={"model_id": data.model_id},
            )
        try:
            probe_cfg = parse_probe_config(data.probe_config)
            validate_probe_config_datasets(probe_cfg)
        except ValidationError as exc:
            raise ValidationAppError(
                "Invalid probe_config",
                details={"errors": exc.errors()},
            ) from exc
        except ValueError as exc:
            raise ValidationAppError(
                str(exc),
                details={"probe_config": data.probe_config},
            ) from exc
        probe_config = probe_cfg.model_dump(mode="json")
        row = self._evals.create(
            model_id=data.model_id,
            evaluation_mode=data.evaluation_mode,
            status=EvaluationStatus.PENDING,
            probe_config=probe_config,
            task=data.task,
            dataset=data.dataset,
            config=data.config,
            model_revision=data.model_revision,
            trustlens_version=data.trustlens_version,
            created_by=created_by,
        )
        payload = EvaluateModelPayload(
            evaluation_id=row.id,
            model_ref=model.hf_repo_id,
            evaluation_mode=row.evaluation_mode,
            probe_config=row.probe_config or {},
        )
        task_id = enqueue_evaluate_model(payload)
        logger.info(
            "evaluation_created evaluation_id=%s model_ref=%s enqueue_task_id=%s",
            row.id,
            model.hf_repo_id,
            task_id,
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

    def get_confidence_summary(self, evaluation_id: uuid.UUID) -> ConfidenceSummary | None:
        """Phase 15: aggregate persisted probe confidences; None until ≥1 probe row."""
        rows = self._probes.list_for_evaluation(evaluation_id)
        if not rows:
            return None
        return summarize(
            [(row.dimension, row.confidence, row.metric_values or {}) for row in rows]
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
            reviewer_id=row.reviewer_id,
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
        *,
        reviewer: User,
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
        edits = [edit.model_dump(mode="json") for edit in body.aspects or []]
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
            reviewer_id=reviewer.id,
            overrides=overrides,
            human_changed=human_changed,
            notes=body.notes,
        )
        logger.info(
            "human_review_created evaluation_id=%s review_id=%s reviewer_id=%s "
            "accept_all=%s human_changed=%s",
            evaluation.id,
            row.id,
            reviewer.id,
            body.accept_all,
            human_changed,
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
            row.evaluation_mode, human_reviewed=human_reviewed
        )
        read = FinalScoreRead.model_validate(row)
        return read.model_copy(
            update={"human_reviewed": human_reviewed, "disclaimer": disclaimer}
        )

    def get_mode_disclosure(self, evaluation: Evaluation) -> ModeDisclosure:
        """Phase 17: always present on detail reads; derived from mode + score + agent."""
        final_row = self._final_scores.get_for_evaluation(evaluation.id)
        human_reviewed = (
            bool((final_row.finalized_osd or {}).get("human_reviewed", False))
            if final_row is not None
            else False
        )
        osd_row = self._osd_outputs.latest_for_evaluation(evaluation.id)
        methodology_status = str(
            ((osd_row.ai_suggestion or {}) if osd_row else {}).get(
                "methodology_status", METHODOLOGY_STATUS_PROPOSED
            )
        )
        return build_mode_disclosure(
            evaluation_mode=evaluation.evaluation_mode,
            human_reviewed=human_reviewed,
            methodology_status=methodology_status,
        )

    def build_detail(self, evaluation: Evaluation) -> EvaluationRead:
        """Enriched detail body shared by GET /{id} and POST /{id}/finalize."""
        read = EvaluationRead.model_validate(evaluation)
        return read.model_copy(
            update={
                "probe_progress": self.get_probe_progress(evaluation.id),
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
        if evaluation.status == EvaluationStatus.FINALIZED and final_row is not None:
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
        """Phase 18: human-approved O/S/D → FRIES → final_scores → FINALIZED."""
        approved = ((review.overrides or {}).get("approved_osd") or {}).get("aspects")
        if not approved:
            # Legacy/malformed review row (pre-Phase-18 shape) — a new structured
            # review is the remedy, so surface the same code as "no review yet".
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
        finalized_osd = to_finalized_osd_assisted(
            approved,
            human_review_id=review.id,
            reviewer_id=review.reviewer_id,
            human_changed=review.human_changed,
        )
        result = score_from_finalized_osd(finalized_osd)
        agent_row = self._osd_outputs.latest_for_evaluation(evaluation.id)
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
        if row is None:
            # Race: another finalize won between our status check and the
            # transition — re-read; FINALIZED + score row is the idempotent result.
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

    def publish(self, evaluation: Evaluation, *, user: User) -> Evaluation:
        """Opt-in leaderboard publish (Phase 22, ADR 0013) — owner/admin via router dep.

        Requires ``FINALIZED`` + a ``final_scores`` row; idempotent — an already
        published evaluation keeps its original ``published_at``/``published_by``.
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
        evaluation.published_by = user.id
        self._session.flush()
        logger.info(
            "evaluation_published evaluation_id=%s published_by=%s",
            evaluation.id,
            user.id,
        )
        return evaluation

    def unpublish(self, evaluation: Evaluation) -> Evaluation:
        """Revoke leaderboard publish — idempotent; clears the publish stamp.

        ``published_at``/``published_by`` are cleared rather than kept as
        history (documented choice); republishing restamps both.
        """
        if not evaluation.is_published:
            return evaluation
        evaluation.is_published = False
        evaluation.published_at = None
        evaluation.published_by = None
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

    def update_status(self, evaluation_id: uuid.UUID, status: EvaluationStatus) -> Evaluation:
        """Repo wrapper — raw status write (prefer transition_status in the worker)."""
        row = self._evals.update_status(evaluation_id, status)
        if row is None:
            raise NotFoundError(
                f"Evaluation {evaluation_id} not found",
                details={"evaluation_id": str(evaluation_id)},
            )
        return row
