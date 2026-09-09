"""_extract_execution_metadata: pipeline-level device evidence capture.

Pure unit tests against the probe outputs already returned by run_all_probes
— no new device logic, just verifying the pipeline reads the existing
per-probe ``inference`` block without fabricating or dropping data.
"""

from __future__ import annotations

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeOutput
from app.tasks.evaluate_pipeline import _extract_execution_metadata


def _output(dimension: FriesDimension, metric_values: dict) -> ProbeOutput:
    return ProbeOutput(
        dimension=dimension,
        metric_values=metric_values,
        confidence=0.8,
        evidence_refs=[],
        status=ProbeEvaluationStatus.EVALUATED,
    )


def test_no_probe_ran_inference_returns_none() -> None:
    outputs = [
        _output(FriesDimension.FAIRNESS, {"fairness_mode": "not_evaluated"}),
        _output(FriesDimension.ROBUSTNESS, {"probe_status": "NOT_APPLICABLE"}),
        _output(FriesDimension.INTEGRITY, {}),
    ]
    assert _extract_execution_metadata(outputs) is None


def test_fairness_inference_block_is_captured_verbatim() -> None:
    inference = {
        "execution_device": "cuda",
        "gpu_available": True,
        "gpu_name": "NVIDIA GeForce RTX 4060",
        "cuda_available": True,
        "inference_backend": "local_hf",
        "device_reason": "CUDA GPU detected and selected",
        "fallback_reason": None,
    }
    outputs = [
        _output(FriesDimension.FAIRNESS, {"fairness_mode": "model_faithful", "inference": inference}),
        _output(FriesDimension.ROBUSTNESS, {"probe_status": "NOT_APPLICABLE"}),
    ]
    assert _extract_execution_metadata(outputs) == inference


def test_robustness_inference_used_when_fairness_did_not_run_inference() -> None:
    inference = {
        "execution_device": "cpu",
        "gpu_available": False,
        "gpu_name": None,
        "cuda_available": False,
        "inference_backend": "local_hf",
        "device_reason": "cpu fallback",
        "fallback_reason": "no CUDA-capable GPU detected",
    }
    outputs = [
        _output(FriesDimension.FAIRNESS, {"fairness_mode": "not_evaluated"}),
        _output(FriesDimension.ROBUSTNESS, {"stub": False, "inference": inference}),
    ]
    assert _extract_execution_metadata(outputs) == inference


def test_never_fabricates_a_device_when_inference_key_missing_entirely() -> None:
    outputs = [_output(FriesDimension.FAIRNESS, {"fairness_mode": "not_evaluated"})]
    assert _extract_execution_metadata(outputs) is None
