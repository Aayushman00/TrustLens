"""Phase 7 fairness-flow contract tests (A-G from the fairness-flow spec).

Covers: evaluation-create contract enforcement (admin proxy_lr gate, pairing
SHA mismatch -> 422) and FairnessProbe dispatch strictly on
``ctx.evaluation_contract`` (no implicit Adult fallback).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.enums import ProbeEvaluationStatus
from app.inference.errors import InferenceError, MODEL_LOAD_ERROR
from app.inference.pairing import get_pairing_by_id
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.schemas.evaluation_contract import EvaluationContractV1
from app.schemas.probe_config import ProbeConfigV1
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend

_HATEXPLAIN_MODEL = "Hate-speech-CNERG/bert-base-uncased-hatexplain"
_HATEXPLAIN_REV = "e487c81b768c7532bf474bd5e486dedea4cf3848"


def _hatexplain_contract(*, model_revision: str = _HATEXPLAIN_REV) -> EvaluationContractV1:
    pairing = get_pairing_by_id("hatexplain_bert_v1")
    assert pairing is not None
    return EvaluationContractV1(
        kind="pairing",
        pairing_id=pairing.id,
        dataset_key=pairing.dataset,
        dataset_revision=pairing.dataset_revision,
        model_ref=_HATEXPLAIN_MODEL,
        model_revision=model_revision,
        task_type=pairing.task_type,
        label_space=pairing.output_decoding.label_space,
        modality=pairing.modality,
        input_adapter=pairing.input_adapter,
    )


def _ctx(
    *,
    evaluation_contract: EvaluationContractV1 | None,
    model_ref: str = "org/any-model",
    model_revision: str | None = "a" * 40,
    probe_config: ProbeConfigV1 | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    store = FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref=model_ref,
        model_revision=model_revision,
        model_metadata={},
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=store,  # type: ignore[arg-type]
        evaluation_contract=evaluation_contract,
    )
    return ctx, store


# --- A/B: no pairing / no contract at all -> NOT_APPLICABLE, never Adult ----


def test_no_contract_is_not_applicable_and_never_calls_lr() -> None:
    """B: missing evaluation contract -> NOT_APPLICABLE; the LR predictor is never invoked."""

    def _boom_predictor(*_a, **_k):
        raise AssertionError("Adult LR predictor must not be called without a contract")

    ctx, store = _ctx(evaluation_contract=None)
    out = FairnessProbe(predictor=_boom_predictor).run(ctx)

    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert out.metric_values["fairness_mode"] == "not_applicable"
    assert "no_fairness_contract" in out.flags
    assert len(store.puts) == 1


def test_documentation_only_contract_is_not_applicable() -> None:
    """A: an ordinary evaluation (documentation_only) never silently runs Adult."""

    def _boom_predictor(*_a, **_k):
        raise AssertionError("Adult LR predictor must not be called for documentation_only")

    contract = EvaluationContractV1(
        kind="documentation_only",
        model_ref="org/any-model",
        model_revision="a" * 40,
    )
    ctx, _ = _ctx(evaluation_contract=contract)
    out = FairnessProbe(predictor=_boom_predictor).run(ctx)

    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert out.metric_values["fairness_mode"] == "not_applicable"


def test_registry_contract_is_not_applicable_for_fairness() -> None:
    """A registry (Robustness-only) contract does not authorize Fairness either."""

    def _boom_predictor(*_a, **_k):
        raise AssertionError("Adult LR predictor must not be called for a registry contract")

    contract = EvaluationContractV1(
        kind="registry",
        dataset_key="ag_news_robustness",
        dataset_revision="x",
        model_ref="org/any-model",
        model_revision="a" * 40,
    )
    ctx, _ = _ctx(evaluation_contract=contract)
    out = FairnessProbe(predictor=_boom_predictor).run(ctx)

    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert out.metric_values["fairness_mode"] == "not_applicable"


# --- C: explicit admin proxy_lr + adult_fairness still returns PROXY -------


def test_explicit_proxy_lr_contract_returns_proxy() -> None:
    contract = EvaluationContractV1(
        kind="proxy_lr",
        dataset_key="adult_fairness",
        model_ref="org/any-model",
        model_revision="a" * 40,
    )
    rows = [
        {"label": 1, "sensitive": "A", "features": {"x": 1.0}},
        {"label": 0, "sensitive": "B", "features": {"x": 0.0}},
    ]
    ctx, _ = _ctx(evaluation_contract=contract)
    out = FairnessProbe(
        loader=lambda *_a, **_k: rows,
        predictor=lambda _r, *, seed: [1, 0],
    ).run(ctx)

    assert out.status is ProbeEvaluationStatus.PROXY
    assert out.metric_values["fairness_mode"] == "proxy_lr"
    assert out.metric_values["predictor"] == "sklearn_logistic_regression"
    assert out.metric_values["evaluation_class"] == "proxy_lr"


def test_proxy_lr_contract_with_wrong_dataset_key_is_not_applicable() -> None:
    """proxy_lr must be explicit adult_fairness — never inferred from a different key."""
    contract = EvaluationContractV1(
        kind="proxy_lr",
        dataset_key="not_adult_fairness",
        model_ref="org/any-model",
        model_revision="a" * 40,
    )
    ctx, _ = _ctx(evaluation_contract=contract)
    out = FairnessProbe(
        predictor=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("must not call LR for a non-adult_fairness proxy_lr contract")
        )
    ).run(ctx)
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE


# --- E: pairing path calls LocalHFBackend.load(model_ref, revision=exact) --


def test_pairing_path_loads_exact_contract_model_ref_and_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"text": "hello world", "label": 1, "sensitive": "GroupA"},
        {"text": "bad post", "label": 0, "sensitive": "GroupB"},
    ]
    monkeypatch.setattr(
        "app.probes.fairness.load_pairing_subset",
        lambda *_a, **_k: (rows, 0),
    )
    fake = FakeInferenceBackend(predictions=[1, 2], num_labels=3)
    contract = _hatexplain_contract()
    ctx, _ = _ctx(
        evaluation_contract=contract,
        model_ref=_HATEXPLAIN_MODEL,
        model_revision=_HATEXPLAIN_REV,
    )
    out = FairnessProbe(inference=fake).run(ctx)

    assert fake.load_calls[0]["model_ref"] == contract.model_ref
    assert fake.load_calls[0]["revision"] == contract.model_revision
    assert out.metric_values["fairness_mode"] == "model_faithful"
    assert out.metric_values["inference_executed"] is True


# --- F: model load/inference failure never claims model_faithful -----------


def test_pairing_load_failure_does_not_claim_model_faithful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"text": "hello world", "label": 1, "sensitive": "GroupA"},
        {"text": "bad post", "label": 0, "sensitive": "GroupB"},
    ]
    monkeypatch.setattr(
        "app.probes.fairness.load_pairing_subset",
        lambda *_a, **_k: (rows, 0),
    )
    fake = FakeInferenceBackend(
        load_error=InferenceError(MODEL_LOAD_ERROR, "could not load pinned checkpoint"),
    )
    contract = _hatexplain_contract()
    ctx, _ = _ctx(
        evaluation_contract=contract,
        model_ref=_HATEXPLAIN_MODEL,
        model_revision=_HATEXPLAIN_REV,
    )
    out = FairnessProbe(inference=fake).run(ctx)

    assert out.status is ProbeEvaluationStatus.FAILED
    assert out.metric_values["fairness_mode"] != "model_faithful"
    assert "predictor_failed" in out.flags


# --- G: HateXplain pairing is Fairness model-faithful only; no Robustness --


def test_hatexplain_pairing_is_fairness_model_faithful_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"text": "hello world", "label": 1, "sensitive": "GroupA"},
        {"text": "bad post", "label": 0, "sensitive": "GroupB"},
    ]
    monkeypatch.setattr(
        "app.probes.fairness.load_pairing_subset",
        lambda *_a, **_k: (rows, 0),
    )
    fake = FakeInferenceBackend(predictions=[1, 2], num_labels=3)
    contract = _hatexplain_contract()
    ctx, _ = _ctx(
        evaluation_contract=contract,
        model_ref=_HATEXPLAIN_MODEL,
        model_revision=_HATEXPLAIN_REV,
    )
    out = FairnessProbe(inference=fake).run(ctx)

    assert out.metric_values["fairness_mode"] == "model_faithful"
    assert out.metric_values["pairing_id"] == "hatexplain_bert_v1"
    # Robustness compat is a separate, untouched contract — no robustness
    # dataset key/adapter is fabricated on the fairness contract itself.
    assert contract.dataset_key == "hatexplain_fairness"


# --- A/C/D at the evaluation-create API layer -------------------------------


def _create_model(api_client: TestClient, headers: dict[str, str], *, revision: str) -> int:
    resp = api_client.post(
        "/v1/models",
        json={"hf_repo_id": _HATEXPLAIN_MODEL, "revision": revision},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_researcher_evaluation_with_no_contract_selection_defaults_documentation_only(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """A: no pairing/dataset/kind selected -> documentation_only, never proxy_lr/Adult."""
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/no-contract-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    contract = created.json()["probe_config"]["evaluation_contract"]
    assert contract["kind"] == "documentation_only"


def test_proxy_lr_has_no_role_gate(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Single-user local instance — proxy_lr has no admin-only gate."""
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/proxy-forbidden-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model.json()["id"],
            "evaluation_mode": "AI_AUTONOMOUS",
            "contract_kind": "proxy_lr",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["probe_config"]["evaluation_contract"]["kind"] == "proxy_lr"


