"""Documentation source schemas (Part 1 — documentation as first-class evidence)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentationType = Literal[
    "model_card",
    "readme",
    "technical_report",
    "safety_system_card",
    "evaluation_report",
    "research_paper",
    "other",
]


class UserDocumentationCreate(BaseModel):
    """A user-supplied documentation pointer — never fetched/hashed server-side.

    Unlike the auto-recorded Hugging Face card, TrustLens does not crawl or
    hash arbitrary user-supplied URLs (no SSRF guard exists for open URLs) —
    it records the pointer as declared evidence, with ``retrieval_status``
    fixed to ``"not_applicable"``, and lets a human follow the link.
    """

    url: str
    documentation_type: DocumentationType
    title: str | None = None
    description: str | None = None


class DocumentationSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    source_kind: Literal["huggingface_hub", "user_supplied"]
    documentation_type: str
    url: str | None = None
    title: str | None = None
    description: str | None = None
    documentation_revision: str | None = None
    documentation_content_hash: str | None = None
    retrieval_status: str
    retrieval_error: str | None = None
    content_length: int | None = None
    source_model_ref: str
    source_model_revision: str | None = None
    created_by: int | None = None
    created_at: datetime


class DocumentationSourceList(BaseModel):
    items: list[DocumentationSourceRead] = Field(default_factory=list)
