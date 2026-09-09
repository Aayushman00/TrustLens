"""Phase 7 robustness-flow contract tests (D-K from the robustness-flow spec;
A/B/C/H are covered directly in test_robustness_probe.py).

Covers: RobustnessProbe dispatch strictly on ``ctx.evaluation_contract`` (no
``probe_config.datasets.robustness`` override, no silent
``resolve_robustness_compat`` auto-selection), frozen model identity reaching
``LocalHFBackend``, evidence identity, and HateXplain remaining Fairness-only.
"""

from __future__ import annotations

import uuid

import pytest

from app.datasets.registry import get_dataset_spec
from app.db.enums import ProbeEvaluationStatus
from app.inference.pairing import get_pairing_by_id
from app.probes.base import ProbeContext
from app.probes.robustness import RobustnessProbe
from app.probes.robustness_nlp import RobustnessRunResult, TransformersCharSwapRunner
from app.schemas.evaluation_contract import EvaluationContractV1
from app.schemas.probe_config import ProbeConfigV1
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend

_AG_NEWS_MODEL = "textattack/bert-base-uncased-ag-news"
_AG_NEWS_REV = "fe417ad660b1657142f66353a184dc0c7e6d2e48"
_SST2_MODEL = "textattack/bert-base-uncased-SST-2"
_SST2_REV = "95f0f6f859b35c8ff0863ae3cd4e2dbc702c0ae2"

_HATEXPLAIN_MODEL = "Hate-speech-CNERG/bert-base-uncased-hatexplain"
_HATEXPLAIN_REV = "e487c81b768c7532bf474bd5e486dedea4cf3848"

_TEXT_META = {
    "pipeline_tag": "text-classification",
    "task": "text-classification",
    "tags": ["text-classification"],
}


def _registry_contract(dataset_key: str, model_ref: str, model_revision: str) -> EvaluationContractV1:
    spec = get_dataset_spec(dataset_key)
    return EvaluationContractV1(
        kind="registry",
        dataset_key=dataset_key,
        dataset_revision=spec.revision,
        model_ref=model_ref,
        model_revision=model_revision,
        task_type=spec.task_type,
        modality=spec.modality,
    )


def _hatexplain_pairing_contract() -> EvaluationContractV1:
    pairing = get_pairing_by_id("hatexplain_bert_v1")
    assert pairing is not None
    return EvaluationContractV1(
        kind="pairing",
        pairing_id=pairing.id,
        dataset_key=pairing.dataset,
        dataset_revision=pairing.dataset_revision,
        model_ref=_HATEXPLAIN_MODEL,
        model_revision=_HATEXPLAIN_REV,
        task_type=pairing.task_type,
        label_space=pairing.output_decoding.label_space,
        modality=pairing.modality,
        input_adapter=pairing.input_adapter,
    )


def _ctx(
    *,
    evaluation_contract: EvaluationContractV1 | None,
    model_ref: str,
    model_revision: str | None,
    metadata: dict | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    store = FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref=model_ref,
        model_revision=model_revision,
        model_metadata=metadata or _TEXT_META,
        probe_config=ProbeConfigV1(),
        evidence_store=store,  # type: ignore[arg-type]
        evaluation_contract=evaluation_contract,
    )
    return ctx, store


class _FakeRunner:
    def __init__(self, result: RobustnessRunResult):
        self.result = result
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _rows(n: int, *, clean_acc: float, robust_acc: float) -> list[dict]:
    clean_correct = int(round(clean_acc * n))
    robust_correct = int(round(robust_acc * n))
    out = []
    for i in range(n):
        label = i % 2
        yc = label if i < clean_correct else (1 - label)
        yr = label if i < robust_correct else (1 - label)
        out.append(
            {"label": label, "y_hat_clean": yc, "y_hat_robust": yr, "text": f"t{i}", "attacked_text": f"x{i}"}
        )
    return out


def _result(n: int, *, clean_acc: float, robust_acc: float) -> RobustnessRunResult:
    aligned = _rows(n, clean_acc=clean_acc, robust_acc=robust_acc)
    return RobustnessRunResult(
        clean_accuracy=clean_acc,
        robust_accuracy=robust_acc,
        attack_success_rate=max(0.0, clean_acc - robust_acc),
        n_samples=n,
        n_evaluated=n,
        n_label_compatible=n,
        n_successfully_perturbed=n,
        n_perturb_failed=0,
        perturbation_coverage=1.0,
        label_compat_fraction=1.0,
        aligned_rows=aligned,
    )


# --- D/E: explicit AG News / SST-2 contract uses that exact dataset --------


@pytest.mark.parametrize(
    "dataset_key,model_ref,model_revision",
    [
        ("ag_news_robustness", _AG_NEWS_MODEL, _AG_NEWS_REV),
        ("sst2_robustness", _SST2_MODEL, _SST2_REV),
    ],
)
def test_explicit_contract_uses_that_exact_dataset(
    monkeypatch: pytest.MonkeyPatch,
    dataset_key: str,
    model_ref: str,
    model_revision: str,
) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda logical_key, **_k: [{"text": "hello world", "label": 0}] * 200
        if logical_key == dataset_key
        else (_ for _ in ()).throw(AssertionError(f"wrong dataset requested: {logical_key}")),
    )
    contract = _registry_contract(dataset_key, model_ref, model_revision)
    ctx, _ = _ctx(evaluation_contract=contract, model_ref=model_ref, model_revision=model_revision)
    runner = _FakeRunner(_result(200, clean_acc=0.9, robust_acc=0.6))
    out = RobustnessProbe(runner=runner).run(ctx)

    assert out.status is ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["dataset"]["logical_key"] == dataset_key
    assert out.metric_values["dataset_key"] == dataset_key


