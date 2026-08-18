"""Hugging Face Hub model adapter (Phase 6, ADR 0012).

Resolves user-selected HF repo ids/URLs to normalized metadata via the Hub
metadata APIs only (``HfApi.model_info``, ``HfApi.list_repo_files``,
``ModelCard.load``). Never downloads model weight files, never crawls/searches
the Hub, and never scrapes the website.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any
from urllib.parse import urlparse

from huggingface_hub import HfApi, ModelCard
from huggingface_hub.utils import (
    GatedRepoError,
    HfHubHTTPError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)

from app.adapters.base import (
    HfAuthRequiredError,
    HfHubUnavailableError,
    InvalidModelRefError,
    ModelNotFoundError,
    NormalizedModelRecord,
)
from app.core.config import get_settings

logger = logging.getLogger("trustlens.adapters.hf_hub")

_ALLOWED_HOSTS = {"huggingface.co", "www.huggingface.co"}
_REPO_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_REVISION_KEYWORDS = {"tree", "blob", "commit", "resolve"}


def parse_hf_ref(repo_id: str | None, url: str | None) -> tuple[str, str | None]:
    """Normalize a bare repo id or an ``https://huggingface.co/...`` URL.

    Returns ``(repo_id, revision_hint)``. Raises ``InvalidModelRefError``
    (422 / ``INVALID_MODEL_REF``) on malformed input or a non-HF host — this
    is the SSRF guard, since only ``huggingface.co`` is ever fetched.
    """
    if url:
        return _parse_hf_url(url)
    ref = (repo_id or "").strip()
    _validate_repo_id(ref)
    return ref, None


def _parse_hf_url(url: str) -> tuple[str, str | None]:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("https", "http") or host not in _ALLOWED_HOSTS:
        raise InvalidModelRefError(
            "Only https://huggingface.co model URLs are accepted",
            details={"url": url},
        )
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        raise InvalidModelRefError("URL is missing a model path", details={"url": url})

    revision: str | None = None
    keyword_index = next((i for i, s in enumerate(segments) if s in _REVISION_KEYWORDS), None)
    if keyword_index is not None:
        repo_segments = segments[:keyword_index]
        if keyword_index + 1 < len(segments):
            revision = segments[keyword_index + 1]
    else:
        repo_segments = segments[:2] if len(segments) >= 2 else segments[:1]

    ref = "/".join(repo_segments)
    _validate_repo_id(ref)
    return ref, revision


def _validate_repo_id(ref: str) -> None:
    if not ref:
        raise InvalidModelRefError("Model reference is empty")
    segments = ref.split("/")
    if len(segments) > 2 or not all(_REPO_SEGMENT_RE.match(s) for s in segments):
        raise InvalidModelRefError(
            "Invalid Hugging Face repo id — expected 'model-name' or 'org/model-name'",
            details={"ref": ref},
        )


def _to_plain_dict(obj: Any) -> dict[str, Any] | None:
    """Best-effort conversion of a Hub SDK object to a plain JSON-able dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:  # noqa: BLE001 - defensive; metadata extraction must never crash
            return None
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        try:
            return dataclasses.asdict(obj)
        except Exception:  # noqa: BLE001
            return None
    return None


class HfHubModelAdapter:
    """Resolves Hugging Face Hub model metadata. Never downloads model weights."""

    def __init__(self, *, token: str | None = None) -> None:
        settings = get_settings()
        resolved = token if token is not None else settings.hf_token
        # An unset HF_TOKEN env var still round-trips as "" through pydantic-settings —
        # an empty bearer token produces an invalid Authorization header, so treat it as absent.
        self._token: str | None = resolved or None
        self._api = HfApi(token=self._token)

    def resolve(self, ref: str, revision: str | None = None) -> NormalizedModelRecord:
        _validate_repo_id(ref)
        info = self._fetch_model_info(ref, revision)
        resolved_revision = getattr(info, "sha", None) or revision

        config = getattr(info, "config", None) or {}
        architectures = config.get("architectures") if isinstance(config, dict) else None
        card_data = _to_plain_dict(getattr(info, "card_data", None))
        pipeline_tag = getattr(info, "pipeline_tag", None)

        metadata: dict[str, Any] = {
            "source": "huggingface_hub",
            "architecture": architectures[0] if architectures else None,
            "pipeline_tag": pipeline_tag,
            "task": pipeline_tag,
            "license": card_data.get("license") if card_data else None,
            "tags": list(getattr(info, "tags", None) or []),
            "card_text": None,
            "card_data": card_data,
            "files": self._fetch_file_list(ref, resolved_revision),
            "library_name": getattr(info, "library_name", None),
            "transformers_info": _to_plain_dict(getattr(info, "transformers_info", None)),
            "hub_url": f"https://huggingface.co/{ref}",
        }
        metadata["card_text"] = self._fetch_card_text(ref)

        return NormalizedModelRecord(
            hf_repo_id=ref,
            revision=resolved_revision,
            checksum=resolved_revision,
            model_metadata=metadata,
        )

    def _fetch_model_info(self, ref: str, revision: str | None) -> Any:
        try:
            return self._api.model_info(ref, revision=revision, token=self._token)
        except GatedRepoError as exc:
            raise HfAuthRequiredError(
                f"Model '{ref}' is gated — set HF_TOKEN with access to import it",
                details={"hf_repo_id": ref},
            ) from exc
        except RepositoryNotFoundError as exc:
            raise ModelNotFoundError(
                f"Model '{ref}' was not found on Hugging Face Hub",
                details={"hf_repo_id": ref},
            ) from exc
        except RevisionNotFoundError as exc:
            raise ModelNotFoundError(
                f"Revision '{revision}' not found for model '{ref}'",
                details={"hf_repo_id": ref, "revision": revision},
            ) from exc
        except HfHubHTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code in (401, 403):
                raise HfAuthRequiredError(
                    f"Access denied for model '{ref}' — set HF_TOKEN with access",
                    details={"hf_repo_id": ref},
                ) from exc
            raise HfHubUnavailableError(
                "Hugging Face Hub request failed",
                details={"hf_repo_id": ref},
            ) from exc
        except Exception as exc:
            raise HfHubUnavailableError(
                "Hugging Face Hub is unreachable",
                details={"hf_repo_id": ref},
            ) from exc

    def _fetch_file_list(self, ref: str, revision: str | None) -> list[str]:
        """Filenames only (ADR 0012) — never downloads file contents."""
        try:
            return list(self._api.list_repo_files(ref, revision=revision, token=self._token))
        except Exception:  # noqa: BLE001 - non-critical; import should still succeed
            logger.warning("hf_list_repo_files_failed hf_repo_id=%s", ref)
            return []

    def _fetch_card_text(self, ref: str) -> str | None:
        """``ModelCard.load`` has no revision parameter — always reads the default branch."""
        try:
            card = ModelCard.load(ref, token=self._token)
            return getattr(card, "text", None)
        except Exception:  # noqa: BLE001 - many repos have no card; not fatal
            logger.info("hf_model_card_unavailable hf_repo_id=%s", ref)
            return None
