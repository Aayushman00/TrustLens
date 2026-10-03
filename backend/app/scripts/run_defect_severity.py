"""L6: defect severity validation (docs/superpowers/plans/2026-10-03-round3-L6-defect-severity.md).

A. Robustness: one knob (the existing attack_budget -> char-swap max_changes) on one
   clean model. B. Safety: the existing nested safety-flip weights (rate 0..1).
Production probes run in-process on the L5 eval set; the aspect score is the
documented heuristic O/S/D band through fries.aspect_score. No threshold changes.

Usage (from backend/)::

    python -m app.scripts.run_defect_severity --out ../results/defect_severity_20261003
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

from app.osd.agent import _robustness_band, _safety_band
from app.probes.base import ProbeOutput
from app.probes.robustness import RobustnessProbe
from app.probes.robustness_nlp import RobustnessRunner
from app.probes.safety import SafetyProbe
from app.schemas.evaluation_contract_v2 import RobustnessContractV2, SafetyContractV2
from app.schemas.probe_config import ProbeConfigV1
from app.scoring.fries import OSDTriple, aspect_score
from app.scripts.compare_ground_truth import evidence_flag_one, spearman
from app.scripts.prepare_flawed_suite_data import SUITE_DIR, validate_out_dir
from app.scripts.run_fairness_confirm import DEFAULT_ROOT, LABEL_MAPPING, REFERENCE, in_memory_context

ROB_BUDGETS = (0.01, 0.03, 0.05, 0.08)
ROB_MODEL = "variant3_explainability"
SAFETY_LEVELS = {"variant3_explainability": 0.0, "sweep_safety_r025": 0.25, "variant5_safety": 0.5,
                 "sweep_safety_r075": 0.75, "sweep_safety_r100": 1.0}
EVAL_CSV = DEFAULT_ROOT / "data" / "eval_set.csv"
MODELS = SUITE_DIR / "models"


def perturbable_rows(csv_bytes: bytes) -> tuple[bytes, list[str]]:
    """Drop rows char-swap cannot perturb (no alphanumeric character), which the
    unchanged G-ROB-PERT-COVERAGE gate (coverage must be 1.0) otherwise blocks on."""
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=reader.fieldnames or [])
    writer.writeheader()
    dropped = []
    for row in reader:
        if any(c.isalnum() for c in row["text"]):
            writer.writerow(row)
        else:
            dropped.append(row["text"])
    return buf.getvalue().encode("utf-8"), dropped


def robustness_once(model_dir: Path, csv_bytes: bytes, budget: float, *, runner: RobustnessRunner | None = None) -> ProbeOutput:
    ctx = in_memory_context(
        model_dir, csv_bytes, probe_config=ProbeConfigV1(attack_budget=budget),
        contracts=lambda cid: {"robustness": RobustnessContractV2(
            dataset_content_id=cid, text_column="text", target_column="label", label_mapping=LABEL_MAPPING)},
    )
    return RobustnessProbe(runner=runner).run(ctx)


def safety_once(model_dir: Path, csv_bytes: bytes, *, backend: Any = None) -> ProbeOutput:
    card = model_dir / "README.md"
    ctx = in_memory_context(
        model_dir, csv_bytes,
        model_metadata={"card_text": card.read_text(encoding="utf-8")} if card.exists() else {},
        contracts=lambda cid: {"safety": SafetyContractV2(
            dataset_content_id=cid, text_column="text", target_column="label", severe_column="severe",
            label_mapping=LABEL_MAPPING, positive_label_index=1, min_severe_n=30)},
    )
    return SafetyProbe(inference=backend).run(ctx)


def aspect(dim: str, m: dict[str, Any]) -> dict[str, Any]:
    band, detail = (_robustness_band if dim == "ROBUSTNESS" else _safety_band)(m)
    score = aspect_score([OSDTriple(*band)]) if all(isinstance(v, int) for v in band) else None
    return {"band": band, "band_detail": detail, "aspect_score": score}


def _status(out: ProbeOutput) -> str:
    return str(getattr(out.status, "value", out.status))


def robustness_record(budget: float, out: ProbeOutput) -> dict[str, Any]:
    m = out.metric_values
    return {
        "attack_budget": budget, "max_changes": m.get("max_changes"),
        **{k: m.get(k) for k in ("clean_accuracy", "robust_accuracy", "accuracy_drop", "relative_degradation",
                                 "attack_success_rate", "perturbation_coverage", "n_evaluated",
                                 "aspect_scoring", "risks_triggered", "scored_risk_id")},
        "accuracy_drop_ci": (m.get("uncertainty") or {}).get("accuracy_drop"),
        "status": _status(out), "status_reason": out.status_reason,
        **aspect("ROBUSTNESS", m),
    }


def safety_record(rate: float, out: ProbeOutput, *, control_severe_fnr: float | None) -> dict[str, Any]:
    m = out.metric_values
    b = m.get("behavior") or {}
    return {
        "injected_rate": rate,
        **{k: b.get(k) for k in ("severe_n", "severe_fnr", "severe_fnr_ci", "fnr_ratio", "harmful_recall",
                                 "benign_fpr", "overall_fnr")},
        "behavior_status": b.get("status"),
        "status": _status(out), "aspect_scoring": m.get("aspect_scoring"),
        "risks_triggered": m.get("risks_triggered"), "disclosure_gaps": m.get("disclosure_gaps"),
        "ground_truth_safety_flag": evidence_flag_one("SAFETY", m, control_severe_fnr),
        **aspect("SAFETY", m),
    }


def monotonicity(x: list[float], y: list[float | None], *, increasing: bool) -> dict[str, Any]:
    """Adjacent-pair violations in the expected direction (abstained levels skipped)."""
    pts = [(a, b) for a, b in zip(x, y, strict=True) if b is not None]
    pairs = list(zip(pts, pts[1:], strict=False))
    violations = sum((q[1] < p[1]) if increasing else (q[1] > p[1]) for p, q in pairs)
    return {
        "expected": "increasing" if increasing else "decreasing", "n": len(pts),
        "violations": violations, "ties": sum(q[1] == p[1] for p, q in pairs), "monotone": violations == 0,
        "spearman_rho": spearman([p[0] for p in pts], [p[1] for p in pts]) if len(pts) >= 3 else None,
    }


_REPEAT = {"ROBUSTNESS": ("accuracy_drop", "aspect_scoring", "clean_accuracy", "robust_accuracy"),
           "SAFETY": ("severe_fnr", "fnr_ratio", "aspect_scoring")}


def _repeatable(dim: str, recs: list[dict[str, Any]]) -> bool:
    return all(r.get(k) == recs[0].get(k) for r in recs for k in _REPEAT[dim])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--exclude-unperturbable", action="store_true",
                    help="drop rows without alphanumerics from the robustness input only (deviation A2)")
    ap.add_argument("--robustness-only", action="store_true")
    args = ap.parse_args(argv)
    out = validate_out_dir(args.out)
    out.mkdir(parents=True)
    csv_bytes = EVAL_CSV.read_bytes()
    rob_bytes, dropped = perturbable_rows(csv_bytes) if args.exclude_unperturbable else (csv_bytes, [])

    rob = []
    for budget in ROB_BUDGETS:
        recs = [robustness_record(budget, robustness_once(MODELS / ROB_MODEL, rob_bytes, budget)) for _ in range(args.runs)]
        rob.append({**recs[0], "repeatable": _repeatable("ROBUSTNESS", recs)})
        print("robustness", budget, rob[-1]["accuracy_drop"], rob[-1]["aspect_scoring"], rob[-1]["aspect_score"])

    saf: list[dict[str, Any]] = []
    for name, rate in {} if args.robustness_only else {REFERENCE: None, **SAFETY_LEVELS}.items():
        if rate is None:
            ctrl = safety_once(MODELS / REFERENCE, csv_bytes)
            control_fnr = ctrl.metric_values.get("severe_fnr")
            saf.append({"model": REFERENCE, "role": "control", **safety_record(0.0, ctrl, control_severe_fnr=None)})
            continue
        recs = [safety_record(rate, safety_once(MODELS / name, csv_bytes), control_severe_fnr=control_fnr)
                for _ in range(args.runs)]
        saf.append({"model": name, **recs[0], "repeatable": _repeatable("SAFETY", recs)})
        print("safety", name, saf[-1]["severe_fnr"], saf[-1]["ground_truth_safety_flag"], saf[-1]["aspect_score"])

    levels = saf[1:]
    mono = {
        "robustness_accuracy_drop": monotonicity(list(ROB_BUDGETS), [r["accuracy_drop"] for r in rob], increasing=True),
        "robustness_relative_degradation": monotonicity(
            list(ROB_BUDGETS), [r["relative_degradation"] for r in rob], increasing=True),
        "robustness_aspect_score": monotonicity(list(ROB_BUDGETS), [r["aspect_score"] for r in rob], increasing=False),
    }
    if saf:
        rates = [r["injected_rate"] for r in levels]
        mono |= {
            "safety_severe_fnr": monotonicity(rates, [r["severe_fnr"] for r in levels], increasing=True),
            "safety_fnr_ratio": monotonicity(rates, [r["fnr_ratio"] for r in levels], increasing=True),
            "safety_aspect_score": monotonicity(rates, [r["aspect_score"] for r in levels], increasing=False),
        }
    result = {"eval_set": str(EVAL_CSV.relative_to(SUITE_DIR.parents[1])), "robustness_model": ROB_MODEL,
              "robustness_rows_dropped_unperturbable": dropped,
              "runs_per_level": args.runs, "robustness": rob, "safety": saf, "monotonicity": mono}
    (out / "analysis.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(mono, indent=2))


if __name__ == "__main__":
    main()
