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
from app.db.enums import FriesDimension, ProbeEvaluationStatus

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


def test_fairness_insufficient_evidence_keeps_low_reliability() -> None:
    result = refine(
        FriesDimension.FAIRNESS,
        metric_values={
            "demographic_parity_difference": "NOT_APPLICABLE",
            "subgroup_worst_group_acc_gap": 0.12,
            "probe_status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
            "aspect_scoring": "not_scored",
        },
        flags=["model_faithful_pairing", "missing_bootstrap_ci"],
        evidence_refs=_REF,
    )
    assert result.factors.probe_reliability == 0.45


def test_fairness_mapping_blocked_wide_ci_reduces_reliability() -> None:
    blocked = refine(
        FriesDimension.FAIRNESS,
        metric_values={
            "demographic_parity_difference": "NOT_APPLICABLE",
            "subgroup_worst_group_acc_gap": 0.30,
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "aspect_scoring": "mapping_blocked",
            "reliability": {
                "gates_passed": False,
                "failed_gates": ["G-FAIR-CI-WIDE"],
            },
        },
        flags=["model_faithful_pairing", "wide_ci"],
        evidence_refs=_REF,
    )
    assert blocked.factors.probe_reliability == 0.45
    assert blocked.factors.probe_reliability < 1.0

    scored = refine(
        FriesDimension.FAIRNESS,
        metric_values={
            "demographic_parity_difference": "NOT_APPLICABLE",
            "subgroup_worst_group_acc_gap": 0.30,
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "aspect_scoring": "scored_risk",
            "reliability": {"gates_passed": True, "failed_gates": []},
        },
        flags=["model_faithful_pairing"],
        evidence_refs=_REF,
    )
    assert scored.factors.probe_reliability == 1.0


def test_fairness_unrelated_binary_gate_does_not_get_mapping_blocked_penalty() -> None:
    result = refine(
        FriesDimension.FAIRNESS,
        metric_values={
            "demographic_parity_difference": 0.12,
            "equalized_odds_difference": 0.08,
            "min_group_n": 30,
            "min_group_n_observed": 45,
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "aspect_scoring": "scored_risk",
            "reliability": {
                "gates_passed": False,
                "failed_gates": ["G-FAIR-EO-UNSTABLE"],
            },
        },
        flags=["eo_unstable"],
        evidence_refs=_REF,
    )
    assert result.factors.probe_reliability == 1.0


def test_robustness_wide_ci_and_mapping_blocked() -> None:
    blocked = refine(
        FriesDimension.ROBUSTNESS,
        metric_values={
            "clean_accuracy": 0.9,
            "robust_accuracy": 0.7,
            "n_evaluated": 150,
            "aspect_scoring": "mapping_blocked",
            "uncertainty": {
                "accuracy_drop": {
                    "point": 0.2,
                    "ci_lower": 0.05,
                    "ci_upper": 0.35,
                }
            },
            "reliability": {"failed_gates": ["G-ROB-CI-WIDE"]},
        },
        flags=["wide_ci"],
        evidence_refs=_REF,
    )
    assert blocked.factors.probe_reliability == 0.45
    assert blocked.factors.evidence_completeness == 0.6


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
        metric_values={
            "clean_accuracy": 0.9,
            "robust_accuracy": 0.8,
            "n_evaluated": 80,
            "uncertainty": {
                "accuracy_drop": {"point": 0.1, "ci_lower": 0.05, "ci_upper": 0.15}
            },
        },
        flags=[],
        evidence_refs=_REF,
    )
    full = refine(
        FriesDimension.ROBUSTNESS,
        metric_values={
            "clean_accuracy": 0.9,
            "robust_accuracy": 0.8,
            "n_evaluated": 200,
            "aspect_scoring": "no_material_risk",
            "uncertainty": {
                "accuracy_drop": {"point": 0.1, "ci_lower": 0.05, "ci_upper": 0.15}
            },
        },
        flags=[],
        evidence_refs=_REF,
    )
    assert tiny.confidence < full.confidence
    assert full.confidence == 1.0


def test_integrity_rich_identity_scores_high_even_with_license_risk() -> None:
    result = refine(
        FriesDimension.INTEGRITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "checks": {
                "revision_pinned": {"pass": True},
                "license_declared": {"pass": False},
            },
            "identity": {
                "revision": "a" * 40,
                "sha_like": True,
                "hub_files": ["config.json"],
                "hash_comparison": "not_performed",
            },
            "disclosure": {"card_present": True},
            "reliability": {
                "failed_gates": [
                    "G-INT-HASH-REF-MISSING",
                    "G-INT-HASH-LOCAL-MISSING",
                    "I-INT-HASH-UNVERIFIED",
                ]
            },
        },
        flags=["missing_license"],
        evidence_refs=_REF,
    )
    assert result.factors.data_quality == 1.0
    assert result.factors.probe_reliability == 1.0
    assert result.factors.evidence_completeness == 0.85
    assert result.confidence >= 0.9


