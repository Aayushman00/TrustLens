"""Runtime GPU/CUDA detection and device selection for local inference.

Never fabricates GPU information: every field here is either read directly
from ``torch.cuda`` or explicitly ``None``/``False`` when unavailable/unknown.
Detection failures (missing torch, driver not visible, etc.) are recorded as
an explicit reason string, never silently swallowed into a false "cpu is
fine" without saying why.
"""

from __future__ import annotations

from dataclasses import dataclass

_AUTO = "auto"


@dataclass(frozen=True)
class GpuDetection:
    """Raw hardware/runtime probe result — no device-selection policy here."""

    cuda_available: bool
    gpu_available: bool
    gpu_name: str | None
    driver_visible: bool
    detection_error: str | None = None


@dataclass(frozen=True)
class DeviceDecision:
    """The actual device selected for inference, plus why."""

    device: str
    """The torch device string actually used, e.g. ``"cuda"`` or ``"cpu"``."""
    execution_device: str
    """Same value as ``device`` — explicit alias for evidence/UI display."""
    requested_device: str
    gpu_available: bool
    gpu_name: str | None
    cuda_available: bool
    device_reason: str
    fallback_reason: str | None = None


def detect_gpu() -> GpuDetection:
    """Probe torch/CUDA for real hardware — never invents a GPU name."""
    try:
        import torch
    except ImportError as exc:
        return GpuDetection(
            cuda_available=False,
            gpu_available=False,
            gpu_name=None,
            driver_visible=False,
            detection_error=f"torch is not importable: {exc}",
        )

    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception as exc:  # noqa: BLE001 — detection must never raise
        return GpuDetection(
            cuda_available=False,
            gpu_available=False,
            gpu_name=None,
            driver_visible=False,
            detection_error=f"torch.cuda.is_available() raised: {exc}",
        )

    if not cuda_available:
        return GpuDetection(
            cuda_available=False,
            gpu_available=False,
            gpu_name=None,
            driver_visible=False,
            detection_error=None,
        )

    gpu_name: str | None = None
    detection_error: str | None = None
    try:
        gpu_name = torch.cuda.get_device_name(0)
    except Exception as exc:  # noqa: BLE001
        detection_error = f"CUDA reported available but device query failed: {exc}"

    return GpuDetection(
        cuda_available=True,
        gpu_available=gpu_name is not None,
        gpu_name=gpu_name,
        driver_visible=True,
        detection_error=detection_error,
    )


def resolve_device(requested: str | None) -> DeviceDecision:
    """Resolve ``requested`` ("auto"/"cpu"/"cuda"/"cuda:N") against real detection.

    - ``"auto"`` (or empty/None): CUDA if genuinely available, else CPU — the
      fallback reason is always recorded, never silent.
    - ``"cpu"``: always honored (explicit CPU request — not a fallback).
    - ``"cuda"``/``"cuda:N"``: honored only if CUDA is actually available;
      otherwise falls back to CPU with an explicit reason. Never claims GPU
      execution when it actually fell back.
    """
    detection = detect_gpu()
    normalized = (requested or _AUTO).strip().lower()

    if normalized == "cpu":
        return DeviceDecision(
            device="cpu",
            execution_device="cpu",
            requested_device="cpu",
            gpu_available=detection.gpu_available,
            gpu_name=detection.gpu_name,
            cuda_available=detection.cuda_available,
            device_reason="explicit cpu requested",
            fallback_reason=None,
        )

    wants_cuda = normalized == _AUTO or normalized.startswith("cuda")
    if wants_cuda and detection.cuda_available:
        device = "cuda" if normalized == _AUTO else normalized
        return DeviceDecision(
            device=device,
            execution_device=device,
            requested_device=normalized,
            gpu_available=True,
            gpu_name=detection.gpu_name,
            cuda_available=True,
            device_reason="CUDA GPU detected and selected",
            fallback_reason=None,
        )

    if wants_cuda and not detection.cuda_available:
        reason = (
            "CUDA was explicitly requested but is not available"
            if normalized != _AUTO
            else "no CUDA-capable GPU detected"
        )
        if detection.detection_error:
            reason = f"{reason}: {detection.detection_error}"
        return DeviceDecision(
            device="cpu",
            execution_device="cpu",
            requested_device=normalized,
            gpu_available=detection.gpu_available,
            gpu_name=detection.gpu_name,
            cuda_available=detection.cuda_available,
            device_reason="cpu fallback",
            fallback_reason=reason,
        )

    # Any other explicit device string (e.g. "mps") — honor it literally,
    # detection info is still attached for evidence, no fallback performed.
    return DeviceDecision(
        device=normalized,
        execution_device=normalized,
        requested_device=normalized,
        gpu_available=detection.gpu_available,
        gpu_name=detection.gpu_name,
        cuda_available=detection.cuda_available,
        device_reason="explicit device string honored",
        fallback_reason=None,
    )


__all__ = ["GpuDetection", "DeviceDecision", "detect_gpu", "resolve_device"]
