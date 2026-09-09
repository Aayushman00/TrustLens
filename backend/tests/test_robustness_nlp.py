"""Unit tests for robustness_nlp runner."""

from __future__ import annotations

import pytest

from app.inference.base import InferenceConfig, TaskType
from app.inference.errors import InferenceError
from app.probes.robustness_nlp import (
    TransformersCharSwapRunner,
    char_swap_attack,
    perturbation_succeeded,
)
from tests.fakes import FakeInferenceBackend


def test_char_swap_deterministic() -> None:
    import random

    rng1 = random.Random(42)
    rng2 = random.Random(42)
    text = "Hello World 123"
    assert char_swap_attack(text, max_changes=3, rng=rng1) == char_swap_attack(
        text, max_changes=3, rng=rng2
    )


def test_revision_passthrough_to_backend() -> None:
    backend = FakeInferenceBackend(predictions=[0, 1, 0, 1], num_labels=2)
    runner = TransformersCharSwapRunner(backend=backend)
    samples = [{"text": "hello world", "label": 0}] * 4
    result = runner.run(
        model_ref="org/model",
        model_revision="abc123",
        samples=samples,
        max_changes=2,
        seed=1,
        inference_config=InferenceConfig(task_type=TaskType.BINARY_CLASSIFICATION),
    )
    assert backend.load_calls[0]["revision"] == "abc123"
    assert result.n_evaluated == 4
    assert result.perturbation_coverage == 1.0


def test_zero_eligible_structured_insufficient() -> None:
    backend = FakeInferenceBackend(predictions=[0], num_labels=2)
    runner = TransformersCharSwapRunner(backend=backend)
    samples = [{"text": "x", "label": 9}] * 5
    result = runner.run(
        model_ref="org/model",
        model_revision=None,
        samples=samples,
        max_changes=1,
        seed=1,
    )
    assert result.insufficient_evidence is True
    assert result.n_label_compatible == 0


def test_model_load_failure_raises() -> None:
    backend = FakeInferenceBackend(
        load_error=InferenceError("MODEL_LOAD_ERROR", "boom"),
    )
    runner = TransformersCharSwapRunner(backend=backend)
    with pytest.raises(InferenceError):
        runner.run(
            model_ref="org/model",
            model_revision=None,
            samples=[{"text": "hello", "label": 0}],
            max_changes=1,
            seed=1,
        )


def test_perturbation_failed_for_no_alnum() -> None:
    assert perturbation_succeeded("", "x") is False
    assert perturbation_succeeded("!!!", "!!!") is False
    assert perturbation_succeeded("hello", "hxllo") is True


def test_label_incompatible_excluded_from_denominator() -> None:
    backend = FakeInferenceBackend(predictions=[0, 1, 0], num_labels=2)
    runner = TransformersCharSwapRunner(backend=backend)
    samples = [
        {"text": "hello", "label": 0},
        {"text": "world", "label": 1},
        {"text": "bad", "label": 5},
    ]
    result = runner.run(
        model_ref="org/model",
        model_revision=None,
        samples=samples,
        max_changes=1,
        seed=3,
    )
    assert result.n_samples == 3
    assert result.n_label_compatible == 2
    assert result.label_compat_fraction == pytest.approx(2 / 3)
