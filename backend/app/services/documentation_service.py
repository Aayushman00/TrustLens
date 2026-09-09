"""Documentation source service — list model documentation evidence + user-supplied add/delete."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.errors import ForbiddenError, NotFoundError
from app.db.models import DocumentationSource
from app.db.repositories.documentation import DocumentationSourceRepository
from app.db.repositories.model import ModelRepository
from app.schemas.documentation import UserDocumentationCreate

_NOT_APPLICABLE = "not_applicable"


class DocumentationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = DocumentationSourceRepository(session)
        self._models = ModelRepository(session)

    def list_for_model(self, model_id: int) -> list[DocumentationSource]:
        model = self._models.get_by_id(model_id)
        if model is None:
            raise NotFoundError(f"Model {model_id} not found", details={"model_id": model_id})
        return self._repo.list_for_model(model_id)

    def add_user_documentation(
        self,
        *,
        model_id: int,
        data: UserDocumentationCreate,
    ) -> DocumentationSource:
        model = self._models.get_by_id(model_id)
        if model is None:
            raise NotFoundError(f"Model {model_id} not found", details={"model_id": model_id})
        # Never fetched/hashed server-side — no SSRF guard exists for
        # arbitrary user-supplied URLs (unlike the allowlisted HF Hub host).
        return self._repo.create(
            model_id=model_id,
            source_kind="user_supplied",
            documentation_type=data.documentation_type,
            retrieval_status=_NOT_APPLICABLE,
            source_model_ref=model.hf_repo_id,
            url=data.url,
            title=data.title,
            description=data.description,
            source_model_revision=model.revision,
        )

    def delete_user_documentation(
        self,
        *,
        model_id: int,
        source_id: int,
    ) -> None:
        row = self._repo.get_by_id(source_id)
        if row is None or row.model_id != model_id:
            raise NotFoundError(
                f"Documentation source {source_id} not found",
                details={"model_id": model_id, "source_id": source_id},
            )
        if row.source_kind != "user_supplied":
            raise ForbiddenError(
                "auto-recorded Hugging Face documentation evidence cannot be deleted directly"
                " — it is refreshed on re-import"
            )
        self._session.delete(row)
        self._session.flush()
