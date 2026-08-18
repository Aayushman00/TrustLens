"""Unit tests for the Hugging Face Hub model adapter — fully mocked, no network."""

from __future__ import annotations

import httpx
import pytest
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError, RevisionNotFoundError

from app.adapters.base import HfAuthRequiredError, ModelNotFoundError, NormalizedModelRecord
from app.adapters.hf_hub import HfHubModelAdapter, parse_hf_ref
from app.api.errors import AppError


def _hub_error(cls: type[Exception], message: str, *, status_code: int = 404) -> Exception:
    """Build a huggingface_hub error across SDK majors.

    hub 0.x accepts a bare message; hub 1.x (httpx-based) requires the
    ``response`` argument. Try the old signature first, then fall back.
    """
    try:
        return cls(message)
    except TypeError:
        response = httpx.Response(
            status_code,
            request=httpx.Request("GET", "https://huggingface.co/api/models/test"),
        )
        return cls(message, response=response)


def test_parse_bare_repo_id() -> None:
    assert parse_hf_ref("distilbert-base-uncased", None) == ("distilbert-base-uncased", None)


def test_parse_org_slash_model_repo_id() -> None:
    assert parse_hf_ref("org/model-name", None) == ("org/model-name", None)


def test_parse_bare_hf_url() -> None:
    assert parse_hf_ref(None, "https://huggingface.co/bert-base-uncased") == (
        "bert-base-uncased",
        None,
    )


def test_parse_org_url_with_tree_revision() -> None:
    ref, revision = parse_hf_ref(None, "https://huggingface.co/org/model/tree/main")
    assert ref == "org/model"
    assert revision == "main"


def test_parse_url_with_www_host_allowed() -> None:
    ref, revision = parse_hf_ref(None, "https://www.huggingface.co/org/model")
    assert ref == "org/model"
    assert revision is None


def test_parse_non_hf_url_rejected_422() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_hf_ref(None, "https://evil.com/model")
    assert exc_info.value.code == "INVALID_MODEL_REF"
    assert exc_info.value.status_code == 422


def test_parse_empty_repo_id_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_hf_ref("", None)
    assert exc_info.value.code == "INVALID_MODEL_REF"


def test_parse_malformed_repo_id_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_hf_ref("org/sub/model", None)
    assert exc_info.value.code == "INVALID_MODEL_REF"


class _FakeModelInfo:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeHfApi:
    """Stand-in for huggingface_hub.HfApi — no network calls."""

    def __init__(
        self,
        *,
        model_info_result: object = None,
        model_info_error: Exception | None = None,
        files: list[str] | None = None,
    ) -> None:
        self._model_info_result = model_info_result
        self._model_info_error = model_info_error
        self._files = files or []

    def model_info(self, repo_id: str, *, revision: str | None = None, token: object = None) -> object:
        if self._model_info_error:
            raise self._model_info_error
        return self._model_info_result

    def list_repo_files(
        self,
        repo_id: str,
        *,
        revision: str | None = None,
        token: object = None,
    ) -> list[str]:
        return self._files


class _FakeModelCard:
    def __init__(self, text: str | None) -> None:
        self.text = text

    @staticmethod
    def load(repo_id: str, *, token: object = None) -> _FakeModelCard:
        return _FakeModelCard("# Model Card\nSome text.")


def _install_fake_api(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> _FakeHfApi:
    fake_api = _FakeHfApi(**kwargs)
    monkeypatch.setattr("app.adapters.hf_hub.HfApi", lambda token=None: fake_api)
    return fake_api


def test_resolve_returns_normalized_record_with_card_and_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = _FakeModelInfo(
        sha="abc123",
        pipeline_tag="text-classification",
        tags=["pytorch", "bert"],
        library_name="transformers",
        card_data={"license": "apache-2.0"},
        config={"architectures": ["DistilBertForSequenceClassification"]},
        transformers_info={"auto_model": "AutoModel"},
    )
    _install_fake_api(monkeypatch, model_info_result=info, files=["config.json", "pytorch_model.bin"])
    monkeypatch.setattr("app.adapters.hf_hub.ModelCard", _FakeModelCard)

    adapter = HfHubModelAdapter()
    record = adapter.resolve("distilbert-base-uncased")

    assert isinstance(record, NormalizedModelRecord)
    assert record.hf_repo_id == "distilbert-base-uncased"
    assert record.revision == "abc123"
    assert record.checksum == "abc123"

    metadata = record.model_metadata
    assert metadata["source"] == "huggingface_hub"
    assert metadata["architecture"] == "DistilBertForSequenceClassification"
    assert metadata["pipeline_tag"] == "text-classification"
    assert metadata["task"] == "text-classification"
    assert metadata["license"] == "apache-2.0"
    assert metadata["tags"] == ["pytorch", "bert"]
    assert metadata["files"] == ["config.json", "pytorch_model.bin"]
    assert metadata["library_name"] == "transformers"
    assert metadata["card_text"] == "# Model Card\nSome text."
    assert metadata["card_data"] == {"license": "apache-2.0"}
    assert metadata["transformers_info"] == {"auto_model": "AutoModel"}
    assert metadata["hub_url"] == "https://huggingface.co/distilbert-base-uncased"


def test_resolve_repo_not_found_raises_model_not_found_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_api(
        monkeypatch, model_info_error=_hub_error(RepositoryNotFoundError, "not found")
    )
    adapter = HfHubModelAdapter()
    with pytest.raises(ModelNotFoundError) as exc_info:
        adapter.resolve("nobody/does-not-exist")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "MODEL_NOT_FOUND"


def test_resolve_revision_not_found_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_api(
        monkeypatch, model_info_error=_hub_error(RevisionNotFoundError, "bad revision")
    )
    adapter = HfHubModelAdapter()
    with pytest.raises(ModelNotFoundError):
        adapter.resolve("org/model", revision="nonexistent")


def test_resolve_gated_repo_raises_hf_auth_required_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_api(
        monkeypatch, model_info_error=_hub_error(GatedRepoError, "gated", status_code=403)
    )
    adapter = HfHubModelAdapter()
    with pytest.raises(HfAuthRequiredError) as exc_info:
        adapter.resolve("org/gated-model")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "HF_AUTH_REQUIRED"


def test_resolve_never_calls_download_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0012 — metadata only. Asserts no weight-download method exists on the fake API,
    guaranteeing the adapter can't accidentally rely on one."""
    info = _FakeModelInfo(sha="deadbeef", pipeline_tag=None, tags=[], library_name=None)
    fake_api = _install_fake_api(monkeypatch, model_info_result=info, files=[])
    monkeypatch.setattr("app.adapters.hf_hub.ModelCard", _FakeModelCard)
    assert not hasattr(fake_api, "snapshot_download")
    assert not hasattr(fake_api, "hf_hub_download")

    HfHubModelAdapter().resolve("org/model")
