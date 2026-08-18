"""Shared Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class TimestampRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime


class CursorPage(BaseModel):
    """Cursor pagination stub (ADR 0007) — next_cursor is opaque string | None."""

    next_cursor: str | None = None
