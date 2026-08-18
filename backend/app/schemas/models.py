"""Model request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import CursorPage


class ModelCreate(BaseModel):
    hf_repo_id: str = Field(..., min_length=1, max_length=256)
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None
    revision: str | None = None


class ImportHfRequest(BaseModel):
    """Body for POST /v1/models/import-hf — provide exactly one of repo_id/url."""

    repo_id: str | None = Field(None, description="HF repo id, e.g. distilbert-base-uncased")
    url: str | None = Field(None, description="HF model URL (alternative to repo_id)")
    revision: str | None = Field(None, description="Optional branch/tag/commit pin")

    @model_validator(mode="after")
    def _exactly_one_ref(self) -> ImportHfRequest:
        if bool(self.repo_id) == bool(self.url):
            raise ValueError("Provide exactly one of 'repo_id' or 'url'")
        return self


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hf_repo_id: str
    model_metadata: dict[str, Any]
    checksum: str | None = None
    revision: str | None = None
    created_at: datetime
    # models table has created_at only (Phase 3); optional for schema stability
    updated_at: datetime | None = None


class ModelList(CursorPage):
    items: list[ModelRead]