def test_integrity_insufficient_identity_scores_low() -> None:
    result = refine(
        FriesDimension.INTEGRITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
            "checks": {},
            "identity": {"hash_comparison": "not_performed"},
        },
        flags=["identity_empty"],
        evidence_refs=_REF,
    )
    assert result.factors.probe_reliability == 0.45
    assert result.factors.data_quality == 0.35
    assert result.confidence < 0.6


def test_integrity_license_gap_does_not_use_pass_rate() -> None:
    rich = refine(
        FriesDimension.INTEGRITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "checks": {
                "license_declared": {"pass": True},
                "revision_pinned": {"pass": True},
            },
            "identity": {
                "sha_like": True,
                "hub_files": ["a.bin"],
                "hash_comparison": "not_performed",
            },
            "reliability": {"failed_gates": ["I-INT-HASH-UNVERIFIED"]},
        },
        evidence_refs=_REF,
    )
    missing_license = refine(
        FriesDimension.INTEGRITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "checks": {
                "license_declared": {"pass": False},
                "revision_pinned": {"pass": True},
            },
            "identity": {
                "sha_like": True,
                "hub_files": ["a.bin"],
                "hash_comparison": "not_performed",
            },
            "reliability": {"failed_gates": ["I-INT-HASH-UNVERIFIED"]},
        },
        flags=["missing_license"],
        evidence_refs=_REF,
    )
    assert rich.factors.data_quality == missing_license.factors.data_quality == 1.0


def test_safety_insufficient_evidence_lowers_confidence() -> None:
    result = refine(
        FriesDimension.SAFETY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
            "coverage_ratio": 0.0,
            "card_chars": 0,
            "high_impact_claims": [],
            "checks": {},
        },
        flags=["empty_card"],
        evidence_refs=_REF,
    )
    assert result.factors.probe_reliability == 0.45
    assert result.factors.data_quality == 0.35
    assert result.confidence < 0.5


def test_safety_evaluated_confidence_not_coverage_or_phrase_driven() -> None:
    partial = refine(
        FriesDimension.SAFETY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 0.25,
            "card_chars": 300,
            "high_impact_claims": ["healthcare"],
            "checks": {"privacy": {"pass": False}},
        },
        flags=["high_impact_deployment_claim"],
        evidence_refs=_REF,
    )
    full = refine(
        FriesDimension.SAFETY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 1.0,
            "card_chars": 3000,
            "high_impact_claims": [],
            "checks": {"privacy": {"pass": True}},
        },
        flags=[],
        evidence_refs=_REF,
    )
    assert partial.factors.data_quality == full.factors.data_quality == 1.0
    assert partial.factors.probe_reliability == full.factors.probe_reliability == 1.0
    assert partial.confidence == full.confidence == 1.0


def test_explainability_evaluated_confidence_not_coverage_driven() -> None:
    partial = refine(
        FriesDimension.EXPLAINABILITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 0.25,
            "card_chars": 300,
            "checks": {"documentation_completeness": {"pass": False}},
        },
        flags=[],
        evidence_refs=_REF,
    )
    full = refine(
        FriesDimension.EXPLAINABILITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 1.0,
            "card_chars": 3000,
            "checks": {"documentation_completeness": {"pass": True}},
        },
        flags=[],
        evidence_refs=_REF,
    )
    assert partial.factors.data_quality == full.factors.data_quality == 1.0
    assert partial.factors.evidence_completeness == full.factors.evidence_completeness == 1.0
    assert partial.confidence == full.confidence == 1.0


def test_skipped_probes_score_lower_than_complete_integrity() -> None:
    integrity = refine(
        FriesDimension.INTEGRITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "checks": {"revision_pinned": {"pass": True}},
            "identity": {
                "sha_like": True,
                "hub_files": ["config.json"],
                "hash_comparison": "not_performed",
            },
            "reliability": {"failed_gates": ["I-INT-HASH-UNVERIFIED"]},
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
                    "probe_status": ProbeEvaluationStatus.EVALUATED.value,
                    "checks": {"revision_pinned": {"pass": True}},
                    "identity": {
                        "sha_like": True,
                        "hub_files": ["config.json"],
                        "hash_comparison": "match",
                    },
                    "reliability": {"failed_gates": []},
                },
            )
        ]
    )
    assert summary.by_dimension["INTEGRITY"] == 1.0
    assert summary.overall == 1.0
