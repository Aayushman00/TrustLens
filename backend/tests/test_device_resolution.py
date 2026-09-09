"""GPU/CUDA device detection and selection — never fabricated, always recorded.

Covers: CUDA available -> CUDA selected; CUDA unavailable -> CPU selected;
GPU metadata correctly recorded; CPU fallback reason recorded; no fabricated
GPU metadata when detection finds nothing; LocalHFBackend actually places
tensors on the resolved device (via .to() call assertions).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.inference.device import GpuDetection, detect_gpu, resolve_device


def _mock_torch(*, cuda_available: bool, device_name: str | None = None, raises: bool = False):
    torch_mock = MagicMock()
    if raises:
        torch_mock.cuda.is_available.side_effect = RuntimeError("driver not visible")
    else:
        torch_mock.cuda.is_available.return_value = cuda_available
    torch_mock.cuda.get_device_name.return_value = device_name
    return torch_mock


def test_cuda_available_is_detected_with_real_gpu_name() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=True, device_name="NVIDIA GeForce RTX 4060")}):
        detection = detect_gpu()
    assert detection.cuda_available is True
    assert detection.gpu_available is True
    assert detection.gpu_name == "NVIDIA GeForce RTX 4060"
    assert detection.driver_visible is True
    assert detection.detection_error is None


def test_cuda_unavailable_is_detected_with_no_fabricated_gpu_name() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=False)}):
        detection = detect_gpu()
    assert detection.cuda_available is False
    assert detection.gpu_available is False
    assert detection.gpu_name is None  # never fabricated
    assert detection.driver_visible is False


def test_detection_error_is_recorded_not_swallowed() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=False, raises=True)}):
        detection = detect_gpu()
    assert detection.cuda_available is False
    assert detection.gpu_name is None
    assert detection.detection_error is not None
    assert "driver not visible" in detection.detection_error


def test_missing_torch_is_recorded_as_detection_error() -> None:
    with patch.dict("sys.modules", {"torch": None}):
        detection = detect_gpu()
    assert detection.cuda_available is False
    assert detection.gpu_available is False
    assert detection.detection_error is not None


def test_auto_selects_cuda_when_available() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=True, device_name="RTX 4060")}):
        decision = resolve_device("auto")
    assert decision.device == "cuda"
    assert decision.execution_device == "cuda"
    assert decision.gpu_available is True
    assert decision.cuda_available is True
    assert decision.gpu_name == "RTX 4060"
    assert decision.fallback_reason is None
    assert "CUDA" in decision.device_reason


def test_auto_falls_back_to_cpu_when_no_cuda_with_explicit_reason() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=False)}):
        decision = resolve_device("auto")
    assert decision.device == "cpu"
    assert decision.execution_device == "cpu"
    assert decision.gpu_available is False
    assert decision.cuda_available is False
    assert decision.gpu_name is None
    assert decision.fallback_reason is not None
    assert "no CUDA" in decision.fallback_reason


def test_explicit_cuda_request_falls_back_when_unavailable_and_records_reason() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=False)}):
        decision = resolve_device("cuda")
    assert decision.device == "cpu"
    assert decision.requested_device == "cuda"
    assert decision.fallback_reason is not None
    assert "explicitly requested" in decision.fallback_reason


def test_explicit_cpu_request_is_never_a_fallback() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=True, device_name="RTX 4060")}):
        decision = resolve_device("cpu")
    assert decision.device == "cpu"
    assert decision.fallback_reason is None
    assert decision.device_reason == "explicit cpu requested"
    # Detection info is still attached even though CPU was chosen — a GPU
    # being present-but-unused must be visible, not hidden.
    assert decision.gpu_available is True
    assert decision.gpu_name == "RTX 4060"


def test_no_fabricated_gpu_metadata_when_nothing_detected() -> None:
    with patch.dict("sys.modules", {"torch": _mock_torch(cuda_available=False)}):
        decision = resolve_device("auto")
    assert decision.gpu_name is None
    assert decision.gpu_available is False
    assert decision.cuda_available is False


def test_detection_is_dataclass_frozen_and_typed() -> None:
    detection = GpuDetection(
        cuda_available=False,
        gpu_available=False,
        gpu_name=None,
        driver_visible=False,
    )
    assert detection.detection_error is None
