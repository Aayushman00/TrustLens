"""Schemas for POST /v1/dataset-fetches and GET /v1/dataset-contents/{id}."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetFetchRequest(BaseModel):
    source_url: str = Field(..., min_length=1, max_length=2048)


class DatasetContentRead(BaseModel):
    id: uuid.UUID
    content_hash: str
    byte_size: int
    format: str
    row_count: int
    columns: list[dict[str, Any]]
    created_at: datetime
