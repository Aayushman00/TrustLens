"""/v1 API router aggregate."""

from __future__ import annotations

from fastapi import APIRouter

from app.routers.v1 import (
    auth,
    evaluation_actions,
    evaluations,
    import_hf,
    leaderboard,
    models,
    reports,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth.router)
api_router.include_router(models.router)
api_router.include_router(import_hf.router)
api_router.include_router(evaluations.router)
api_router.include_router(evaluation_actions.router)
api_router.include_router(reports.router)
api_router.include_router(leaderboard.router)
