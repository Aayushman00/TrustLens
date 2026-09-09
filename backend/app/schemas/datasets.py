"""User-defined local Fairness dataset schemas (upload / columns / group discovery)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserDatasetColumn(BaseModel):
    name: str
    inferred_type: Literal["numeric", "categorical", "unknown"]


class UserDatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    format: str
    content_hash: str
    row_count: int
    size_bytes: int
    columns: list[UserDatasetColumn]
    status: str
    status_reason: str | None = None
    created_at: datetime


class UserDatasetList(BaseModel):
    items: list[UserDatasetRead]


class ObservedGroup(BaseModel):
    value: str
    count: int


class GroupDiscoveryRead(BaseModel):
    group_column: str
    total_rows: int
    observed_groups: list[ObservedGroup]
    missing_count: int
    missing_reasons: dict[str, int]
