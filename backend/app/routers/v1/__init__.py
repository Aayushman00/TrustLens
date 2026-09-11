"""/v1 API router aggregate."""

from __future__ import annotations

from fastapi import APIRouter

from app.routers.v1 import (
    dataset_content,
    documentation,
    evaluation_actions,
    evaluation_drafts,
    evaluations,
    import_hf,
    models,
    reports,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(models.router)
api_router.include_router(import_hf.router)
api_router.include_router(documentation.router)
api_router.include_router(dataset_content.router)
api_router.include_router(dataset_content.content_router)
api_router.include_router(evaluations.router)
api_router.include_router(evaluation_actions.router)
api_router.include_router(evaluation_drafts.router)
api_router.include_router(reports.router)
