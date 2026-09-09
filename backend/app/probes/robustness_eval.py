"""Robustness evaluation — gates, R-ROB-PERT trigger (tl-methodology-v1.0).

Layer A only: no O mapping, no osd_proposals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.enums import ProbeEvaluationStatus
from app.probes.robustness_stats import (
    BOOTSTRAP_B,
    CI_WIDE_THRESHOLD,
    CLEAN_FLOOR,
    EPSILON_DROP,
    LABEL_COMPAT_MIN_FRACTION,
    MIN_EVALUATED,
    SCORED_RISK_ID,
    accuracy_drop,
    accuracy_wilson_uncertainty,
    paired_bootstrap_accuracy_drop_ci,
    pert_trigger_fires,
    relative_degradation,
)


@dataclass
class ClassificationRobustnessResult:
    status: ProbeEvaluationStatus
    status_reason: str | None
    aspect_scoring: str
    scored_risk_id: str | None
    risks_triggered: list[str]
    metrics: dict[str, Any]
    uncertainty: dict[str, Any]
    reliability: dict[str, Any]
    flags: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    confidence: float = 0.8


def evaluate_classification_robustness(
    *,
    aligned: list[dict[str, Any]],
    n_requested: int,
    n_label_compatible: int,
    label_compat_fraction: float,
    n_successfully_perturbed: int,
    perturbation_coverage: float,
    seed: int,
    domain_mismatch: bool = False,
    allow_domain_mismatch: bool = False,
    mapping_blocked_pre: bool = False,
) -> ClassificationRobustnessResult:
    """Compute robustness metrics, gates, and R-ROB-PERT trigger."""
    flags: list[str] = []
    limitations: list[str] = []
    failed_gates: list[str] = []

    n_evaluated = len(aligned)
    metrics: dict[str, Any] = {
        "n_requested": n_requested,
        "n_label_compatible": n_label_compatible,
        "n_evaluated": n_evaluated,
        "label_compat_fraction": round(label_compat_fraction, 6),
        "n_successfully_perturbed": n_successfully_perturbed,
        "n_perturb_failed": max(0, n_label_compatible - n_successfully_perturbed),
        "perturbation_coverage": round(perturbation_coverage, 6),
        "clean_accuracy": None,
        "robust_accuracy": None,
        "degradation_ratio": None,
        "relative_degradation": None,
        "accuracy_drop": None,
        "attack_success_rate": None,
        "proposed_mapping": False,
    }
    uncertainty: dict[str, Any] = {}

    if domain_mismatch and not allow_domain_mismatch:
        failed_gates.append("G-ROB-DOMAIN")
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason="evaluation_domain mismatch and allow_domain_mismatch is false",
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags + ["domain_mismatch"],
            limitations=limitations,
            confidence=0.45,
        )

    if domain_mismatch and allow_domain_mismatch:
        flags.append("domain_mismatch")
        limitations.append(
            "G-ROB-DOMAIN: domain mismatch — evidence only; mapping blocked"
        )
        mapping_blocked_pre = True

    if n_label_compatible == 0 or label_compat_fraction < LABEL_COMPAT_MIN_FRACTION:
        failed_gates.append("G-ROB-LABEL-COMPAT")
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason=(
                f"label compatibility insufficient: n_label_compatible={n_label_compatible}, "
                f"fraction={label_compat_fraction:.4f} < {LABEL_COMPAT_MIN_FRACTION}"
            ),
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags + ["label_compat_insufficient"],
            limitations=limitations,
            confidence=0.45,
        )

    if n_evaluated < MIN_EVALUATED:
        failed_gates.append("G-ROB-N-EVAL")
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason=f"n_evaluated={n_evaluated} < min={MIN_EVALUATED}",
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags + ["insufficient_n_eval"],
            limitations=limitations,
            confidence=0.45,
        )

    if perturbation_coverage < 1.0:
        failed_gates.append("G-ROB-PERT-COVERAGE")
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason=(
                f"incomplete perturbation coverage: {perturbation_coverage:.4f} < 1.0"
            ),
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags + ["incomplete_perturbation_coverage"],
            limitations=limitations
            + ["Perturbation coverage incomplete — scored risk path blocked"],
            confidence=0.45,
        )

    clean_correct = sum(
        1 for r in aligned if int(r["y_hat_clean"]) == int(r["label"])
    )
    robust_correct = sum(
        1 for r in aligned if int(r["y_hat_robust"]) == int(r["label"])
    )
    flipped = sum(
        1
        for r in aligned
        if int(r["y_hat_clean"]) == int(r["label"])
        and int(r["y_hat_robust"]) != int(r["label"])
    )

    clean_acc = clean_correct / n_evaluated
    robust_acc = robust_correct / n_evaluated
    drop = accuracy_drop(clean_acc, robust_acc)
    rel_deg = relative_degradation(clean_acc, robust_acc)
    deg_ratio = round(robust_acc / clean_acc, 4) if clean_acc > 0 else None
    asr = flipped / n_evaluated

    metrics.update(
        {
            "clean_accuracy": round(clean_acc, 4),
            "robust_accuracy": round(robust_acc, 4),
            "degradation_ratio": deg_ratio,
            "relative_degradation": round(rel_deg, 4),
            "accuracy_drop": round(drop, 6),
            "attack_success_rate": round(asr, 4),
        }
    )

    uncertainty["clean_accuracy"] = accuracy_wilson_uncertainty(clean_correct, n_evaluated)
    uncertainty["robust_accuracy"] = accuracy_wilson_uncertainty(robust_correct, n_evaluated)
    drop_uncertainty = paired_bootstrap_accuracy_drop_ci(aligned, B=BOOTSTRAP_B, seed=seed)
    uncertainty["accuracy_drop"] = drop_uncertainty

    point = drop_uncertainty.get("point")
    ci_lower = drop_uncertainty.get("ci_lower")
    ci_upper = drop_uncertainty.get("ci_upper")

    if ci_lower is None or ci_upper is None:
        flags.append("missing_bootstrap_ci")
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason="bootstrap CI unavailable for accuracy_drop",
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags,
            limitations=limitations + ["bootstrap percentile CI had no valid replicates"],
            confidence=0.45,
        )

    if clean_acc < CLEAN_FLOOR:
        failed_gates.append("G-ROB-CLEAN-FLOOR")
        flags.append("uninformative_robustness")
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.EVALUATED,
            status_reason=(
                f"clean_accuracy={clean_acc:.4f} < {CLEAN_FLOOR} — uninformative robustness"
            ),
            aspect_scoring="mapping_blocked",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags,
            limitations=limitations
            + ["G-ROB-CLEAN-FLOOR: clean accuracy too low for scored risk"],
            confidence=0.75,
        )

    if (
        ci_lower is not None
        and ci_upper is not None
        and (float(ci_upper) - float(ci_lower)) > CI_WIDE_THRESHOLD
    ):
        failed_gates.append("G-ROB-CI-WIDE")
        flags.append("wide_ci")
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.EVALUATED,
            status_reason="accuracy_drop CI width exceeds 0.20 — mapping blocked",
            aspect_scoring="mapping_blocked",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags,
            limitations=limitations + ["G-ROB-CI-WIDE: wide CI blocks R-ROB-PERT scoring"],
            confidence=0.75,
        )

    if mapping_blocked_pre:
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.EVALUATED,
            status_reason="domain mismatch override — evidence only; mapping blocked",
            aspect_scoring="mapping_blocked",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags,
            limitations=limitations,
            confidence=0.75,
        )

    if pert_trigger_fires(
        float(point) if point is not None else None,
        float(ci_lower) if ci_lower is not None else None,
    ):
        return ClassificationRobustnessResult(
            status=ProbeEvaluationStatus.EVALUATED,
            status_reason=(
                f"R-ROB-PERT triggered: drop={point} > {EPSILON_DROP}, "
                f"ci_lower={ci_lower} > {EPSILON_DROP}"
            ),
            aspect_scoring="scored_risk",
            scored_risk_id=SCORED_RISK_ID,
            risks_triggered=[SCORED_RISK_ID],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": True, "failed_gates": []},
            flags=flags,
            limitations=limitations,
            confidence=0.85,
        )

    return ClassificationRobustnessResult(
        status=ProbeEvaluationStatus.EVALUATED,
        status_reason=(
            f"no material perturbation risk at 95% CI "
            f"(drop={point}, ci_lower={ci_lower}, ε={EPSILON_DROP})"
        ),
        aspect_scoring="no_material_risk",
        scored_risk_id=None,
        risks_triggered=[],
        metrics=metrics,
        uncertainty=uncertainty,
        reliability={"gates_passed": True, "failed_gates": []},
        flags=flags,
        limitations=limitations,
        confidence=0.8,
    )
