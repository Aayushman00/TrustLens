"""ConfidenceEngine unit tests (Phase 15) — pure, no DB/S3."""

from __future__ import annotations

import math

from app.confidence.engine import (
    CONFIDENCE_METHOD,
    ConfidenceSummary,
    geometric_mean,
    refine,
    summarize,
)
from app.db.enums import FriesDimension

_REF = [{"evidence_id": "e1"}]


def test_geometric_mean_basics() -> None:
    assert geometric_mean([]) == 0.0
    assert geometric_mean([1.0, 1.0, 1.0]) == 1.0
    assert math.isclose(geometric_mean([0.25, 1.0]), 0.5)
    assert geometric_mean([0.0, 1.0]) == 0.0


def test_geometric_mean_clamps_inputs_and_output() -> None:
    assert geometric_mean([2.0, 3.0]) == 1.0  # inputs clamped to 1
    assert geometric_mean([-1.0, 0.5]) == 0.0  # negative clamped to 0
    assert 0.0 <= geometric_mean([0.3, 0.7, 0.9]) <= 1.0


def test_fairness_thin_slice_lowers_data_quality() -> None:
    result = refine(
        FriesDimension.FAIRNESS,
        metric_values={
            "demographic_parity_difference": 0.12,
            "min_group_n": 30,
            "min_group_n_observed": 7,
            "needs_human_review": True,
        },
        flags=["insufficient_slice_size"],
        evidence_refs=_REF,
    )
    assert result.factors.data_quality == 0.55
    assert result.factors.probe_reliability == 1.0
    assert result.confidence < 0.85


def test_fairness_skipped_scores_low_reliability() -> None:
    result = refine(
        FriesDimension.FAIRNESS,
        metric_values={"demographic_parity_difference": None, "skip_reason": "no dataset"},
        flags=["dataset_load_failed", "metrics_skipped"],
        evidence_refs=_REF,
    )
    assert result.factors.data_quality == 0.35
    assert result.factors.probe_reliability == 0.45
    assert result.confidence < 0.6


def test_robustness_skip_and_tiny_samples_score_low() -> None:
    skipped = refine(
        FriesDimension.ROBUSTNESS,
        metric_values={"clean_accuracy": None, "n_samples": 64},
        flags=["unsupported_modality", "attack_skipped"],
        evidence_refs=_REF,
    )
    assert skipped.factors.probe_reliability == 0.45
    assert skipped.factors.data_quality == 0.4

    tiny = refine(
        FriesDimension.ROBUSTNESS,
        metric_values={"clean_accuracy": 0.9, "robust_accuracy": 0.8, "n_samples": 8},
        flags=[],
        evidence_refs=_REF,
    )
    full = refine(
        FriesDimension.ROBUSTNESS,
        metric_values={"clean_accuracy": 0.9, "robust_accuracy": 0.8, "n_samples": 128},
        flags=[],
        evidence_refs=_REF,
    )
    assert tiny.confidence < full.confidence
    assert full.confidence == 1.0


def test_integrity_complete_checks_score_high() -> None:
    checks = {name: {"pass": True} for name in ("a", "b", "c", "d", "e", "f")}
    result = refine(
        FriesDimension.INTEGRITY,
        metric_values={"checks": checks, "pass_count": 6, "fail_count": 0},
        flags=[],
        evidence_refs=_REF,
    )
    assert result.factors.data_quality == 1.0
    assert result.factors.probe_reliability == 1.0
    assert result.factors.evidence_completeness == 1.0
    assert result.confidence == 1.0


def test_integrity_failed_checks_lower_data_quality() -> None:
    result = refine(
        FriesDimension.INTEGRITY,
        metric_values={"checks": {"a": {"pass": True}, "b": {"pass": False}},
                       "pass_count": 3, "fail_count": 3},
        flags=["missing_license"],
        evidence_refs=_REF,
    )
    assert result.factors.data_quality == 0.5
    assert result.confidence < 1.0