def test_admin_proxy_lr_contract_persisted(
    api_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """C: an admin-created proxy_lr evaluation persists kind=proxy_lr/adult_fairness."""
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/proxy-admin-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model.json()["id"],
            "evaluation_mode": "AI_AUTONOMOUS",
            "contract_kind": "proxy_lr",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    contract = created.json()["probe_config"]["evaluation_contract"]
    assert contract["kind"] == "proxy_lr"
    assert contract["dataset_key"] == "adult_fairness"


def test_pairing_sha_mismatch_rejected_422(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """D: a pairing_id whose model_revision disagrees with the pinned model is rejected."""
    model_id = _create_model(api_client, auth_headers, revision="0" * 40)
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "pairing_id": "hatexplain_bert_v1",
        },
        headers=auth_headers,
    )
    assert created.status_code == 422, created.text


def test_pairing_matching_revision_accepted(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Sanity check for D: the exact pinned revision is accepted (kind=pairing)."""
    model_id = _create_model(api_client, auth_headers, revision=_HATEXPLAIN_REV)
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "pairing_id": "hatexplain_bert_v1",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    contract = created.json()["probe_config"]["evaluation_contract"]
    assert contract["kind"] == "pairing"
    assert contract["pairing_id"] == "hatexplain_bert_v1"
    assert contract["model_revision"] == _HATEXPLAIN_REV


def test_ambiguous_pairing_and_dataset_key_rejected_422(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    model_id = _create_model(api_client, auth_headers, revision=_HATEXPLAIN_REV)
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "pairing_id": "hatexplain_bert_v1",
            "dataset_key": "ag_news_robustness",
        },
        headers=auth_headers,
    )
    assert created.status_code == 422, created.text
