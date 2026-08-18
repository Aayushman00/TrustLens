"""FairnessProbe + fairness_metrics unit tests (Phase 12)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.datasets.loader import DatasetLoadError, normalize_fairness_row
from app.db.enums import FriesDimension
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.probes.fairness_metrics import (
    compute_fairness_bundle,
    demographic_parity_difference,
    equalized_odds_difference,
    subgroup_f1_spread,
)
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import EvidenceStoreError
from tests.fakes import FakeEvidenceStore

_FIXTURE = Path(__file__).parent / "fixtures" / "fairness_toy.json"


def _load_toy() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


class _BoomStore(FakeEvidenceStore):
    def put_artifact(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise EvidenceStoreError("boom")


def _ctx(
    *,
    probe_config: ProbeConfigV1 | None = None,
    store: FakeEvidenceStore | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/any-model",
        model_metadata={"pipeline_tag": "text-classification"},
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=evidence,  # type: ignore[arg-type]
        model_revision="a" * 40,
    )
    return ctx, evidence


def test_toy_helpers_match_hand_calc() -> None:
    toy = _load_toy()
    y_true = [r["y_true"] for r in toy["rows"]]
    y_pred = [r["y_pred"] for r in toy["rows"]]
    sensitive = [r["sex"] for r in toy["rows"]]
    expected = toy["expected"]

    assert demographic_parity_difference(y_pred, sensitive) == pytest.approx(
        expected["demographic_parity_difference"]
    )
    assert equalized_odds_difference(y_true, y_pred, sensitive) == pytest.approx(
        expected["equalized_odds_difference"]
    )
    assert subgroup_f1_spread(y_true, y_pred, sensitive) == pytest.approx(
        expected["subgroup_f1_spread"], abs=1e-6
    )
    bundle = compute_fairness_bundle(y_true, y_pred, sensitive)
    assert bundle["demographic_parity_difference"] == pytest.approx(
        expected["demographic_parity_difference"]
    )
    assert bundle["groups"]["Male"]["n"] == 5
    assert bundle["groups"]["Female"]["f1"] == pytest.approx(0.666667, abs=1e-6)


def test_probe_toy_output_and_needs_human_review() -> None:
    toy = _load_toy()
    rows = [
        {
            "label": r["y_true"],
            "sensitive": r["sex"],
            "features": {"x": float(i)},
        }
        for i, r in enumerate(toy["rows"])
    ]
    y_pred = [r["y_pred"] for r in toy["rows"]]

    def _loader(*_a, **_k):
        return rows

    def _predictor(_rows, *, seed: int):
        return list(y_pred)

    ctx, store = _ctx(
        probe_config=ProbeConfigV1(
            datasets={"fairness": "adult_fairness"},
            extra={"seed": 1, "max_samples": 64, "min_group_n": 30},
        )
    )
    out = FairnessProbe(loader=_loader, predictor=_predictor).run(ctx)
    assert out.dimension == FriesDimension.FAIRNESS
    assert out.metric_values["proposed_mapping"] is False
    assert out.metric_values["needs_human_review"] is True
    assert out.metric_values["demographic_parity_difference"] == pytest.approx(0.4)
    assert out.metric_values["equalized_odds_difference"] == pytest.approx(0.5)
    assert out.metric_values["subgroup_f1_spread"] == pytest.approx(1 / 3, abs=1e-5)
    assert "insufficient_slice_size" in out.flags
    assert out.confidence < 0.85
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "fairness"


def test_thin_groups_flag_and_lower_confidence() -> None:
    rows = [
        {"label": 1, "sensitive": "A", "features": {"x": 1.0}},
        {"label": 0, "sensitive": "A", "features": {"x": 0.0}},
        {"label": 1, "sensitive": "B", "features": {"x": 1.0}},
        {"label": 0, "sensitive": "B", "features": {"x": 0.0}},
    ]

    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(
            datasets={"fairness": "adult_fairness"},
            extra={"min_group_n": 10},
        )
    )
    out = FairnessProbe(
        loader=lambda *_a, **_k: rows,
        predictor=lambda _r, *, seed: [1, 0, 0, 0],
    ).run(ctx)
    assert "insufficient_slice_size" in out.flags
    assert out.confidence == 0.75
    assert out.metric_values["needs_human_review"] is True


def test_unsupported_modality_skips_sentiment_fairness() -> None:
    ctx, store = _ctx(
        probe_config=ProbeConfigV1(datasets={"fairness": "sentiment_fairness"})
    )
    out = FairnessProbe().run(ctx)
    assert "unsupported_modality" in out.flags
    assert "metrics_skipped" in out.flags
    assert out.metric_values["demographic_parity_difference"] is None
    assert out.metric_values["proposed_mapping"] is False
    assert out.metric_values["needs_human_review"] is False
    assert len(store.puts) == 1


def test_unknown_dataset_skips() -> None:
    ctx, _ = _ctx(probe_config=ProbeConfigV1(datasets={"fairness": "no_such_pin"}))
    out = FairnessProbe().run(ctx)
    assert "dataset_load_failed" in out.flags
    assert out.metric_values["skip_reason"]


def test_loader_failure_soft_skip() -> None:
    def _boom(*_a, **_k):
        raise DatasetLoadError("failed to load adult_fairness: boom")

    ctx, store = _ctx(
        probe_config=ProbeConfigV1(datasets={"fairness": "adult_fairness"})
    )
    out = FairnessProbe(loader=_boom).run(ctx)
    assert "dataset_load_failed" in out.flags
    assert "metrics_skipped" in out.flags
    assert len(out.evidence_refs) == 1
    assert len(store.puts) == 1


def test_missing_sensitive_flag() -> None:
    def _boom(*_a, **_k):
        raise DatasetLoadError(
            "no usable fairness rows in adult_fairness (sensitive='sex')"
        )

    ctx, _ = _ctx()
    out = FairnessProbe(loader=_boom).run(ctx)
    assert "missing_sensitive_attribute" in out.flags
    assert "dataset_load_failed" in out.flags


def test_evidence_store_error_propagates() -> None:
    ctx, _ = _ctx(
        store=_BoomStore(),
        probe_config=ProbeConfigV1(datasets={"fairness": "adult_fairness"}),
    )
    with pytest.raises(EvidenceStoreError):
        FairnessProbe(
            loader=lambda *_a, **_k: [
                {"label": 1, "sensitive": "A", "features": {"x": 1.0}},
                {"label": 0, "sensitive": "B", "features": {"x": 0.0}},
            ],
            predictor=lambda _r, *, seed: [1, 0],
        ).run(ctx)


def test_normalize_fairness_row_adult_shape() -> None:
    row = {
        "age": 39,
        "workclass": "State-gov",
        "sex": "Male",
        "class": ">50K",
        "education": "Bachelors",
    }
    normalized = normalize_fairness_row(row, sensitive_attribute="sex")
    assert normalized is not None
    assert normalized["label"] == 1
    assert normalized["sensitive"] == "Male"
    assert "sex" not in normalized["features"]
    assert "class" not in normalized["features"]
    assert normalized["features"]["age"] == 39
