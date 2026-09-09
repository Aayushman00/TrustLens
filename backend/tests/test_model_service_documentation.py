"""ModelService.import_from_hf persists/refreshes the auto-fetched HF documentation_sources row."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.adapters.base import NormalizedModelRecord
from app.db.repositories.documentation import DocumentationSourceRepository
from app.schemas.models import ImportHfRequest
from app.services.model_service import ModelService


class _FakeAdapter:
    def __init__(self, record: NormalizedModelRecord) -> None:
        self._record = record

    def resolve(self, ref: str, revision: str | None = None) -> NormalizedModelRecord:
        return self._record


def _record(hf_repo_id: str, *, revision: str, retrieval_status: str = "ok") -> NormalizedModelRecord:
    return NormalizedModelRecord(
        hf_repo_id=hf_repo_id,
        revision=revision,
        checksum=revision,
        model_metadata={
            "source": "huggingface_hub",
            "card_text": "# Card" if retrieval_status == "ok" else None,
            "documentation_evidence": {
                "documentation_source_type": "model_card",
                "documentation_url": f"https://huggingface.co/{hf_repo_id}/blob/{revision}/README.md",
                "documentation_revision": revision,
                "documentation_content_hash": "sha256:abc" if retrieval_status == "ok" else None,
                "retrieval_status": retrieval_status,
                "retrieval_error": None if retrieval_status == "ok" else "not found",
                "content_length": 6 if retrieval_status == "ok" else None,
                "source_model_ref": hf_repo_id,
                "source_model_revision": revision,
            },
        },
    )


def test_import_persists_documentation_source(db_session: Session) -> None:
    hf_repo_id = "org/doc-model"
    service = ModelService(db_session, hf_adapter=_FakeAdapter(_record(hf_repo_id, revision="rev1")))
    model = service.import_from_hf(ImportHfRequest(repo_id=hf_repo_id))

    rows = DocumentationSourceRepository(db_session).list_for_model(model.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.source_kind == "huggingface_hub"
    assert row.documentation_revision == "rev1"
    assert row.retrieval_status == "ok"
    assert row.documentation_content_hash == "sha256:abc"
    assert row.source_model_ref == hf_repo_id


def test_reimport_refreshes_documentation_source_without_duplicating(db_session: Session) -> None:
    hf_repo_id = "org/doc-model-2"
    service = ModelService(db_session, hf_adapter=_FakeAdapter(_record(hf_repo_id, revision="rev1")))
    model = service.import_from_hf(ImportHfRequest(repo_id=hf_repo_id))

    service2 = ModelService(db_session, hf_adapter=_FakeAdapter(_record(hf_repo_id, revision="rev2")))
    service2.import_from_hf(ImportHfRequest(repo_id=hf_repo_id))

    rows = DocumentationSourceRepository(db_session).list_for_model(model.id)
    assert len(rows) == 1, "re-import must replace, not accumulate, the auto-fetched row"
    assert rows[0].documentation_revision == "rev2"


def test_missing_card_recorded_as_not_found_never_fabricated(db_session: Session) -> None:
    hf_repo_id = "org/no-card-model"
    service = ModelService(
        db_session,
        hf_adapter=_FakeAdapter(_record(hf_repo_id, revision="rev1", retrieval_status="not_found")),
    )
    model = service.import_from_hf(ImportHfRequest(repo_id=hf_repo_id))

    rows = DocumentationSourceRepository(db_session).list_for_model(model.id)
    assert len(rows) == 1
    assert rows[0].retrieval_status == "not_found"
    assert rows[0].documentation_content_hash is None
