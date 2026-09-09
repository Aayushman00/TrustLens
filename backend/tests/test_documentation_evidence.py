"""Documentation-as-evidence (Part 1): pinned-revision HF fetch, hashing,
missing/unfetchable cards, user-supplied documentation CRUD + ownership.
"""

from __future__ import annotations

import pytest
from huggingface_hub.utils import EntryNotFoundError

from app.documentation.evidence import (
    RETRIEVAL_ERROR,
    RETRIEVAL_NOT_FOUND,
    RETRIEVAL_OK,
    resolve_hf_documentation_evidence,
)
from app.storage.evidence_store import format_sha256


def test_no_revision_refuses_to_fetch_moving_branch() -> None:
    """Without a pinned revision, this must not silently read the default branch."""
    result = resolve_hf_documentation_evidence("org/model", None)
    assert result.retrieval_status == RETRIEVAL_ERROR
    assert result.documentation_revision is None
    assert result.content is None
    assert "revision" in (result.retrieval_error or "")


def test_successful_pinned_fetch_hashes_content(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Card\nSome documentation text.", encoding="utf-8")
    monkeypatch.setattr(
        "app.documentation.evidence.hf_hub_download",
        lambda **kwargs: str(readme),
    )

    result = resolve_hf_documentation_evidence("org/model", "abc123def", token=None)

    assert result.retrieval_status == RETRIEVAL_OK
    assert result.documentation_revision == "abc123def"
    assert result.source_model_ref == "org/model"
    assert result.source_model_revision == "abc123def"
    assert result.documentation_url == "https://huggingface.co/org/model/blob/abc123def/README.md"
    assert result.content == "# Card\nSome documentation text."
    assert result.documentation_content_hash == format_sha256(result.content.encode("utf-8"))
    assert result.content_length == len(result.content.encode("utf-8"))
    assert result.retrieval_error is None


def test_missing_card_recorded_as_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(**kwargs):
        raise EntryNotFoundError("no README.md")

    monkeypatch.setattr("app.documentation.evidence.hf_hub_download", _raise)

    result = resolve_hf_documentation_evidence("org/no-card", "rev1")
    assert result.retrieval_status == RETRIEVAL_NOT_FOUND
    assert result.content is None
    assert result.documentation_content_hash is None
    assert result.documentation_revision == "rev1"


def test_network_error_recorded_never_fabricated(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(**kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("app.documentation.evidence.hf_hub_download", _raise)

    result = resolve_hf_documentation_evidence("org/model", "rev1")
    assert result.retrieval_status == RETRIEVAL_ERROR
    assert result.content is None
    assert result.documentation_content_hash is None
    assert "connection reset" in (result.retrieval_error or "")


def test_as_metadata_never_leaks_raw_content() -> None:
    from app.documentation.evidence import DocumentationEvidence

    evidence = DocumentationEvidence(
        documentation_source_type="model_card",
        documentation_url="https://huggingface.co/org/model/blob/rev1/README.md",
        documentation_revision="rev1",
        documentation_content_hash="sha256:abc",
        retrieval_status=RETRIEVAL_OK,
        content_length=10,
        source_model_ref="org/model",
        source_model_revision="rev1",
        content="secret card body",
    )
    metadata = evidence.as_metadata()
    assert "content" not in metadata
    assert metadata["documentation_content_hash"] == "sha256:abc"
