"""Hugging Face documentation evidence — pinned to a frozen model revision.

Explainability/Safety Track 1 evaluate model-card *text*; this module is only
concerned with WHERE that text came from and proving it is not silently
drifting off a moving default branch. Every field is either read directly
from the Hub or an explicit status/error string — nothing here is fabricated,
and a missing/unfetchable card is recorded as such rather than skipped
silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from huggingface_hub import hf_hub_download
from huggingface_hub.utils import EntryNotFoundError

from app.storage.evidence_store import format_sha256

_README_FILENAME = "README.md"
DOCUMENTATION_SOURCE_TYPE_MODEL_CARD = "model_card"

RETRIEVAL_OK = "ok"
RETRIEVAL_NOT_FOUND = "not_found"
RETRIEVAL_ERROR = "error"


@dataclass(frozen=True)
class DocumentationEvidence:
    """Pinned-revision documentation fetch result — never the live default branch."""

    documentation_source_type: str
    documentation_url: str | None
    documentation_revision: str | None
    documentation_content_hash: str | None
    retrieval_status: str
    content_length: int | None
    source_model_ref: str
    source_model_revision: str | None
    retrieval_error: str | None = None
    content: str | None = None

    def as_metadata(self) -> dict[str, object]:
        """JSON-safe dict without the raw content (for model_metadata/API)."""
        return {
            "documentation_source_type": self.documentation_source_type,
            "documentation_url": self.documentation_url,
            "documentation_revision": self.documentation_revision,
            "documentation_content_hash": self.documentation_content_hash,
            "retrieval_status": self.retrieval_status,
            "retrieval_error": self.retrieval_error,
            "content_length": self.content_length,
            "source_model_ref": self.source_model_ref,
            "source_model_revision": self.source_model_revision,
        }


def resolve_hf_documentation_evidence(
    repo_id: str,
    revision: str | None,
    *,
    token: str | None = None,
) -> DocumentationEvidence:
    """Fetch ``README.md`` pinned to ``revision`` — refuses to fetch a moving branch.

    Without a resolved revision there is nothing to pin to, so this returns an
    explicit ``error`` status rather than silently falling back to whatever
    the Hub currently serves as the default branch.
    """
    if not revision:
        return DocumentationEvidence(
            documentation_source_type=DOCUMENTATION_SOURCE_TYPE_MODEL_CARD,
            documentation_url=f"https://huggingface.co/{repo_id}",
            documentation_revision=None,
            documentation_content_hash=None,
            retrieval_status=RETRIEVAL_ERROR,
            content_length=None,
            source_model_ref=repo_id,
            source_model_revision=None,
            retrieval_error="no resolved model revision to pin documentation to",
        )

    url = f"https://huggingface.co/{repo_id}/blob/{revision}/{_README_FILENAME}"
    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=_README_FILENAME,
            revision=revision,
            token=token,
        )
    except EntryNotFoundError:
        return DocumentationEvidence(
            documentation_source_type=DOCUMENTATION_SOURCE_TYPE_MODEL_CARD,
            documentation_url=url,
            documentation_revision=revision,
            documentation_content_hash=None,
            retrieval_status=RETRIEVAL_NOT_FOUND,
            content_length=None,
            source_model_ref=repo_id,
            source_model_revision=revision,
        )
    except Exception as exc:  # noqa: BLE001 — record as evidence, never crash import
        return DocumentationEvidence(
            documentation_source_type=DOCUMENTATION_SOURCE_TYPE_MODEL_CARD,
            documentation_url=url,
            documentation_revision=revision,
            documentation_content_hash=None,
            retrieval_status=RETRIEVAL_ERROR,
            content_length=None,
            source_model_ref=repo_id,
            source_model_revision=revision,
            retrieval_error=str(exc),
        )

    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    content_bytes = text.encode("utf-8")
    return DocumentationEvidence(
        documentation_source_type=DOCUMENTATION_SOURCE_TYPE_MODEL_CARD,
        documentation_url=url,
        documentation_revision=revision,
        documentation_content_hash=format_sha256(content_bytes),
        retrieval_status=RETRIEVAL_OK,
        content_length=len(content_bytes),
        source_model_ref=repo_id,
        source_model_revision=revision,
        content=text,
    )


__all__ = ["DocumentationEvidence", "resolve_hf_documentation_evidence"]