# --- F: no silent AG News/SST-2 auto-selection ------------------------------


def test_model_matching_compat_entry_without_explicit_dataset_key_is_not_applicable() -> None:
    """Even though this exact model+revision has an approved compat pin, no
    dataset is auto-selected unless the contract explicitly names it."""
    contract = EvaluationContractV1(
        kind="registry",
        dataset_key=None,
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
    )
    ctx, _ = _ctx(evaluation_contract=contract, model_ref=_AG_NEWS_MODEL, model_revision=_AG_NEWS_REV)
    out = RobustnessProbe(runner=_FakeRunner(_result(200, clean_acc=0.9, robust_acc=0.6))).run(ctx)
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert "no_compatible_dataset" in out.flags
    assert out.metric_values["dataset_key"] is None


# --- G: frozen model_revision reaches LocalHFBackend, not a drifted ctx one -


def test_frozen_contract_identity_reaches_backend_not_drifted_ctx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    contract = _registry_contract("ag_news_robustness", _AG_NEWS_MODEL, _AG_NEWS_REV)
    # Simulate ctx.model_ref/model_revision having drifted from the frozen
    # contract (e.g. a re-imported Model row) — the actual load must still
    # use the frozen contract identity, never this drifted ctx value.
    drifted_ref = "org/drifted-live-model"
    drifted_rev = "f" * 40
    ctx, _ = _ctx(evaluation_contract=contract, model_ref=drifted_ref, model_revision=drifted_rev)

    fake_backend = FakeInferenceBackend(predictions=[0], num_labels=4)
    runner = TransformersCharSwapRunner(backend=fake_backend)
    out = RobustnessProbe(runner=runner).run(ctx)

    assert fake_backend.load_calls, "backend.load was never called"
    assert fake_backend.load_calls[0]["model_ref"] == _AG_NEWS_MODEL
    assert fake_backend.load_calls[0]["revision"] == _AG_NEWS_REV
    assert fake_backend.load_calls[0]["model_ref"] != drifted_ref
    assert fake_backend.load_calls[0]["revision"] != drifted_rev
    assert out.status in (ProbeEvaluationStatus.EVALUATED, ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE)


# --- I: robustness evidence records exact dataset/model identity -----------


def test_evidence_records_frozen_contract_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    contract = _registry_contract("ag_news_robustness", _AG_NEWS_MODEL, _AG_NEWS_REV)
    ctx, store = _ctx(evaluation_contract=contract, model_ref=_AG_NEWS_MODEL, model_revision=_AG_NEWS_REV)
    runner = _FakeRunner(_result(200, clean_acc=0.9, robust_acc=0.6))
    out = RobustnessProbe(runner=runner).run(ctx)

    assert out.metric_values["model_ref"] == contract.model_ref
    assert out.metric_values["model_revision"] == contract.model_revision
    assert out.metric_values["dataset_key"] == contract.dataset_key
    assert out.metric_values["dataset_revision"] == contract.dataset_revision
    assert out.metric_values["task_type"] == contract.task_type
    assert out.metric_values["evaluation_class"] == "registry"
    assert out.metric_values["inference_executed"] is True

    key = store.puts[0].uri.split(f"s3://{store.bucket}/", 1)[1]
    import json

    artifact = json.loads(store.objects[key].decode("utf-8"))
    assert artifact["model_revision"] == contract.model_revision
    assert artifact["dataset_key"] == contract.dataset_key
    assert artifact["evaluation_class"] == "registry"


# --- J: HateXplain Fairness pairing does not cause Robustness to run -------


def test_hatexplain_pairing_contract_does_not_run_robustness() -> None:
    contract = _hatexplain_pairing_contract()
    ctx, _ = _ctx(
        evaluation_contract=contract,
        model_ref=_HATEXPLAIN_MODEL,
        model_revision=_HATEXPLAIN_REV,
    )
    out = RobustnessProbe(runner=_FakeRunner(_result(200, clean_acc=0.9, robust_acc=0.6))).run(ctx)
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert "no_compatible_dataset" in out.flags
    assert out.metric_values["dataset_key"] is None
    assert out.metric_values["evaluation_class"] == "pairing"


# --- K: existing gates/statistics remain reachable and unchanged -----------


def test_clean_floor_gate_still_fires_through_contract_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G-ROB-CLEAN-FLOOR (unchanged, see test_robustness_eval.py for the pure
    math) must still be reachable end-to-end through the new contract-driven
    entrypoint — this only proves wiring, not new gate behavior."""
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    contract = _registry_contract("ag_news_robustness", _AG_NEWS_MODEL, _AG_NEWS_REV)
    ctx, _ = _ctx(evaluation_contract=contract, model_ref=_AG_NEWS_MODEL, model_revision=_AG_NEWS_REV)
    runner = _FakeRunner(_result(200, clean_acc=0.10, robust_acc=0.05))
    out = RobustnessProbe(runner=runner).run(ctx)
    assert "G-ROB-CLEAN-FLOOR" in out.metric_values["reliability"]["failed_gates"]
