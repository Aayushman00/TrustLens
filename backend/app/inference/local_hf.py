"""Local Hugging Face inference via Transformers (sequence classification / regression)."""

from __future__ import annotations

import logging
from typing import Any

from app.inference.base import (
    BatchPrediction,
    DecisionMode,
    DeviceInfo,
    InferenceConfig,
    InferenceMetadata,
    LoadedModelInfo,
    PredictionRecord,
    TaskType,
)
from app.inference.device import DeviceDecision, resolve_device
from app.inference.errors import (
    INFERENCE_ERROR,
    INVALID_INPUT,
    INVALID_MODEL_REVISION,
    MODEL_LOAD_ERROR,
    NOT_LOADED,
    TOKENIZATION_ERROR,
    UNSUPPORTED_TASK,
    InferenceError,
)

logger = logging.getLogger("trustlens.inference.local_hf")

_BACKEND_ID = "local_hf"


def _resolve_hf_token(hf_token: str | None) -> str | None:
    if hf_token:
        return hf_token
    try:
        from app.core.config import get_settings

        return get_settings().hf_token
    except Exception:  # noqa: BLE001
        return None


def _softmax(logits: list[float]) -> list[float]:
    import math

    if not logits:
        return []
    max_v = max(logits)
    exps = [math.exp(v - max_v) for v in logits]
    total = sum(exps)
    if total == 0:
        return [1.0 / len(logits)] * len(logits)
    return [v / total for v in exps]


