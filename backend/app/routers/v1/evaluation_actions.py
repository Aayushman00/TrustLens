"""Evaluation lifecycle routes — human-review + finalize (17/18), publish (22).

Local single-user instance — no auth/RBAC. Human review and the Assisted
finalize write path are live (Phase 18); publish/unpublish flip the opt-in
leaderboard visibility flag (Phase 22, ADR 0013).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ErrorResponse
from app.schemas.evaluations import EvaluationRead
from app.schemas.reviews import HumanReviewRead, HumanReviewRequest
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluations", tags=["evaluations-lifecycle"])


@router.post(
    "/{evaluation_id}/human-review",
    response_model=HumanReviewRead,
    status_code=201,
    summary="Submit human review (accept/edit agent O/S/D)",
    description=(
        "AI-Assisted only, at AWAITING_REVIEW. Structured accept/edit of the "
        "agent's PROPOSED O/S/D: accept_all=true takes the suggestion as-is; "
        "otherwise per-aspect edits override and missing aspects keep agent "
        "values (humans may set 0=veto or 10=optimal). Each POST appends a "
        "review row; finalize uses the latest. 409 ASSISTED_ONLY on Autonomous, "
        "ALREADY_FINALIZED after finalize, NOT_READY before AWAITING_REVIEW."
    ),
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def submit_human_review(
    evaluation_id: uuid.UUID,
    body: HumanReviewRequest,
    db: Session = Depends(get_db),
) -> HumanReviewRead:
    return EvaluationService(db).submit_human_review(evaluation_id, body)


@router.post(
    "/{evaluation_id}/finalize",
    response_model=EvaluationRead,
    summary="Finalize evaluation (dual-mode policy)",
    description=(
        "Dual-mode policy (ADR 0011). AI_AUTONOMOUS: pipeline-finalized — returns the "
        "existing result idempotently; 409 NOT_READY while running, 409 FAILED_EVALUATION "
        "after failure. AI_ASSISTED: 409 REVIEW_REQUIRED until a human review exists; "
        "with one, the human-approved O/S/D is scored with FRIES and persisted "
        "(human_reviewed=true) and the evaluation becomes FINALIZED."
    ),
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def finalize_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    service = EvaluationService(db)
    evaluation = service.get_evaluation(evaluation_id)
    finalized = service.finalize_evaluation(evaluation)
    return service.build_detail(finalized)


@router.post(
    "/{evaluation_id}/publish",
    response_model=EvaluationRead,
    summary="Publish to leaderboard (opt-in)",
    description=(
        "Opt-in leaderboard publish (ADR 0013). Requires FINALIZED with a final "
        "score → else 409 NOT_FINALIZED. Idempotent: already published returns "
        "200 with the current state. Evaluations are never auto-published on "
        "finalize; default is private."
    ),
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def publish_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    service = EvaluationService(db)
    evaluation = service.get_evaluation(evaluation_id)
    return service.build_detail(service.publish(evaluation))


@router.post(
    "/{evaluation_id}/unpublish",
    response_model=EvaluationRead,
    summary="Unpublish from leaderboard",
    description=(
        "Revoke leaderboard publish. Idempotent: already private returns 200. "
        "Clears published_at (republish restamps)."
    ),
    responses={
        404: {"model": ErrorResponse},
    },
)
def unpublish_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    service = EvaluationService(db)
    evaluation = service.get_evaluation(evaluation_id)
    return service.build_detail(service.unpublish(evaluation))
