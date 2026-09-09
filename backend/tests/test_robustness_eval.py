"""Unit tests for robustness_eval gates and R-ROB-PERT trigger."""

from __future__ import annotations

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.probes.robustness_eval import evaluate_classification_robustness
from app.probes.robustness_stats import SCORED_RISK_ID


def _rows(n: int, *, clean_acc: float, robust_acc: float) -> list[dict]:
    clean_correct = int(round(clean_acc * n))
    robust_correct = int(round(robust_acc * n))
    out: list[dict] = []
    for i in range(n):
        label = i % 2
        yc = label if i < clean_correct else (1 - label)
        yr = label if i < robust_correct else (1 - label)
        out.append({"label": label, "y_hat_clean": yc, "y_hat_robust": yr})
    return out


def _base_kwargs(**overrides):
    base = {
        "n_requested": 200,
        "n_label_compatible": 120,
        "label_compat_fraction": 1.0,
        "n_successfully_perturbed": 120,
        "perturbation_coverage": 1.0,
        "seed": 42,
    }
    base.update(overrides)
    return base


def _alternating_drop_rows(n: int) -> list[dict]:
    """Heterogeneous per-row drops → bootstrap CI width > 0.20."""
    out: list[dict] = []
    for i in range(n):
        label = i % 2
        if i % 2 == 0:
            yc, yr = label, 1 - label
        else:
            yc, yr = 1 - label, label
        out.append({"label": label, "y_hat_clean": yc, "y_hat_robust": yr})
    return out


def test_g_rob_ci_wide_mapping_blocked() -> None:
    aligned = _alternating_drop_rows(120)
    result = evaluate_classification_robustness(
        aligned=aligned,
        **_base_kwargs(n_label_compatible=120, n_successfully_perturbed=120),
    )
    drop_unc = result.uncertainty.get("accuracy_drop") or {}
    ci_lower = drop_unc.get("ci_lower")
    ci_upper = drop_unc.get("ci_upper")
    assert ci_lower is not None and ci_upper is not None
    assert float(ci_upper) - float(ci_lower) > 0.20
    assert result.status is ProbeEvaluationStatus.EVALUATED
    assert result.aspect_scoring == "mapping_blocked"
    assert "G-ROB-CI-WIDE" in result.reliability["failed_gates"]
    assert "wide_ci" in result.flags
    assert result.scored_risk_id is None
    assert result.risks_triggered == []


def test_label_compat_fraction_below_threshold() -> None:
    """Partial label compatibility (90%) blocks scored path; distinct from zero eligible."""
    result = evaluate_classification_robustness(
        aligned=_rows(120, clean_acc=0.9, robust_acc=0.85),
        **_base_kwargs(
            n_label_compatible=180,
            label_compat_fraction=0.90,
            n_successfully_perturbed=120,
            perturbation_coverage=120 / 180,
        ),
    )
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-LABEL-COMPAT" in result.reliability["failed_gates"]
    assert result.aspect_scoring == "not_scored"
    assert result.scored_risk_id is None


def test_g_rob_n_eval_insufficient() -> None:
    result = evaluate_classification_robustness(
        aligned=_rows(80, clean_acc=0.9, robust_acc=0.7),
        **_base_kwargs(n_label_compatible=80, n_successfully_perturbed=80),
    )
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-N-EVAL" in result.reliability["failed_gates"]


def test_g_rob_label_compat_insufficient() -> None:
    result = evaluate_classification_robustness(
        aligned=[],
        **_base_kwargs(n_label_compatible=0, label_compat_fraction=0.0, n_successfully_perturbed=0),
    )
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-LABEL-COMPAT" in result.reliability["failed_gates"]


def test_incomplete_coverage_blocks_scored_path() -> None:
    result = evaluate_classification_robustness(
        aligned=_rows(120, clean_acc=0.9, robust_acc=0.5),
        **_base_kwargs(n_successfully_perturbed=100, perturbation_coverage=100 / 120),
    )
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-PERT-COVERAGE" in result.reliability["failed_gates"]


def test_g_rob_domain_hard_mismatch() -> None:
    result = evaluate_classification_robustness(
        aligned=[],
        **_base_kwargs(),
        domain_mismatch=True,
        allow_domain_mismatch=False,
    )
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-DOMAIN" in result.reliability["failed_gates"]


def test_g_rob_clean_floor_mapping_blocked() -> None:
    result = evaluate_classification_robustness(
        aligned=_rows(120, clean_acc=0.1, robust_acc=0.05),
        **_base_kwargs(),
    )
    assert result.aspect_scoring == "mapping_blocked"
    assert "G-ROB-CLEAN-FLOOR" in result.reliability["failed_gates"]
    assert result.scored_risk_id is None


def test_r_rob_pert_fires() -> None:
    result = evaluate_classification_robustness(
        aligned=_rows(150, clean_acc=0.95, robust_acc=0.55),
        **_base_kwargs(n_label_compatible=150, n_successfully_perturbed=150),
    )
    assert result.aspect_scoring == "scored_risk"
    assert result.scored_risk_id == SCORED_RISK_ID
    assert SCORED_RISK_ID in result.risks_triggered


def test_no_material_risk_when_drop_below_epsilon() -> None:
    result = evaluate_classification_robustness(
        aligned=_rows(150, clean_acc=0.92, robust_acc=0.90),
        **_base_kwargs(n_label_compatible=150, n_successfully_perturbed=150),
    )
    assert result.status is ProbeEvaluationStatus.EVALUATED
    assert result.aspect_scoring == "no_material_risk"
    assert result.scored_risk_id is None
    assert result.risks_triggered == []


def test_domain_override_mapping_blocked() -> None:
    result = evaluate_classification_robustness(
        aligned=_rows(120, clean_acc=0.9, robust_acc=0.85),
        **_base_kwargs(),
        domain_mismatch=False,
        allow_domain_mismatch=True,
        mapping_blocked_pre=True,
    )
    assert result.aspect_scoring == "mapping_blocked"
    assert result.scored_risk_id is None
