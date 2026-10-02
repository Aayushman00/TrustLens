"""L4 (round 3): binary fairness emits a pre-declared, bootstrap-gated risk.

Rule (tl-fairness-binary-v1.1), mirroring multiclass F-FAIR-PERF:
    b_g = P(Yhat=pos | g) - P(Y=pos | g)       over groups with n >= min_group_n
    excess_dpd_v2 = max_g b_g - min_g b_g
    FAIRNESS_RISK       iff point > EPSILON and bootstrap ci_lower > EPSILON
    DISPARITY_OBSERVED  iff point > EPSILON but ci_lower <= EPSILON
    NO_MATERIAL_DISPARITY iff point <= EPSILON
    INSUFFICIENT_EVIDENCE when < 2 groups reach min_group_n or no CI
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.probes.fairness_stats import (
    BINARY_METHODOLOGY_VERSION,
    BINARY_RISK_ID,
    EPSILON,
    binary_fairness_decision,
    excess_dpd_v1,
    excess_dpd_v2,
)
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    LabelMappingEntry,
    ModelLabelSnapshot,
)
from app.schemas.probe_config import ProbeConfigV1
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.scripts.compare_ground_truth import evidence_flag_one
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend
from tests.test_fairness_contract_v2 import _binary_csv_and_content

# --- excess DPD -------------------------------------------------------------


def _rows(spec: dict[str, tuple[int, int, int]]) -> tuple[list[int], list[int], list[str]]:
    """spec: group -> (n, n_label_pos, n_pred_pos); first n_label_pos rows are label=1,
    first n_pred_pos rows are predicted 1."""
    y_true: list[int] = []
    y_pred: list[int] = []
    groups: list[str] = []
    for g, (n, lab, pred) in spec.items():
        y_true += [1 if i < lab else 0 for i in range(n)]
        y_pred += [1 if i < pred else 0 for i in range(n)]
        groups += [g] * n
    return y_true, y_pred, groups


def test_excess_dpd_v2_is_spread_of_per_group_prediction_minus_label_rate() -> None:
    # a: pred 0.9 - label 0.9 = 0.0 ; b: pred 0.3 - label 0.1 = +0.2
    y_true, y_pred, g = _rows({"a": (100, 90, 90), "b": (100, 10, 30)})
    assert excess_dpd_v2(y_true, y_pred, g) == pytest.approx(0.2)


def test_excess_dpd_v2_sees_compressed_gap_that_v1_clips_to_zero() -> None:
    # Labels gap 0.8, predictions gap 0.5: v1 = max(0.5 - 0.8, 0) = 0;
    # v2 = b_b - b_a = 0.0 - (-0.3) = 0.3 (group a under-predicted).
    y_true, y_pred, g = _rows({"a": (100, 90, 60), "b": (100, 10, 10)})
    assert excess_dpd_v1(y_true, y_pred, g) == 0.0
    assert excess_dpd_v2(y_true, y_pred, g) == pytest.approx(0.3)


def test_excess_dpd_v1_preserves_original_formula() -> None:
    y_true, y_pred, g = _rows({"a": (100, 50, 90), "b": (100, 40, 10)})
    # DPD 0.8 - label gap 0.1 = 0.7
    assert excess_dpd_v1(y_true, y_pred, g) == pytest.approx(0.7)


def test_excess_dpd_v2_honours_positive_label_index() -> None:
    y_true, y_pred, g = _rows({"a": (100, 90, 90), "b": (100, 10, 30)})
    flipped = excess_dpd_v2([1 - y for y in y_true], [1 - y for y in y_pred], g, positive_label_index=0)
    assert flipped == pytest.approx(0.2)


# --- decision rule ------------------------------------------------------------


def test_epsilon_is_the_predeclared_methodology_floor() -> None:
    assert EPSILON == 0.02


@pytest.mark.parametrize(
    ("ci", "finding", "aspect", "risks"),
    [
        ({"point": 0.30, "ci_lower": 0.25, "ci_upper": 0.35}, "FAIRNESS_RISK", "risk_detected", [BINARY_RISK_ID]),
        ({"point": 0.015, "ci_lower": 0.0, "ci_upper": 0.03}, "NO_MATERIAL_DISPARITY", "no_material_risk", []),
        ({"point": 0.05, "ci_lower": 0.01, "ci_upper": 0.09}, "DISPARITY_OBSERVED", "disparity_observed", []),
        ({"point": 0.05, "ci_lower": EPSILON, "ci_upper": 0.09}, "DISPARITY_OBSERVED", "disparity_observed", []),
        ({"point": None, "ci_lower": None, "ci_upper": None}, "INSUFFICIENT_EVIDENCE", "not_scored", []),
        ({"point": 0.30, "ci_lower": None, "ci_upper": None}, "INSUFFICIENT_EVIDENCE", "not_scored", []),
    ],
    ids=["triggers", "within_epsilon", "ci_crosses_epsilon", "ci_lower_at_epsilon", "no_estimate", "no_ci"],
)
def test_binary_fairness_decision(ci: dict, finding: str, aspect: str, risks: list[str]) -> None:
    d = binary_fairness_decision(ci)
    assert (d["finding"], d["aspect_scoring"], d["risks_triggered"]) == (finding, aspect, risks)


def test_only_fairness_risk_is_flagged_by_the_frozen_rule() -> None:
    for ci, flagged in (
        ({"point": 0.3, "ci_lower": 0.25, "ci_upper": 0.35}, True),
        ({"point": 0.05, "ci_lower": 0.01, "ci_upper": 0.09}, False),
        ({"point": 0.01, "ci_lower": 0.0, "ci_upper": 0.02}, False),
    ):
        d = binary_fairness_decision(ci)
        assert evidence_flag_one("FAIRNESS", d, None) is flagged


# --- probe end to end ---------------------------------------------------------


def _run_probe(db_session: Any, spec: dict[str, tuple[int, int, int]], min_group_n: int = 50):
    lines = ["text,label,group"]
    preds: list[int] = []
    for g, (n, lab, pred) in spec.items():
        for i in range(n):
            lines.append(f"t{i}{g},{'pos' if i < lab else 'neg'},{g}")
            preds.append(1 if i < pred else 0)
    csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    store, content = _binary_csv_and_content(db_session, csv_bytes, row_count=len(preds))
    fc = FairnessContractV2(
        dataset_content_id=content.id,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
        min_group_n=min_group_n,
    )
    contract = EvaluationContractV2(
        model_ref="org/model",
        model_revision="a" * 40,
        resolved_model_sha="a" * 40,
        model_label_snapshot=ModelLabelSnapshot(num_labels=2, id2label={0: "NEG", 1: "POS"}),
        fairness=fc,
        robustness=None,
    )
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_config=ProbeConfigV1(),
        evidence_store=FakeEvidenceStore(),  # type: ignore[arg-type]
        evaluation_contract=contract,
        dataset_content_store=store,
        session=db_session,
    )
    return FairnessProbe(inference=FakeInferenceBackend(predictions=preds, num_labels=2)).run(ctx)


def test_clean_control_with_base_rate_gap_is_no_material_risk(db_session: Any) -> None:
    """Perfect predictions on data whose own label rates differ by 0.6:
    raw DPD is large, but the model adds nothing — no risk."""
    out = _run_probe(db_session, {"a": (400, 280, 280), "b": (400, 40, 40)})
    m = out.metric_values
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert m["demographic_parity_difference"] == pytest.approx(0.6)
    assert m["label_rate_gap"] == pytest.approx(0.6)
    assert m["excess_dpd_v2"] == 0.0
    assert m["fairness_finding"] == "NO_MATERIAL_DISPARITY"
    assert m["aspect_scoring"] == "no_material_risk"
    assert m["risks_triggered"] == []
    assert not evidence_flag_one("FAIRNESS", m, None)


def test_model_added_disparity_triggers_risk(db_session: Any) -> None:
    # Same label rates (0.5); model over-predicts positives for group b by 0.3.
    out = _run_probe(db_session, {"a": (400, 200, 200), "b": (400, 200, 320)})
    m = out.metric_values
    assert m["excess_dpd_v2"] == pytest.approx(0.3)
    assert m["excess_dpd_v2_ci"]["ci_lower"] > EPSILON
    assert m["fairness_finding"] == "FAIRNESS_RISK"
    assert m["aspect_scoring"] == "risk_detected"
    assert m["risks_triggered"] == [BINARY_RISK_ID]
    assert m["scored_risk_id"] is None
    assert evidence_flag_one("FAIRNESS", m, None)
    assert "not a finding that the model is unfair" in out.status_reason


def test_evidence_keeps_raw_metrics_cis_and_group_counts(db_session: Any) -> None:
    m = _run_probe(db_session, {"a": (400, 200, 200), "b": (400, 200, 320)}).metric_values
    for key in ("demographic_parity_difference", "equalized_odds_difference", "subgroup_f1_spread",
                "label_rate_gap", "excess_dpd", "excess_dpd_v1", "excess_dpd_v2",
                "dp_ci", "eo_ci", "f1_ci", "excess_dpd_v2_ci", "groups", "min_group_n_observed"):
        assert m[key] is not None, key
    assert m["excess_dpd"] == m["excess_dpd_v1"]
    assert m["methodology_version"] == BINARY_METHODOLOGY_VERSION
    assert m["fairness_rule"]["epsilon"] == EPSILON


def test_insufficient_group_size_abstains(db_session: Any) -> None:
    out = _run_probe(db_session, {"a": (200, 100, 100), "b": (20, 10, 18)}, min_group_n=50)
    m = out.metric_values
    assert out.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert m["fairness_finding"] == "INSUFFICIENT_EVIDENCE"
    assert m["aspect_scoring"] == "not_scored"
    assert m["risks_triggered"] == []
    assert m["demographic_parity_difference"] is not None  # evidence kept


def test_methodology_versions_bumped() -> None:
    assert CURRENT_METHODOLOGY_VERSION == "v5-binary-fairness-risk-2026"
    assert BINARY_METHODOLOGY_VERSION == "tl-fairness-binary-v1.1"
