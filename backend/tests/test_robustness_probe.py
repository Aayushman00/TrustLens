"""RobustnessProbe unit tests — mocked runner, no torch/Hub (Phase 11)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext
from app.probes.robustness import RobustnessProbe
from app.probes.robustness_nlp import RobustnessRunResult
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import EvidenceStoreError
from tests.fakes import FakeEvidenceStore


class _FakeRunner:
    def __init__(self, result: RobustnessRunResult | None = None, *, error: Exception | None = None):
        self.result = result or RobustnessRunResult(
            clean_accuracy=0.9,
            robust_accuracy=0.6,
            attack_success_rate=0.3,
            n_samples=64,
            n_evaluated=64,
        )
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> RobustnessRunResult:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _BoomStore(FakeEvidenceStore):
    def put_artifact(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise EvidenceStoreError("boom")


def _ctx(
    *,
    metadata: dict | None = None,
    probe_config: ProbeConfigV1 | None = None,
    store: FakeEvidenceStore | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/text-clf",
        model_metadata=metadata
        or {
            "pipeline_tag": "text-classification",
            "task": "text-classification",
            "tags": ["text-classification"],
        },
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=evidence,  # type: ignore[arg-type]
        model_revision="a" * 40,
    )
    return ctx, evidence


def test_fake_runner_accuracies_and_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _FakeRunner()
    samples = [{"text": "hello", "label": 0}] * 16

    def _fake_load(*_a, **_k):
        return samples

    monkeypatch.setattr("app.probes.robustness.load_pinned_subset", _fake_load)
    ctx, store = _ctx(
        probe_config=ProbeConfigV1(
            attack_budget=0.03,
            datasets={"robustness": "ag_news_robustness"},
            extra={"seed": 42, "max_samples": 32},
        )
    )
    out = RobustnessProbe(runner=runner).run(ctx)
    assert out.dimension == FriesDimension.ROBUSTNESS
    assert out.metric_values["proposed_mapping"] is False
    assert out.metric_values["clean_accuracy"] == 0.9
    assert out.metric_values["robust_accuracy"] == 0.6
    assert out.metric_values["degradation_ratio"] == pytest.approx(0.6667, rel=1e-3)
    assert out.metric_values["attack"] == "char_swap"
    assert out.metric_values["seed"] == 42
    assert out.metric_values["epsilon"] == 0.03
    assert out.metric_values["max_changes"] == 3
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "robustness"
    assert runner.calls and runner.calls[0]["max_changes"] == 3
    assert runner.calls[0]["seed"] == 42


def test_unsupported_modality_skips() -> None:
    ctx, store = _ctx(metadata={"pipeline_tag": "fill-mask", "tags": []})
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert "unsupported_modality" in out.flags
    assert "attack_skipped" in out.flags
    assert out.confidence <= 0.5
    assert out.metric_values["clean_accuracy"] is None
    assert out.metric_values["proposed_mapping"] is False
    assert len(out.evidence_refs) == 1
    assert len(store.puts) == 1


def test_vision_dataset_unsupported() -> None:
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(datasets={"robustness": "cifar10_subset"}),
    )
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert "unsupported_modality" in out.flags
    assert out.metric_values["dataset"]["logical_key"] == "cifar10_subset"


def test_attack_budget_flows_into_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "x", "label": 0}] * 10,
    )
    ctx, _ = _ctx(probe_config=ProbeConfigV1(attack_budget=0.05, extra={"seed": 7}))
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert out.metric_values["epsilon"] == 0.05
    assert out.metric_values["max_changes"] == 5
    assert out.metric_values["seed"] == 7


def test_evidence_store_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "x", "label": 0}] * 10,
    )
    ctx, _ = _ctx(store=_BoomStore())
    with pytest.raises(EvidenceStoreError):
        RobustnessProbe(runner=_FakeRunner()).run(ctx)
