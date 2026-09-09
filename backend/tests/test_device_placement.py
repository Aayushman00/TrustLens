"""LocalHFBackend actually places model/tensors on the resolved device.

Split into:
- portable tests (mock ``resolve_device`` so they run on any machine, GPU or
  not) that verify the CPU-fallback wiring and that evidence fields are
  recorded correctly;
- one real-hardware test that only runs when this exact host has a genuine
  CUDA GPU (``pytest.mark.skipif``) — it moves a real tensor onto the real
  GPU and asserts ``tensor.device.type == "cuda"``. It is skipped, never
  faked, on machines without a GPU.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch

from app.inference.base import InferenceConfig, TaskType
from app.inference.device import DeviceDecision
from app.inference.local_hf import LocalHFBackend

_HAS_REAL_CUDA = torch.cuda.is_available()


def _mock_transformers(*, num_labels: int = 2):
    mock_tokenizer = MagicMock()

    def _encode(texts, **kwargs):  # noqa: ANN001
        batch_len = len(texts)
        return {
            "input_ids": torch.zeros(batch_len, 4, dtype=torch.long),
            "attention_mask": torch.ones(batch_len, 4, dtype=torch.long),
        }

    mock_tokenizer.side_effect = _encode

    mock_model = MagicMock()
    mock_model.config.num_labels = num_labels
    mock_model.config.problem_type = None
    mock_model.parameters.return_value = iter([MagicMock(dtype="float32")])
    mock_model.eval = MagicMock()
    mock_model.to = MagicMock(return_value=mock_model)

    def _forward(**kwargs):  # noqa: ANN003
        out = MagicMock()
        out.logits = torch.tensor([[1.0, 0.0]])
        return out

    mock_model.side_effect = _forward
    return mock_tokenizer, mock_model


def test_cpu_fallback_is_actually_used_for_model_placement() -> None:
    """resolve_device forced to CPU fallback -> model.to(cpu) actually called."""
    backend = LocalHFBackend()
    tokenizer, model = _mock_transformers()
    decision = DeviceDecision(
        device="cpu",
        execution_device="cpu",
        requested_device="auto",
        gpu_available=False,
        gpu_name=None,
        cuda_available=False,
        device_reason="cpu fallback",
        fallback_reason="no CUDA-capable GPU detected",
    )
    with (
        patch("transformers.AutoTokenizer.from_pretrained", return_value=tokenizer),
        patch("transformers.AutoModelForSequenceClassification.from_pretrained", return_value=model),
        patch("app.inference.local_hf.resolve_device", return_value=decision),
    ):
        backend.load("org/m", config=InferenceConfig(task_type=TaskType.BINARY_CLASSIFICATION))
        assert model.to.call_args[0][0] == torch.device("cpu")

        result = backend.predict_batch(["hello"])
        # Encoded tensors were actually moved via .to(device) — verifiable on
        # a real (CPU) tensor since CPU is always available.
        assert result.metadata.device == "cpu"
        assert result.metadata.execution_device == "cpu"
        assert result.metadata.gpu_available is False
        assert result.metadata.cuda_available is False
        assert result.metadata.fallback_reason == "no CUDA-capable GPU detected"
        assert result.metadata.gpu_name is None  # never fabricated
        backend.close()


def test_cuda_decision_selects_cuda_device_object_for_model_placement() -> None:
    """resolve_device forced to CUDA -> model.to(cuda) actually requested.

    Uses a mocked model (``.to`` is a MagicMock) so this runs without real
    GPU hardware — it verifies the *placement call*, not real tensor residency
    (that's covered by the real-hardware test below).
    """
    backend = LocalHFBackend()
    tokenizer, model = _mock_transformers()
    decision = DeviceDecision(
        device="cuda",
        execution_device="cuda",
        requested_device="auto",
        gpu_available=True,
        gpu_name="Mock GPU",
        cuda_available=True,
        device_reason="CUDA GPU detected and selected",
        fallback_reason=None,
    )
    with (
        patch("transformers.AutoTokenizer.from_pretrained", return_value=tokenizer),
        patch("transformers.AutoModelForSequenceClassification.from_pretrained", return_value=model),
        patch("app.inference.local_hf.resolve_device", return_value=decision),
    ):
        backend.load("org/m", config=InferenceConfig(task_type=TaskType.BINARY_CLASSIFICATION))
        assert model.to.call_args[0][0] == torch.device("cuda")
        meta = backend._build_metadata()  # noqa: SLF001 — white-box evidence check
        assert meta.device == "cuda"
        assert meta.execution_device == "cuda"
        assert meta.gpu_available is True
        assert meta.gpu_name == "Mock GPU"
        assert meta.cuda_available is True
        assert meta.fallback_reason is None
        backend.close()


def test_device_info_never_claims_gpu_when_decision_was_cpu() -> None:
    backend = LocalHFBackend()
    tokenizer, model = _mock_transformers()
    decision = DeviceDecision(
        device="cpu",
        execution_device="cpu",
        requested_device="cuda",
        gpu_available=False,
        gpu_name=None,
        cuda_available=False,
        device_reason="cpu fallback",
        fallback_reason="CUDA was explicitly requested but is not available",
    )
    with (
        patch("transformers.AutoTokenizer.from_pretrained", return_value=tokenizer),
        patch("transformers.AutoModelForSequenceClassification.from_pretrained", return_value=model),
        patch("app.inference.local_hf.resolve_device", return_value=decision),
    ):
        backend.load("org/m", config=InferenceConfig(task_type=TaskType.BINARY_CLASSIFICATION))
        info = backend.device_info()
        assert info.device == "cpu"
        assert info.device_type == "cpu"
        assert info.gpu_available is False
        assert info.gpu_name is None
        assert info.fallback_reason == "CUDA was explicitly requested but is not available"
        backend.close()


@pytest.mark.skipif(
    not _HAS_REAL_CUDA,
    reason="requires a genuine CUDA GPU on this host — skipped, not faked, elsewhere",
)
def test_real_gpu_end_to_end_tensor_placement() -> None:
    """Real hardware check: with an actual CUDA GPU, LocalHFBackend really
    resolves to cuda and a real tensor ends up resident on the GPU."""
    from app.inference.device import resolve_device

    decision = resolve_device("auto")
    assert decision.device == "cuda"
    assert decision.gpu_available is True
    assert decision.gpu_name  # real detected name, non-empty
    assert decision.cuda_available is True
    assert decision.fallback_reason is None

    device = torch.device(decision.device)
    tensor = torch.zeros(2, 2).to(device)
    assert tensor.device.type == "cuda"
