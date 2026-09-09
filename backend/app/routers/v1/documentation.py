"""Documentation evidence routes (Part 1 — documentation as first-class evidence).

Lists the auto-recorded (pinned-revision) Hugging Face card evidence plus any
user-supplied documentation pointers for a model, and lets any authenticated
user attach/remove their own user-supplied entries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.common import ErrorResponse
from app.schemas.documentation import (
    DocumentationSourceList,
    DocumentationSourceRead,
    UserDocumentationCreate,
)
from app.services.documentation_service import DocumentationService

router = APIRouter(prefix="/models/{model_id}/documentation", tags=["documentation"])


@router.get(
    "",
    response_model=DocumentationSourceList,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def list_documentation(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentationSourceList:
    rows = DocumentationService(db).list_for_model(model_id)
    return DocumentationSourceList(items=[DocumentationSourceRead.model_validate(r) for r in rows])


@router.post(
    "",
    response_model=DocumentationSourceRead,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def add_user_documentation(
    model_id: int,
    body: UserDocumentationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentationSourceRead:
    row = DocumentationService(db).add_user_documentation(
        model_id=model_id,
        data=body,
        created_by=current_user.id,
    )
    return DocumentationSourceRead.model_validate(row)


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def delete_user_documentation(
    model_id: int,
    source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    DocumentationService(db).delete_user_documentation(
        model_id=model_id,
        source_id=source_id,
        current_user=current_user,
    )
