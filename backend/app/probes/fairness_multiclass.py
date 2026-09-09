"""Multiclass fairness evaluation — F-FAIR-PERF (tl-methodology-v1.0)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.enums import ProbeEvaluationStatus
from app.probes.fairness_stats import (
    BOOTSTRAP_B,
    CI_WIDE_THRESHOLD,
    EPSILON,
    SCORED_RISK_ID,
    bootstrap_gap_ci,
    filter_compared_groups,
    group_accuracies_from_aligned,
    per_group_wilson_uncertainty,
    perf_trigger_fires,
    subgroup_worst_group_acc_gap,
)


@dataclass
class MulticlassFairnessResult:
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


def evaluate_multiclass_fairness(
    aligned: list[dict[str, Any]],
    *,
    seed: int,
    min_total_n: int,
    min_group_n: int,
    sensitive_attribute: str,
) -> MulticlassFairnessResult:
    """Compute subgroup accuracy gap, bootstrap CI, gates, and F-FAIR-PERF trigger.

    Caller must validate ``sensitive_attribute`` against the dataset registry.
    Rows are grouped on normalized field ``sensitive``.
    """
    flags: list[str] = ["model_faithful_pairing"]
    limitations: list[str] = []
    failed_gates: list[str] = []

    metrics: dict[str, Any] = {
        "sensitive_attribute": sensitive_attribute,
        "demographic_parity_difference": "NOT_APPLICABLE",
        "equalized_odds_difference": "NOT_APPLICABLE",
        "subgroup_f1_spread": None,
        "subgroup_worst_group_acc_gap": None,
        "per_group": {},
        "excluded_groups": [],
        "min_group_n": min_group_n,
        "min_total_n": min_total_n,
        "n_evaluated": len(aligned),
    }
    uncertainty: dict[str, Any] = {}

    if len(aligned) < min_total_n:
        failed_gates.append("G-FAIR-N-TOTAL")
        return MulticlassFairnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason=(
                f"n_evaluated={len(aligned)} < min_total_n={min_total_n}"
            ),
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags + ["insufficient_total_n"],
            limitations=limitations,
            confidence=0.45,
        )

    per_group_all = group_accuracies_from_aligned(aligned)
    compared, excluded = filter_compared_groups(per_group_all, min_group_n)

    per_group_out: dict[str, Any] = {}
    for name, stats in per_group_all.items():
        entry = {
            "n": stats["n"],
            "correct": stats["correct"],
            "accuracy": round(float(stats["accuracy"]), 6),
        }
        if name in excluded:
            entry["excluded"] = True
            entry["excluded_reason"] = f"n < min_group_n ({min_group_n})"
        per_group_out[name] = entry

    metrics["per_group"] = per_group_out
    metrics["excluded_groups"] = excluded
    metrics["min_group_n_observed"] = (
        min(int(g["n"]) for g in compared.values()) if compared else 0
    )

    if len(compared) < 2:
        failed_gates.append("G-FAIR-N-GROUP")
        if excluded:
            flags.append("thin_groups_excluded")
        return MulticlassFairnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason=(
                f"fewer than 2 groups with n >= {min_group_n} after excluding thin slices"
            ),
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags + ["insufficient_group_n"],
            limitations=limitations,
            confidence=0.45,
        )

    if excluded:
        flags.append("thin_groups_excluded")
        limitations.append(
            f"Groups excluded for n < {min_group_n}: {', '.join(sorted(excluded))}"
        )

    gap = subgroup_worst_group_acc_gap(compared)
    metrics["subgroup_worst_group_acc_gap"] = round(gap, 6)

    gap_uncertainty = bootstrap_gap_ci(
        aligned,
        min_group_n=min_group_n,
        B=BOOTSTRAP_B,
        seed=seed,
    )
    uncertainty["subgroup_worst_group_acc_gap"] = gap_uncertainty
    uncertainty["per_group"] = per_group_wilson_uncertainty(per_group_all)

    point = gap_uncertainty.get("point")
    ci_lower = gap_uncertainty.get("ci_lower")
    ci_upper = gap_uncertainty.get("ci_upper")

    if ci_lower is None or ci_upper is None:
        flags.append("missing_bootstrap_ci")
        return MulticlassFairnessResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason=(
                "bootstrap CI unavailable — no valid replicates for "
                "subgroup_worst_group_acc_gap"
            ),
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": False, "failed_gates": failed_gates},
            flags=flags,
            limitations=limitations
            + ["bootstrap percentile CI had no valid replicates"],
            confidence=0.45,
        )

    gates_passed = True
    if (
        ci_lower is not None
        and ci_upper is not None
        and (float(ci_upper) - float(ci_lower)) > CI_WIDE_THRESHOLD
    ):
        failed_gates.append("G-FAIR-CI-WIDE")
        gates_passed = False
        flags.append("wide_ci")
        return MulticlassFairnessResult(
            status=ProbeEvaluationStatus.EVALUATED,
            status_reason="primary disparity CI width exceeds 0.15 — mapping blocked",
            aspect_scoring="mapping_blocked",
            scored_risk_id=None,
            risks_triggered=[],
            metrics=metrics,
            uncertainty=uncertainty,
            reliability={"gates_passed": gates_passed, "failed_gates": failed_gates},
            flags=flags,
            limitations=limitations
            + ["G-FAIR-CI-WIDE: wide CI blocks F-FAIR-PERF scoring"],
            confidence=0.75,
        )

    if perf_trigger_fires(
        float(point) if point is not None else None,
        float(ci_lower) if ci_lower is not None else None,
    ):
        return MulticlassFairnessResult(
            status=ProbeEvaluationStatus.EVALUATED,
            status_reason=(
                f"F-FAIR-PERF triggered: gap={point} > {EPSILON}, "
                f"ci_lower={ci_lower} > {EPSILON}"
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

    return MulticlassFairnessResult(
        status=ProbeEvaluationStatus.EVALUATED,
        status_reason=(
            "no scored disparity above practical floor at 95% CI "
            f"(gap={point}, ci_lower={ci_lower}, ε={EPSILON})"
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
