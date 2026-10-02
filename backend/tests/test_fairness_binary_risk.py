"""L4.1 (round 3): binary fairness risk from the equal-opportunity (TPR) gap.

Rule (tl-fairness-binary-v1.2). The tl-fairness-binary-v1.1 trigger
(excess_dpd_v2) was an exploratory candidate, rejected after inspection
because it depends on group base rates; see
docs/superpowers/plans/2026-10-03-round3-L4.1-eod-fairness-risk.md.

    eligible groups: n >= min_group_n
    every eligible group needs >= 1 positive label (TPR = TP / (TP + FN))
    EOD = max_g TPR_g - min_g TPR_g          over eligible groups
    CI  = bootstrap percentile 95% CI of EOD (B=1000, contract seed)
    FAIRNESS_RISK         EOD > EPSILON and ci_lower > EPSILON
    DISPARITY_OBSERVED    EOD > EPSILON and ci_lower <= EPSILON
    NO_MATERIAL_DISPARITY EOD <= EPSILON
    INSUFFICIENT_EVIDENCE < 2 eligible groups, too few positives, or no CI
    G-FAIR-CI-WIDE        EOD CI width > CI_WIDE_THRESHOLD -> mapping_blocked
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.probes.fairness_metrics import equal_opportunity_difference
from app.probes.fairness_stats import (
    BINARY_METHODOLOGY_VERSION,
    BINARY_RISK_ID,
    EPSILON,
    binary_fairness_decision,
    excess_dpd_v1,
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

# Group spec: group -> (n, n_label_pos, n_true_pos, n_false_pos). Rows are
# laid out positives first; the first n_true_pos positives and the first
# n_false_pos negatives are predicted positive.


def _rows(spec: dict[str, tuple[int, int, int, int]]) -> tuple[list[int], list[int], list[str]]:
    y_true: list[int] = []
    y_pred: list[int] = []
    groups: list[str] = []
    for g, (n, pos, tp, fp) in spec.items():
        for i in range(n):
            is_pos = i < pos
            y_true.append(int(is_pos))
            y_pred.append(int(i < tp if is_pos else (i - pos) < fp))
            groups.append(g)
    return y_true, y_pred, groups


# --- EOD ------------------------------------------------------------------------


def test_eod_two_groups_is_absolute_tpr_gap() -> None:
    # TPR a = 80/100, TPR b = 50/100
    y_true, y_pred, g = _rows({"a": (200, 100, 80, 0), "b": (200, 100, 50, 0)})
    assert equal_opportunity_difference(y_true, y_pred, g) == pytest.approx(0.3)


def test_eod_multi_group_is_max_minus_min_tpr() -> None:
    y_true, y_pred, g = _rows({"a": (100, 50, 45, 0), "b": (100, 50, 30, 0), "c": (100, 50, 40, 0)})
    assert equal_opportunity_difference(y_true, y_pred, g) == pytest.approx(0.9 - 0.6)


def test_eod_honours_positive_label_index() -> None:
    y_true, y_pred, g = _rows({"a": (200, 100, 80, 0), "b": (200, 100, 50, 0)})
    flipped = equal_opportunity_difference([1 - y for y in y_true], [1 - y for y in y_pred], g, positive_label_index=0)
    # Label index 0 on the flipped encoding is the original positive class.
    assert flipped == pytest.approx(0.3)
    # Index 1 on the flipped encoding is the original negative class: TPR = 1 - FPR = 1.0 both.
    assert equal_opportunity_difference([1 - y for y in y_true], [1 - y for y in y_pred], g) == pytest.approx(0.0)


def test_eod_undefined_without_positives() -> None:
    y_true, y_pred, g = _rows({"a": (100, 50, 40, 0), "b": (100, 0, 0, 5)})
    with pytest.raises(ValueError, match="positive"):
        equal_opportunity_difference(y_true, y_pred, g)


def test_large_base_rate_gap_and_dpd_with_small_eod() -> None:
    # Same TPR (0.5) and FPR (0) in both groups; base rates 0.8 vs 0.1.
    y_true, y_pred, g = _rows({"a": (200, 160, 80, 0), "b": (200, 20, 10, 0)})
    assert equal_opportunity_difference(y_true, y_pred, g) == pytest.approx(0.0)
    assert excess_dpd_v1(y_true, y_pred, g) == 0.0  # DPD 0.35 < label gap 0.7


# --- decision rule --------------------------------------------------------------


def test_epsilon_is_the_methodology_wide_tolerance() -> None:
    assert EPSILON == 0.02


@pytest.mark.parametrize(
    ("ci", "finding", "aspect", "risks"),
    [
        ({"point": 0.30, "ci_lower": 0.25, "ci_upper": 0.35}, "FAIRNESS_RISK", "risk_detected", [BINARY_RISK_ID]),
        ({"point": 0.05, "ci_lower": 0.01, "ci_upper": 0.09}, "DISPARITY_OBSERVED", "disparity_observed", []),
        ({"point": EPSILON, "ci_lower": 0.0, "ci_upper": 0.04}, "NO_MATERIAL_DISPARITY", "no_material_risk", []),
        ({"point": 0.05, "ci_lower": EPSILON, "ci_upper": 0.09}, "DISPARITY_OBSERVED", "disparity_observed", []),
        ({"point": 0.30, "ci_lower": None, "ci_upper": None}, "INSUFFICIENT_EVIDENCE", "not_scored", []),
        ({"point": None, "ci_lower": None, "ci_upper": None}, "INSUFFICIENT_EVIDENCE", "not_scored", []),
    ],
    ids=["ci_lower_above_eps", "ci_crosses_eps", "point_exactly_eps", "lower_exactly_eps", "no_ci", "no_point"],
)
def test_binary_fairness_decision(ci: dict, finding: str, aspect: str, risks: list[str]) -> None:
    d = binary_fairness_decision(ci)
    assert (d["finding"], d["aspect_scoring"], d["risks_triggered"]) == (finding, aspect, risks)


def test_risk_id_is_the_equal_opportunity_risk() -> None:
    assert BINARY_RISK_ID == "F-FAIR-EOPP"


# --- probe end to end -----------------------------------------------------------


def _run_probe(db_session: Any, spec: dict[str, tuple[int, int, int, int]], min_group_n: int = 50):
    y_true, y_pred, groups = _rows(spec)
    lines = ["text,label,group"] + [
        f"t{i},{'pos' if y else 'neg'},{g}" for i, (y, g) in enumerate(zip(y_true, groups, strict=True))
    ]
    csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    store, content = _binary_csv_and_content(db_session, csv_bytes, row_count=len(y_pred))
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
    return FairnessProbe(inference=FakeInferenceBackend(predictions=y_pred, num_labels=2)).run(ctx)


def test_base_rate_gap_without_tpr_gap_is_no_material_risk(db_session: Any) -> None:
    """Equal TPR/FPR across groups but base rates 0.6 vs 0.2: DPD and the
    label-rate gap are large, EOD is 0 — no risk."""
    out = _run_probe(db_session, {"a": (500, 300, 240, 10), "b": (500, 100, 80, 20)})
    m = out.metric_values
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert m["label_rate_gap"] == pytest.approx(0.4)
    assert m["demographic_parity_difference"] > 0.25
    assert m["equal_opportunity_difference"] == 0.0
    assert m["fairness_finding"] == "NO_MATERIAL_DISPARITY"
    assert m["aspect_scoring"] == "no_material_risk"
    assert m["risks_triggered"] == []
    assert not evidence_flag_one("FAIRNESS", m, None)


def test_large_tpr_gap_triggers_only_the_eopp_risk(db_session: Any) -> None:
    out = _run_probe(db_session, {"a": (600, 300, 270, 15), "b": (600, 300, 150, 15)})
    m = out.metric_values
    assert m["equal_opportunity_difference"] == pytest.approx(0.4)
    assert m["eopp_ci"]["ci_lower"] > EPSILON
    assert m["fairness_finding"] == "FAIRNESS_RISK"
    assert m["aspect_scoring"] == "risk_detected"
    assert m["risks_triggered"] == ["F-FAIR-EOPP"]
    assert m["scored_risk_id"] is None
    assert evidence_flag_one("FAIRNESS", m, None)
    assert "not a finding that the model is unfair" in out.status_reason


def test_evidence_retains_all_fairness_information(db_session: Any) -> None:
    m = _run_probe(db_session, {"a": (600, 300, 270, 15), "b": (600, 300, 150, 30)}).metric_values
    for key in ("demographic_parity_difference", "equalized_odds_difference", "equal_opportunity_difference",
                "fpr_gap", "subgroup_f1_spread", "label_rate_gap", "excess_dpd", "excess_dpd_v1",
                "dp_ci", "eo_ci", "f1_ci", "eopp_ci", "groups", "min_group_n_observed", "eligibility"):
        assert m[key] is not None, key
    assert m["fpr_gap"] == pytest.approx(0.05)
    assert m["excess_dpd"] == m["excess_dpd_v1"]
    assert "excess_dpd_v2" not in m
    assert m["groups"]["a"]["n"] == 600
    assert m["eligibility"]["positives"] == {"a": 300, "b": 300}
    assert m["eligibility"]["min_positives_per_group"] == 1
    assert m["methodology_version"] == BINARY_METHODOLOGY_VERSION
    assert m["fairness_rule"]["epsilon"] == EPSILON
    assert m["fairness_rule"]["risk_id"] == "F-FAIR-EOPP"


def test_insufficient_positive_examples_abstains(db_session: Any) -> None:
    # Group b passes min_group_n (n=200) but has no positive label: TPR undefined.
    out = _run_probe(db_session, {"a": (200, 100, 80, 0), "b": (200, 0, 0, 10)}, min_group_n=50)
    m = out.metric_values
    assert out.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert m["fairness_finding"] == "INSUFFICIENT_EVIDENCE"
    assert m["aspect_scoring"] == "not_scored"
    assert m["risks_triggered"] == []
    assert "G-FAIR-POSITIVES" in m["reliability"]["failed_gates"]
    assert m["demographic_parity_difference"] is not None  # evidence kept


def test_fewer_than_two_eligible_groups_abstains(db_session: Any) -> None:
    out = _run_probe(db_session, {"a": (200, 100, 80, 0), "b": (20, 10, 2, 0)}, min_group_n=50)
    assert out.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-FAIR-N-GROUP" in out.metric_values["reliability"]["failed_gates"]


def test_wide_eod_ci_blocks_mapping(db_session: Any) -> None:
    # 30 positives per group leave the TPR-gap CI wider than CI_WIDE_THRESHOLD.
    out = _run_probe(db_session, {"a": (400, 30, 24, 0), "b": (400, 30, 12, 0)}, min_group_n=30)
    m = out.metric_values
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert m["eopp_ci"]["ci_upper"] - m["eopp_ci"]["ci_lower"] > 0.15
    assert m["aspect_scoring"] == "mapping_blocked"
    assert "G-FAIR-CI-WIDE" in m["reliability"]["failed_gates"]
    assert "wide_ci_eopp" in out.flags
    assert m["risks_triggered"] == []
    assert m["fairness_finding"] == "INSUFFICIENT_EVIDENCE"


def test_wide_dp_ci_alone_no_longer_blocks(db_session: Any) -> None:
    """The gate follows the CI the rule uses (EOD), not the DP CI."""
    out = _run_probe(db_session, {"a": (60, 50, 50, 0), "b": (60, 50, 50, 5)}, min_group_n=30)
    m = out.metric_values
    assert m["dp_ci"]["ci_upper"] - m["dp_ci"]["ci_lower"] > 0.15
    assert "wide_ci_dp" in out.flags
    assert m["eopp_ci"]["ci_upper"] - m["eopp_ci"]["ci_lower"] <= 0.15
    assert m["aspect_scoring"] != "mapping_blocked"


def test_methodology_versions_bumped() -> None:
    assert CURRENT_METHODOLOGY_VERSION not in ("v4-disclosure-gaps-2026", "v5-binary-fairness-risk-2026")  # L4.1 introduced v6; later rounds bump further
    assert BINARY_METHODOLOGY_VERSION == "tl-fairness-binary-v1.2"
