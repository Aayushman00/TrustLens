"""Fairness probe pairing path tests (fake backend, network-free)."""

from __future__ import annotations

import uuid

import pytest

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.schemas.probe_config import ProbeConfigV1
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend

_HATEXPLAIN_MODEL = "Hate-speech-CNERG/bert-base-uncased-hatexplain"
_HATEXPLAIN_REV = "e487c81b768c7532bf474bd5e486dedea4cf3848"


def _ctx(model_ref: str, revision: str | None = None) -> tuple[ProbeContext, FakeEvidenceStore]:
    store = FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref=model_ref,
        model_revision=revision,
        model_metadata={"pipeline_tag": "text-classification"},
        probe_config=ProbeConfigV1(datasets={"fairness": "hatexplain_fairness"}),
        evidence_store=store,  # type: ignore[arg-type]
    )
    return ctx, store


def test_pairing_faithful_fake_backend_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "text": "hello world",
            "label": 1,
            "sensitive": "GroupA",
        },
        {
            "text": "bad post",
            "label": 0,
            "sensitive": "GroupB",
        },
    ]
    fake = FakeInferenceBackend(predictions=[1, 2], num_labels=3)

    def _fake_load(*_a, **_k):
        return rows, 0

    monkeypatch.setattr(
        "app.probes.fairness.load_pairing_subset",
        lambda *_a, **_k: _fake_load(),
    )

    ctx, _ = _ctx(_HATEXPLAIN_MODEL, _HATEXPLAIN_REV)
    out = FairnessProbe(inference=fake).run(ctx)

    assert out.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert out.metric_values["fairness_mode"] == "model_faithful"
    assert out.metric_values["pairing_id"] == "hatexplain_bert_v1"
    assert out.metric_values["adapter_id"] == "hatexplain_post_tokens_v1"
    assert out.metric_values["n_evaluated"] == 2
    assert out.metric_values["sensitive_attribute"] == "target_community"
    assert out.metric_values["demographic_parity_difference"] == "NOT_APPLICABLE"
    assert fake.load_calls[0]["model_ref"] == _HATEXPLAIN_MODEL
    assert fake.load_calls[0]["revision"] == _HATEXPLAIN_REV
    assert len(fake.predict_calls) == 1
    assert fake.predict_calls[0] == ["hello world", "bad post"]


def test_unpaired_model_not_applicable_on_nlp_dataset() -> None:
    ctx, _ = _ctx("org/unpaired-model", "a" * 40)
    out = FairnessProbe(
        loader=lambda *_a, **_k: [],
        predictor=lambda _r, *, seed: [],
    ).run(ctx)
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
