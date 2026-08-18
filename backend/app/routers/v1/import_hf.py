"""HF import — Phase 6 (ADR 0012). Distinct from POST /v1/models manual create.

Resolves a user-provided HF repo id/URL to metadata only (never weights) via
the Model Adapter boundary (``app.adapters``) and upserts the models registry.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.common import ErrorResponse
from app.schemas.models import ImportHfRequest, ModelRead
from app.services.model_service import ModelService

router = APIRouter(prefix="/models", tags=["models-import"])
logger = logging.getLogger("trustlens.api")


@router.post(
    "/import-hf",
    response_model=ModelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Import model metadata from Hugging Face Hub",
    description=(
        "Resolve a user-provided HF repo id or URL via the Hub metadata API "
        "(model info, file list, model card) and upsert the models registry. "
        "Never downloads model weights. Re-importing an existing hf_repo_id "
        "refreshes its metadata/revision/checksum. Distinct from POST /v1/models "
        "(manual create)."
    ),
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse, "description": "Gated model without HF_TOKEN access"},
        404: {"model": ErrorResponse, "description": "Repo/revision not found on the Hub"},
        422: {"model": ErrorResponse, "description": "Invalid/non-HF reference"},
        502: {"model": ErrorResponse, "description": "Hugging Face Hub unavailable"},
    },
)
def import_hf(
    body: ImportHfRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ModelRead:
    row = ModelService(db).import_from_hf(body)
    logger.info(
        "hf_import_completed hf_repo_id=%s model_id=%s requested_by=%s",
        row.hf_repo_id,
        row.id,
        current_user.email,
    )
    return ModelRead.model_validate(row)
