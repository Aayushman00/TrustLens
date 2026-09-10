"""Config-only (AutoConfig) model inspection for intake-time compatibility
validation. Never loads model weights — no GPU/RAM cost, no torch import
required at the API layer."""

from __future__ import annotations

from dataclasses import dataclass

from transformers import AutoConfig

from app.inference.errors import INVALID_MODEL_REVISION, MODEL_LOAD_ERROR


class ModelInspectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ModelLabelSnapshot:
    num_labels: int
    id2label: dict[int, str]
    resolved_sha: str


def inspect_model_config(
    model_ref: str,
    *,
    revision: str | None,
    hf_token: str | None,
) -> ModelLabelSnapshot:
    kwargs: dict[str, str] = {}
    if revision:
        kwargs["revision"] = revision
    if hf_token:
        kwargs["token"] = hf_token
    try:
        config = AutoConfig.from_pretrained(model_ref, **kwargs)
    except Exception as exc:
        from huggingface_hub.utils import RevisionNotFoundError

        if isinstance(exc, RevisionNotFoundError):
            raise ModelInspectionError(
                INVALID_MODEL_REVISION, f"model revision not found for {model_ref}: {exc}"
            ) from exc
        raise ModelInspectionError(MODEL_LOAD_ERROR, f"failed to inspect model config for {model_ref}: {exc}") from exc

    # Primary check: ensure model has a sequence-classification architecture
    architectures = getattr(config, "architectures", None) or []
    is_classifier = any(
        arch.endswith("ForSequenceClassification")
        for arch in (architectures if architectures else [])
    )
    if not is_classifier:
        raise ModelInspectionError(
            MODEL_LOAD_ERROR,
            f"{model_ref} does not have a sequence-classification architecture (found: {architectures})",
        )

    # Secondary sanity checks for classification metadata
    num_labels = getattr(config, "num_labels", None)
    id2label_raw = getattr(config, "id2label", None)
    if not num_labels or not isinstance(id2label_raw, dict):
        raise ModelInspectionError(
            MODEL_LOAD_ERROR, f"{model_ref} has no classification metadata (num_labels={num_labels})"
        )
    resolved_sha = getattr(config, "_commit_hash", None) or (revision or "")
    return ModelLabelSnapshot(
        num_labels=int(num_labels),
        id2label={int(k): str(v) for k, v in id2label_raw.items()},
        resolved_sha=str(resolved_sha),
    )
