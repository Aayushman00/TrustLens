"""Report routes — canonical JSON + PDF projection (Phase 19, ADR 0009).

RBAC (documented MVP choice): any authenticated user may fetch or force-generate
reports — the same access level as evaluation detail reads; reports expose no
data beyond what those reads already return.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.common import ErrorResponse
from app.schemas.reports import ReportRead
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])

_ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.get(
    "/{evaluation_id}",
    response_model=ReportRead,
    summary="Get evaluation report (canonical JSON + artifact URIs)",
    description=(
        "Latest report_v1 for a FINALIZED evaluation: embedded canonical JSON plus "
        "versioned MinIO URIs (reports/{evaluation_id}/v{n}/report.json and, when "
        "PDF rendering is enabled, report.pdf). Auto-generates version 1 on first "
        "read. Every report is mode-labeled (AI-ASSISTED / AI-AUTONOMOUS) with the "
        "Phase 17/18 disclosure and an original-FRIES score section. "
        "409 NOT_FINALIZED until the evaluation is finalized."
    ),
    responses=_ERROR_RESPONSES,
)
def get_report(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportRead:
    return ReportService(db).get_report(evaluation_id)


@router.post(
    "/{evaluation_id}/generate",
    response_model=ReportRead,
    status_code=201,
    summary="Force-generate a new report version",
    description=(
        "Regenerates the report from current finalized data as version latest+1 "
        "(append-only: new MinIO keys, prior versions untouched). "
        "409 NOT_FINALIZED until the evaluation is finalized."
    ),
    responses=_ERROR_RESPONSES,
)
def generate_report(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportRead:
    return ReportService(db).generate(evaluation_id)
