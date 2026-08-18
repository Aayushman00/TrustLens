"""Leaderboard schemas (Phase 22, ADR 0013) — published-only, context-labeled.

Every entry retains its comparability context (task/dataset/config/revision/
version) and its mode + human-review provenance; FRIES scores are never a
universal cross-task trust ranking.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.db.enums import EvaluationMode
from app.schemas.common import CursorPage

NON_COMPARABLE_NOTE = (
    "Entries may span multiple tasks/datasets and are not directly comparable — "
    "filter by task (and dataset) for a comparable ranking. FRIES scores do not "
    "form a universal cross-task trust ranking."
)


class LeaderboardReportRef(BaseModel):
    """Latest report artifact URIs for an entry (Phase 19), when generated."""

    version: int
    json_uri: str | None = None
    pdf_uri: str | None = None


class LeaderboardEntry(BaseModel):
    evaluation_id: uuid.UUID
    model_id: int
    hf_repo_id: str
    model_revision: str | None = None
    evaluation_mode: EvaluationMode
    human_reviewed: bool
    task: str | None = None
    dataset: str | None = None
    config: str | None = None
    trustlens_version: str | None = None
    fries_score: float
    overall_confidence: float | None = None
    published_at: datetime | None = None
    report: LeaderboardReportRef | None = None


class LeaderboardList(CursorPage):
    items: list[LeaderboardEntry]
    # Set when the task filter is omitted — entries may not be comparable.
    note: str | None = None
