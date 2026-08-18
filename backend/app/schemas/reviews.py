"""Human review request/response schemas (Phase 18) — structured accept/edit.

Reviews are structured O/S/D overrides, never free-form-only. Humans may set
the extremes the heuristic agent never proposes: 0 (veto) and 10 (optimal).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.db.enums import FriesDimension


class AspectOSDEdit(BaseModel):
    aspect: FriesDimension
    O: int = Field(ge=0, le=10)
    S: int = Field(ge=0, le=10)
    D: int = Field(ge=0, le=10)


class HumanReviewRequest(BaseModel):
    accept_all: bool = False
    # accept_all=false: partial or full overrides; missing aspects keep agent values.
    aspects: list[AspectOSDEdit] | None = None
    notes: str | None = None
    review_rationale: str | None = None

    @model_validator(mode="after")
    def _validate_aspects(self) -> HumanReviewRequest:
        if self.accept_all and self.aspects:
            raise ValueError("accept_all=true takes the agent suggestion as-is — omit 'aspects'")
        if not self.accept_all and not self.aspects:
            raise ValueError("accept_all=false requires at least one aspect edit")
        if self.aspects:
            names = [edit.aspect for edit in self.aspects]
            if len(names) != len(set(names)):
                raise ValueError("duplicate aspect in edits")
        return self


class HumanReviewRead(BaseModel):
    id: int
    evaluation_id: uuid.UUID
    reviewer_id: int
    human_changed: bool
    accept_all: bool
    approved_osd: dict[str, Any]
    review_rationale: str | None = None
    notes: str | None = None
    created_at: datetime
