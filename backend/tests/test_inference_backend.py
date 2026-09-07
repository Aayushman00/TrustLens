"""InferenceBackend + LocalHFBackend unit tests (mocked HF, no downloads)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.inference.base import (
    DecisionMode,
    InferenceConfig,
    PredictionRecord,
    TaskType,
)
from app.inference.errors import (
    INVALID_INPUT,
    INVALID_MODEL_REVISION,
    MODEL_LOAD_ERROR,
    NOT_LOADED,
    UNSUPPORTED_TASK,
    InferenceError,
)
from app.inference.local_hf import LocalHFBackend, _softmax
from tests.fakes import FakeInferenceBackend


def _hub_error(cls: type[Exception], message: str, *, status_code: int = 404) -> Exception:
    try:
        return cls(message)
    except TypeError:
        response = httpx.Response(
            status_code,
            request=httpx.Request("GET", "https://huggingface.co/api/models/test"),
        )
        return cls(message, response=response)


def test_fake_backend_load_and_ordered_batch() -> None:
    backend = FakeInferenceBackend(predictions=[1, 0, 1])
    backend.load("org/model", revision="abc123")
    out = backend.predict_batch(["a", "b", "c", "d", "e"])
    assert [p.y_hat for p in out.predictions] == [1, 0, 1, 1, 0]
    assert backend.load_calls[0]["model_ref"] == "org/model"
    assert backend.load_calls[0]["revision"] == "abc123"
    assert backend.predict_calls == [["a", "b", "c", "d", "e"]]


def test_fake_backend_respects_batch_chunks_via_local_hf(monkeypatch: pytest.MonkeyPatch) -> None:
    """LocalHFBackend batches without reordering."""
    backend = LocalHFBackend()
    config = InferenceConfig(batch_size=2, task_type=TaskType.MULTICLASS_CLASSIFICATION)

    mock_tokenizer = MagicMock()
    mock_model = MagicMock()
    mock_model.config.num_labels = 3
    mock_model.config.problem_type = None
    mock_model.parameters.return_value = iter([MagicMock(dtype="float32")])

    def _encode(texts, **kwargs):  # noqa: ANN001
        import torch

        batch_len = len(texts)
        return {
            "input_ids": torch.zeros(batch_len, 4, dtype=torch.long),
            "attention_mask": torch.ones(batch_len, 4, dtype=torch.long),
        }

    mock_tokenizer.side_effect = _encode

    logits_batches = [
        [[2.0, 0.0, 0.0], [0.0, 3.0, 0.0]],
        [[0.0, 0.0, 4.0]],
    ]
    call_idx = {"i": 0}

    def _forward(**kwargs):  # noqa: ANN003
        import torch

        logits = torch.tensor(logits_batches[call_idx["i"]])
        call_idx["i"] += 1
        out = MagicMock()
        out.logits = logits
        return out

    mock_model.eval = MagicMock()
    mock_model.to = MagicMock(return_value=mock_model)
    mock_model.side_effect = _forward

    with (
        patch("transformers.AutoTokenizer.from_pretrained", return_value=mock_tokenizer),
        patch(
            "transformers.AutoModelForSequenceClassification.from_pretrained",
            return_value=mock_model,
        ),
    ):
        backend.load("org/m", revision="rev1", config=config)
        result = backend.predict_batch(["t1", "t2", "t3"])
        backend.close()

    assert [p.y_hat for p in result.predictions] == [0, 1, 2]
    assert mock_tokenizer.call_count == 2


def test_local_hf_passes_revision_to_from_pretrained() -> None:
    backend = LocalHFBackend()
    mock_tokenizer = MagicMock()
    mock_model = MagicMock()
    mock_model.config.num_labels = 2
    mock_model.parameters.return_value = iter([MagicMock(dtype="float32")])
    mock_model.eval = MagicMock()
    mock_model.to = MagicMock(return_value=mock_model)

    with (
        patch(
            "transformers.AutoTokenizer.from_pretrained",
            return_value=mock_tokenizer,
        ) as tok,
        patch(
            "transformers.AutoModelForSequenceClassification.from_pretrained",
            return_value=mock_model,
        ) as mdl,
    ):
        backend.load("org/x", revision="deadbeef", config=InferenceConfig())
        backend.close()

    assert tok.call_args.kwargs.get("revision") == "deadbeef"
    assert mdl.call_args.kwargs.get("revision") == "deadbeef"


def test_invalid_revision_maps_to_error() -> None:
    from huggingface_hub.utils import RevisionNotFoundError

    backend = LocalHFBackend()
    with (
        patch(
            "transformers.AutoTokenizer.from_pretrained",
            side_effect=_hub_error(RevisionNotFoundError, "bad"),
        ),
        pytest.raises(InferenceError) as exc,
    ):
        backend.load("org/x", revision="missing")
    assert exc.value.code == INVALID_MODEL_REVISION


def test_unsupported_regression_head() -> None:
    backend = LocalHFBackend()
    mock_model = MagicMock()
    mock_model.config.num_labels = 3
    mock_model.config.problem_type = "single_label_classification"
    mock_model.eval = MagicMock()
    mock_model.to = MagicMock(return_value=mock_model)

    with (
        patch("transformers.AutoTokenizer.from_pretrained", return_value=MagicMock()),
        patch(
            "transformers.AutoModelForSequenceClassification.from_pretrained",
            return_value=mock_model,
        ),
        pytest.raises(InferenceError) as exc,
    ):
        backend.load(
            "org/x",
            config=InferenceConfig(task_type=TaskType.REGRESSION),
        )
    assert exc.value.code == UNSUPPORTED_TASK


def test_predict_without_load_raises_not_loaded() -> None:
    backend = LocalHFBackend()
    with pytest.raises(InferenceError) as exc:
        backend.predict_batch(["hi"])
    assert exc.value.code == NOT_LOADED


def test_binary_threshold_decoding() -> None:
    backend = LocalHFBackend()
    config = InferenceConfig(
        task_type=TaskType.BINARY_CLASSIFICATION,
        decision=DecisionMode.THRESHOLD,
        binary_threshold=0.5,
    )
    backend._config = config  # noqa: SLF001
    backend.is_loaded = True
    record_low = backend._decode_logits([2.0, 0.0])  # noqa: SLF001
    record_high = backend._decode_logits([0.0, 2.0])  # noqa: SLF001
    assert record_low.y_hat == 0
    assert record_high.y_hat == 1
    assert record_low.probabilities is not None


def test_regression_decode_continuous() -> None:
    backend = LocalHFBackend()
    backend._config = InferenceConfig(task_type=TaskType.REGRESSION)  # noqa: SLF001
    record = backend._decode_logits([1.25])  # noqa: SLF001
    assert record.y_hat == 1.25


def test_softmax_sums_to_one() -> None:
    probs = _softmax([1.0, 2.0, 3.0])
    assert abs(sum(probs) - 1.0) < 1e-6


def test_device_info_exposed() -> None:
    backend = FakeInferenceBackend()
    backend.load("org/m", revision="r1", config=InferenceConfig(batch_size=16))
    info = backend.device_info()
    assert info.backend == "fake"
    assert info.batch_size == 16
    assert info.device == "cpu"


def test_load_failure_propagates() -> None:
    err = InferenceError(MODEL_LOAD_ERROR, "boom")
    backend = FakeInferenceBackend(load_error=err)
    with pytest.raises(InferenceError) as exc:
        backend.load("org/m")
    assert exc.value.code == MODEL_LOAD_ERROR


def test_empty_model_ref_invalid() -> None:
    backend = LocalHFBackend()
    with pytest.raises(InferenceError) as exc:
        backend.load("")
    assert exc.value.code == INVALID_INPUT
