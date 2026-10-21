"""Shared Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class CursorPage(BaseModel):
    """Cursor pagination stub (ADR 0007) — next_cursor is opaque string | None."""

    next_cursor: str | None = None