class LocalHFBackend:
    """Load HF weights once; run ordered batch predictions."""

    def __init__(self) -> None:
        self._model_ref: str | None = None
        self._revision: str | None = None
        self._config: InferenceConfig = InferenceConfig()
        self._tokenizer: Any = None
        self._model: Any = None
        self._device: Any = None
        self._device_decision: DeviceDecision | None = None
        self._loaded_info = LoadedModelInfo()
        self.is_loaded = False

    def load(
        self,
        model_ref: str,
        *,
        revision: str | None = None,
        config: InferenceConfig | None = None,
        hf_token: str | None = None,
    ) -> LoadedModelInfo:
        ref = (model_ref or "").strip()
        if not ref:
            raise InferenceError(INVALID_INPUT, "model_ref must not be empty")

        self.close()
        self._model_ref = ref
        self._revision = revision
        self._config = config or InferenceConfig()

        try:
            import torch
            from huggingface_hub.utils import RevisionNotFoundError
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise InferenceError(
                MODEL_LOAD_ERROR,
                "torch/transformers required — install trustlens-backend[robustness]",
                details={"cause": str(exc)},
            ) from exc

        token = _resolve_hf_token(hf_token)
        token_kwargs: dict[str, Any] = {}
        if revision:
            token_kwargs["revision"] = revision
        if token:
            token_kwargs["token"] = token

        try:
            tokenizer = AutoTokenizer.from_pretrained(ref, **token_kwargs)
            model = AutoModelForSequenceClassification.from_pretrained(ref, **token_kwargs)
        except RevisionNotFoundError as exc:
            raise InferenceError(
                INVALID_MODEL_REVISION,
                f"model revision not found for {ref}",
                details={"model_ref": ref, "revision": revision},
            ) from exc
        except Exception as exc:
            raise InferenceError(
                MODEL_LOAD_ERROR,
                f"failed to load model {ref}",
                details={"model_ref": ref, "revision": revision, "cause": str(exc)},
            ) from exc

        decision = resolve_device(self._config.device)
        device = torch.device(decision.device)
        model.to(device)
        model.eval()
        self._device_decision = decision
        if decision.fallback_reason:
            logger.info(
                "inference_device_fallback requested=%s selected=%s reason=%s",
                decision.requested_device,
                decision.device,
                decision.fallback_reason,
            )

        num_labels = getattr(model.config, "num_labels", None)
        problem_type = getattr(model.config, "problem_type", None)
        if self._config.task_type == TaskType.REGRESSION:
            if not (
                num_labels == 1
                or problem_type == "regression"
                or getattr(model.config, "id2label", None) == {0: "LABEL_0"}
            ):
                self.close()
                raise InferenceError(
                    UNSUPPORTED_TASK,
                    "model head is not configured for regression",
                    details={
                        "model_ref": ref,
                        "num_labels": num_labels,
                        "problem_type": problem_type,
                    },
                )
        elif self._config.task_type in (
            TaskType.BINARY_CLASSIFICATION,
            TaskType.MULTICLASS_CLASSIFICATION,
        ):
            if num_labels is None or num_labels < 1:
                self.close()
                raise InferenceError(
                    UNSUPPORTED_TASK,
                    "model has no sequence-classification head",
                    details={"model_ref": ref, "num_labels": num_labels},
                )

        id2label_raw = getattr(model.config, "id2label", None)
        id2label: dict[int, str] | None = None
        if isinstance(id2label_raw, dict):
            id2label = {int(k): str(v) for k, v in id2label_raw.items()}

        self._tokenizer = tokenizer
        self._model = model
        self._device = device
        self._loaded_info = LoadedModelInfo(
            num_labels=int(num_labels) if isinstance(num_labels, int) else None,
            problem_type=str(problem_type) if problem_type else None,
            id2label=id2label,
        )
        self.is_loaded = True
        logger.info(
            "inference_loaded model_ref=%s revision=%s task=%s device=%s",
            ref,
            revision,
            self._config.task_type.value,
            self._config.device,
        )
        return self._loaded_info

    def predict(self, inputs: list[str]) -> BatchPrediction:
        return self.predict_batch(inputs)

    def predict_batch(self, inputs: list[str]) -> BatchPrediction:
        if not self.is_loaded or self._model is None or self._tokenizer is None:
            raise InferenceError(NOT_LOADED, "model is not loaded — call load() first")
        if not isinstance(inputs, list):
            raise InferenceError(INVALID_INPUT, "inputs must be a list of strings")
        texts = [str(x) for x in inputs]
        if not texts:
            return BatchPrediction(
                predictions=[],
                n_samples=0,
                metadata=self._build_metadata(),
            )

        import torch

        predictions: list[PredictionRecord] = []
        batch_size = max(1, int(self._config.batch_size))
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            try:
                encoded = self._tokenizer(
                    chunk,
                    return_tensors="pt",
                    truncation=True,
                    max_length=self._config.max_length,
                    padding=True,
                )
            except Exception as exc:
                raise InferenceError(
                    TOKENIZATION_ERROR,
                    "tokenizer failed on input batch",
                    details={"batch_start": start, "batch_size": len(chunk)},
                ) from exc
            encoded = {k: v.to(self._device) for k, v in encoded.items()}
            try:
                with torch.no_grad():
                    outputs = self._model(**encoded)
                    logits_tensor = outputs.logits
            except Exception as exc:
                raise InferenceError(
                    INFERENCE_ERROR,
                    "model forward pass failed",
                    details={"batch_start": start, "batch_size": len(chunk)},
                ) from exc

            for row_logits in logits_tensor.cpu().tolist():
                record = self._decode_logits(row_logits)
                predictions.append(record)

        if len(predictions) != len(texts):
            raise InferenceError(
                INFERENCE_ERROR,
                "prediction count does not match input count",
                details={"expected": len(texts), "got": len(predictions)},
            )

        return BatchPrediction(
            predictions=predictions,
            n_samples=len(predictions),
            metadata=self._build_metadata(),
        )

    def _decode_logits(self, row_logits: list[float]) -> PredictionRecord:
        if self._config.task_type == TaskType.REGRESSION:
            value = float(row_logits[0] if len(row_logits) == 1 else row_logits[0])
            return PredictionRecord(y_hat=value, logits=list(row_logits))

        probs = _softmax(row_logits)
        if (
            self._config.task_type == TaskType.BINARY_CLASSIFICATION
            and self._config.decision == DecisionMode.THRESHOLD
            and len(probs) >= 2
        ):
            y_hat = 1 if probs[1] >= self._config.binary_threshold else 0
        else:
            y_hat = int(max(range(len(row_logits)), key=lambda i: row_logits[i]))
        return PredictionRecord(y_hat=y_hat, probabilities=probs, logits=list(row_logits))

    def _build_metadata(self) -> InferenceMetadata:
        dtype: str | None = None
        if self._model is not None:
            try:
                dtype = str(next(self._model.parameters()).dtype)
            except StopIteration:
                dtype = None
        decision = self._device_decision
        device_str = decision.device if decision is not None else self._config.device
        device_name = decision.gpu_name if decision is not None else None
        return InferenceMetadata(
            model_ref=self._model_ref or "",
            revision=self._revision,
            task_type=self._config.task_type.value,
            device=device_str,
            device_name=device_name,
            dtype=dtype,
            batch_size=self._config.batch_size,
            backend=_BACKEND_ID,
            num_labels=self._loaded_info.num_labels,
            execution_device=decision.execution_device if decision is not None else None,
            gpu_available=decision.gpu_available if decision is not None else None,
            gpu_name=decision.gpu_name if decision is not None else None,
            cuda_available=decision.cuda_available if decision is not None else None,
            device_reason=decision.device_reason if decision is not None else None,
            fallback_reason=decision.fallback_reason if decision is not None else None,
        )

    def device_info(self) -> DeviceInfo:
        meta = self._build_metadata() if self.is_loaded else None
        if meta is None:
            return DeviceInfo(
                device=self._config.device,
                device_type="cpu" if self._config.device == "cpu" else "accelerator",
                device_name=None,
                dtype=None,
                batch_size=self._config.batch_size,
                backend=_BACKEND_ID,
            )
        device_type = "cpu" if meta.device == "cpu" else "accelerator"
        return DeviceInfo(
            device=meta.device,
            device_type=device_type,
            device_name=meta.device_name,
            dtype=meta.dtype,
            batch_size=meta.batch_size,
            backend=meta.backend,
            execution_device=meta.execution_device,
            gpu_available=meta.gpu_available,
            gpu_name=meta.gpu_name,
            cuda_available=meta.cuda_available,
            device_reason=meta.device_reason,
            fallback_reason=meta.fallback_reason,
        )

    def close(self) -> None:
        self._tokenizer = None
        self._model = None
        self._device = None
        self._device_decision = None
        self._model_ref = None
        self._revision = None
        self._loaded_info = LoadedModelInfo()
        self.is_loaded = False