def test_safety_empty_card_scores_low() -> None:
    result = refine(
        FriesDimension.SAFETY,
        metric_values={"coverage_ratio": 0.0, "card_chars": 0, "high_impact_claims": []},
        flags=["empty_card"],
        evidence_refs=_REF,
    )
    assert result.factors.data_quality == 0.1  # floored
    assert result.factors.probe_reliability == 0.4
    assert result.confidence < 0.35


def test_safety_high_impact_with_gaps_lowers_reliability() -> None:
    result = refine(
        FriesDimension.SAFETY,
        metric_values={
            "coverage_ratio": 0.75,
            "card_chars": 900,
            "high_impact_claims": ["medical"],
        },
        flags=["high_impact_deployment_claim"],
        evidence_refs=_REF,
    )
    assert result.factors.probe_reliability == 0.5


def test_explainability_coverage_drives_confidence() -> None:
    low = refine(
        FriesDimension.EXPLAINABILITY,
        metric_values={"coverage_ratio": 0.25, "card_chars": 300},
        flags=[],
        evidence_refs=_REF,
    )
    high = refine(
        FriesDimension.EXPLAINABILITY,
        metric_values={"coverage_ratio": 1.0, "card_chars": 3000},
        flags=[],
        evidence_refs=_REF,
    )
    assert low.factors.probe_reliability == 0.6  # coverage < 0.4 → weak parse
    assert low.confidence < high.confidence
    assert high.confidence == 1.0


def test_skipped_probes_score_lower_than_complete_integrity() -> None:
    integrity = refine(
        FriesDimension.INTEGRITY,
        metric_values={
            "checks": {n: {"pass": True} for n in ("a", "b", "c", "d", "e", "f")},
            "pass_count": 6,
            "fail_count": 0,
        },
        flags=[],
        evidence_refs=_REF,
    )
    skipped_fairness = refine(
        FriesDimension.FAIRNESS,
        metric_values={"demographic_parity_difference": None},
        flags=["metrics_skipped"],
        evidence_refs=_REF,
    )
    skipped_robustness = refine(
        FriesDimension.ROBUSTNESS,
        metric_values={"clean_accuracy": None},
        flags=["attack_skipped", "unsupported_modality"],
        evidence_refs=_REF,
    )
    assert skipped_fairness.confidence < integrity.confidence
    assert skipped_robustness.confidence < integrity.confidence


def test_refine_without_flags_uses_metric_values_only() -> None:
    """summarize() re-derives from persisted metrics when flags are unavailable."""
    result = refine(
        FriesDimension.ROBUSTNESS,
        metric_values={"clean_accuracy": None, "skip_reason": "x"},
        evidence_refs=_REF,
    )
    assert result.factors.probe_reliability == 0.45


def test_summarize_uses_stored_confidence_and_geometric_mean() -> None:
    stored = {
        FriesDimension.FAIRNESS: 0.55,
        FriesDimension.ROBUSTNESS: 0.40,
        FriesDimension.INTEGRITY: 0.91,
        FriesDimension.EXPLAINABILITY: 0.80,
        FriesDimension.SAFETY: 0.70,
    }
    summary = summarize([(dim, conf, {}) for dim, conf in stored.items()])
    assert isinstance(summary, ConfidenceSummary)
    assert summary.method == CONFIDENCE_METHOD
    assert summary.proposed_calibration is True
    assert set(summary.by_dimension) == {d.value for d in stored}
    expected = math.exp(sum(math.log(v) for v in stored.values()) / len(stored))
    assert math.isclose(summary.overall, round(expected, 4), abs_tol=1e-9)
    assert "not correctness" in summary.note


def test_summarize_rederives_when_confidence_missing() -> None:
    summary = summarize(
        [
            (
                FriesDimension.INTEGRITY,
                None,
                {
                    "checks": {n: {"pass": True} for n in ("a", "b", "c")},
                    "pass_count": 3,
                    "fail_count": 0,
                },
            )
        ]
    )
    assert summary.by_dimension["INTEGRITY"] == 1.0
    assert summary.overall == 1.0
