"""Leaderboard route (Phase 22, ADR 0013) — opt-in published evaluations only.

Bearer auth is kept for MVP consistency with every other /v1 route ("public"
means published-only visibility, not anonymous access — documented choice).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.enums import EvaluationMode
from app.db.models import User
from app.schemas.common import ErrorResponse
from app.schemas.leaderboard import LeaderboardList
from app.services.leaderboard_service import LeaderboardService

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get(
    "",
    response_model=LeaderboardList,
    summary="Opt-in leaderboard (published + FINALIZED only)",
    description=(
        "Lists only evaluations explicitly published by their owner/admin — "
        "FINALIZED with a final score; private by default. Sorted by fries_score "
        "desc (tie: published_at desc, id desc). Filter by task/dataset/"
        "evaluation_mode for comparable rankings; without a task filter the "
        "response carries a note that entries may not be comparable across "
        "tasks. Entries attach the latest report URIs when a report exists."
    ),
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def get_leaderboard(
    task: str | None = Query(None, description="Exact-match task filter"),
    dataset: str | None = Query(None, description="Exact-match dataset filter"),
    evaluation_mode: EvaluationMode | None = Query(
        None, description="AI_ASSISTED or AI_AUTONOMOUS"
    ),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor (evaluation UUID)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeaderboardList:
    return LeaderboardService(db).list_published(
        task=task,
        dataset=dataset,
        evaluation_mode=evaluation_mode,
        limit=limit,
        cursor=cursor,
    )
