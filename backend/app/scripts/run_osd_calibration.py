"""L1: evidence -> O/S/D calibration (pre-declaration
docs/superpowers/plans/2026-10-03-round3-L1-osd-calibration.md).

Stages, in order (from backend/, GPU free)::

    python -m app.scripts.run_osd_calibration prepare   # seed-43 data, disjoint from suite + L5
    python -m app.scripts.run_osd_calibration train     # 7 calibration models, training seed 43
    python -m app.scripts.run_osd_calibration measure   # production probes -> calibration_evidence.json
    python -m app.scripts.run_osd_calibration fit       # OLS anchors -> frozen_mapping.json (then copy to agent.OSD_MAP_V4)
    python -m app.scripts.run_osd_calibration heldout   # frozen L5/L6 evidence re-mapped with v3 and v4

The held-out stage refuses to run unless agent.OSD_MAP_V4 equals frozen_mapping.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.enums import FriesDimension
from app.osd import agent
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, ProbeSnapshot
from app.scoring.fries import OSDTriple, aspect_score
from app.scripts.compare_ground_truth import evidence_flag_one, spearman
from app.scripts.prepare_flawed_suite_data import (
    PRIMARY_TRAIN_SIZE,
    REPO_ROOT,
    EVAL_SIZE,
    _apply_fairness_flip,
    _apply_safety_flip,
    _build_eval_set,
    _sample_slice,
    _write_csv,
    _write_jsonl,
    _write_manifest,
    existing_suite_texts,
    validate_out_dir,
)
from app.scripts.run_defect_severity import monotonicity

ROOT = REPO_ROOT / "results" / "osd_calibration_20261003"
CAL = ROOT / "calibration"
FROZEN_PATH = CAL / "frozen_mapping.json"
SEED = 43
RATES = (0.3, 0.6, 1.0)
ROB_BUDGETS = (0.02, 0.04, 0.06, 0.10)
ROB_MAX_BUDGET = 0.10
L5_ROOT = REPO_ROOT / "results" / "fairness_confirm_20261003"
L6 = REPO_ROOT / "results" / "defect_severity_20261003" / "analysis.json"
L6_A2 = REPO_ROOT / "results" / "defect_severity_20261003_a2" / "analysis.json"
FAMILIES = ("FAIRNESS", "ROBUSTNESS", "SAFETY")


def model_names() -> list[str]:
    return ["clean"] + [f"{k}_r{round(r * 100):03d}" for k in ("fairness", "safety") for r in RATES]


def calibration_exclusions() -> set[str]:
    """Every text of the existing suite and of the L5 confirm data (eval + train)."""
    texts = existing_suite_texts()
    for p in sorted((L5_ROOT / "data").glob("*.jsonl")):
        texts.update(json.loads(line)["text"] for line in p.read_text(encoding="utf-8").splitlines())
    return texts


def prepare_calibration(test_ds: Any, train_ds: Any, *, seed: int, out: Path, exclude_texts: set[str],
                        eval_size: int = EVAL_SIZE, train_size: int = PRIMARY_TRAIN_SIZE) -> dict[str, Any]:
    out = validate_out_dir(out)
    data = out / "data"
    eval_rows = _build_eval_set(test_ds, seed=seed, size=eval_size, exclude_texts=exclude_texts)
    if len(eval_rows) != eval_size:
        raise ValueError(f"eval set has {len(eval_rows)} rows after exclusions, need {eval_size}")
    _write_jsonl(data / "eval_set.jsonl", eval_rows)
    _write_csv(data / "eval_set.csv", eval_rows)
    _write_manifest(data / "eval_set_manifest.json", {
        "role": "L1 calibration eval set", "dataset": "google/civil_comments", "split": "test", "seed": seed,
        "size": len(eval_rows), "excluded_texts": len(exclude_texts),
        "note": "disjoint by exact text from every suite slice and the L5 confirm data"})
    clean = _sample_slice(train_ds, size=train_size, seed=seed, exclude_texts=set(exclude_texts) | {
        r["text"] for r in eval_rows})
    if len(clean) != train_size:
        raise ValueError(f"train slice has {len(clean)} rows after exclusions, need {train_size}")
    _write_jsonl(data / "clean_train.jsonl", clean)
    _write_manifest(data / "clean_data_manifest.json", {"seed": seed, "size": len(clean), "flip_rate": 0.0})
    flips = {"fairness": _apply_fairness_flip, "safety": _apply_safety_flip}
    for kind, flip in flips.items():
        for rate in RATES:
            name = f"{kind}_r{round(rate * 100):03d}"
            rows, flipped = flip(clean, seed=seed, rate=rate)
            _write_jsonl(data / f"{name}_train.jsonl", rows)
            _write_manifest(data / f"{name}_data_manifest.json", {
                "flaw_target": kind.upper(), "seed": seed, "size": len(rows), "flip_rate": rate,
                "rows_flipped": len(flipped), "base_slice": "clean_train.jsonl", "nested": True})
    return {"out": out, "seed": seed, "models": model_names()}


# --- fit / freeze ----------------------------------------------------------


def fit_anchors(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """OLS e = alpha + beta*s; anchors (alpha, alpha + beta), None when beta <= 0."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx if sxx else 0.0
    if beta <= 1e-12:
        return None
    alpha = my - beta * mx
    return alpha, alpha + beta


def _evidence(dim: str, m: dict[str, Any]) -> float | None:
    measured = agent._v4_evidence(FriesDimension(dim), m)
    return None if measured is None else measured[0]


def check_frozen(frozen: dict[str, Any]) -> None:
    code = {"version": agent.OSD_MAP_V4["version"], "calibration_sha256": agent.OSD_MAP_V4["calibration_sha256"],
            "anchors": {k: list(v) for k, v in agent.OSD_MAP_V4["anchors"].items()}}
    want = {k: frozen[k] for k in ("version", "calibration_sha256", "anchors")}
    if json.loads(json.dumps(code)) != want:
        raise RuntimeError(f"agent.OSD_MAP_V4 {code} differs from frozen mapping {want}")


# --- held-out --------------------------------------------------------------


def map_both(dim: str, m: dict[str, Any]) -> dict[str, Any]:
    ctx = AgentContext(evaluation_id=uuid.uuid4(), model_ref="heldout", model_metadata={},
                       probe_results=[ProbeSnapshot(dimension=FriesDimension(dim), metric_values=m, confidence=None,
                                                    evidence_refs=[])])
    out = {}
    for mapping in ("v3", "v4"):
        a = next(x for x in HeuristicOSDAgent(mapping=mapping).propose(ctx).aspects if x.aspect.value == dim)
        band = [a.O, a.S, a.D]
        ok = all(isinstance(v, int) for v in band)
        out[mapping] = {"band": band, "aspect_score": round(aspect_score([OSDTriple(*band)]), 4) if ok else None}
    return out


def family_metrics(levels: list[float], ys: list[float | None]) -> dict[str, Any]:
    """Expected direction: O/S/D and score decrease as controlled severity rises."""
    mono = monotonicity(levels, ys, increasing=False)
    vals = [y for y in ys if y is not None]
    return {**mono, "abstentions": len(ys) - len(vals), "range": round(max(vals) - min(vals), 4) if vals else None,
            "distinct_values": len(set(vals))}


def _heldout_rows() -> dict[str, list[dict[str, Any]]]:
    """Frozen held-out evidence as (level, metrics, risk flag) per family; nothing re-measured."""
    gt = json.loads((L5_ROOT / "ground_truth.json").read_text(encoding="utf-8"))
    fair = []
    for name, entry in gt["models"].items():
        if "flip_rate" not in entry:
            continue
        m = json.loads((L5_ROOT / "analysis" / "raw" / f"{name}__run1.json").read_text(encoding="utf-8"))["metric_values"]
        fair.append({"model": name, "level": entry["flip_rate"], "metrics": m,
                     "risk": evidence_flag_one("FAIRNESS", m, None)})
    l6 = json.loads(L6.read_text(encoding="utf-8"))["safety"]
    control = next(r for r in l6 if r.get("role") == "control")
    safety = []
    for r in l6:
        if r.get("role") == "control":
            continue
        m = {"severe_fnr": r["severe_fnr"], "fnr_ratio": r["fnr_ratio"], "behavior": {
            "status": r["behavior_status"], "severe_fnr_ci": r["severe_fnr_ci"]}}
        safety.append({"model": r["model"], "level": r["injected_rate"], "metrics": m,
                       "risk": bool(r["risks_triggered"]), "gt_evidence_flag": r["ground_truth_safety_flag"]})
    rob = []
    for r in json.loads(L6_A2.read_text(encoding="utf-8"))["robustness"]:
        m = {k: r[k] for k in ("clean_accuracy", "robust_accuracy", "aspect_scoring")}
        rob.append({"model": "variant3_explainability", "level": r["attack_budget"], "metrics": m,
                    "risk": bool(r["risks_triggered"]) or r["aspect_scoring"] in ("risk_detected", "scored_risk")})
    return {"FAIRNESS": sorted(fair, key=lambda x: x["level"]), "SAFETY": sorted(safety, key=lambda x: x["level"]),
            "ROBUSTNESS": rob, "_control_severe_fnr": control["severe_fnr"]}


def heldout_analysis() -> dict[str, Any]:
    rows = _heldout_rows()
    out: dict[str, Any] = {}
    for fam in FAMILIES:
        recs = []
        for r in rows[fam]:
            e = _evidence(fam, r["metrics"])
            blocked = r["metrics"].get("aspect_scoring") in ("mapping_blocked", "not_scored")
            recs.append({k: v for k, v in r.items() if k != "metrics"}
                        | {"evidence": e, "blocked": blocked, **map_both(fam, r["metrics"])})
        levels = [r["level"] for r in recs]
        ev = monotonicity(levels, [r["evidence"] for r in recs], increasing=True)
        per_map = {}
        for mp in ("v3", "v4"):
            comp = {c: family_metrics(levels, [r[mp]["band"][i] for r in recs]) for i, c in enumerate("OSD")}
            score = family_metrics(levels, [r[mp]["aspect_score"] for r in recs])
            scored = [r for r in recs if r[mp]["aspect_score"] is not None]
            pairs = [(r["evidence"], r[mp]["aspect_score"]) for r in scored if r["evidence"] is not None]
            per_map[mp] = {"O": comp["O"], "S": comp["S"], "D": comp["D"], "score": score,
                           # ordering of the measured evidence itself, independent of the injected level
                           "evidence_vs_score_rho": spearman([p[0] for p in pairs], [p[1] for p in pairs])
                           if len(pairs) >= 3 else None,
                           "score_separation_low_minus_high": round(scored[0][mp]["aspect_score"]
                                                                    - scored[-1][mp]["aspect_score"], 4)
                           if len(scored) >= 2 else None,
                           # measured, not gate-blocked, yet no complete band
                           "mapping_failures": sum(1 for r in recs if r["evidence"] is not None and not r["blocked"]
                                                   and r[mp]["aspect_score"] is None)}
        out[fam] = {"levels": recs, "evidence": ev, "risk_detected_levels": [r["level"] for r in recs if r["risk"]],
                    "v3": per_map["v3"], "v4": per_map["v4"]}
    ref = json.loads((L5_ROOT / "analysis" / "raw" / "reference_toxicbert_2label__run1.json").read_text(
        encoding="utf-8"))["metric_values"]
    ctrl = next(r for r in json.loads(L6.read_text(encoding="utf-8"))["safety"] if r.get("role") == "control")
    ctrl_m = {"severe_fnr": ctrl["severe_fnr"], "fnr_ratio": ctrl["fnr_ratio"], "behavior": {"status": ctrl["behavior_status"]}}
    out["controls"] = {
        "FAIRNESS reference_toxicbert_2label (L5)": {"evidence": _evidence("FAIRNESS", ref),
                                                     "risk": evidence_flag_one("FAIRNESS", ref, None), **map_both("FAIRNESS", ref)},
        "SAFETY reference_toxicbert_2label (L6)": {"evidence": ctrl["severe_fnr"], **map_both("SAFETY", ctrl_m)},
    }
    out["SAFETY"]["gt_evidence_flag_levels"] = [r["level"] for r in rows["SAFETY"] if r["gt_evidence_flag"]]
    out["SAFETY"]["control_severe_fnr"] = rows["_control_severe_fnr"]
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prepare", "train", "measure", "fit", "heldout"])
    ap.add_argument("--heldout-out", default="heldout", help="held-out output folder name under the root (new folder)")
    args = ap.parse_args(argv)
    if args.stage == "heldout":
        stage_heldout(args.heldout_out)
    else:
        globals()[f"stage_{args.stage}"]()


def stage_prepare() -> None:
    from datasets import load_dataset

    test_ds = load_dataset("google/civil_comments", split="test")
    train_ds = load_dataset("google/civil_comments", split="train")
    res = prepare_calibration(test_ds, train_ds, seed=SEED, out=CAL, exclude_texts=calibration_exclusions())
    print(res)


def stage_train() -> None:
    from app.scripts.train_flawed_suite import VariantSpec, train_variant

    for n in model_names():
        spec = VariantSpec(n, n, f"{n}_train.jsonl", f"{n}_data_manifest.json", 3, 2e-5, 16, 0.01)
        train_variant(spec, seed=SEED, data_dir=CAL / "data", models_dir=CAL / "models")


def stage_measure() -> None:
    from app.scripts import run_defect_severity as l6
    from app.scripts.run_fairness_confirm import probe_once

    csv_bytes = (CAL / "data" / "eval_set.csv").read_bytes()
    models = CAL / "models"
    rows: list[dict[str, Any]] = []

    def keep(fam: str, name: str, level: float, s: float, m: dict[str, Any], **extra: Any) -> None:
        rows.append({"family": fam, "model": name, "level": level, "s": s, "evidence": _evidence(fam, m),
                     "aspect_scoring": m.get("aspect_scoring"), "risks_triggered": m.get("risks_triggered"), **extra})
        print(fam, name, level, rows[-1]["evidence"], flush=True)

    for name, rate in [("clean", 0.0)] + [(f"fairness_r{round(r * 100):03d}", r) for r in RATES]:
        keep("FAIRNESS", name, rate, rate, probe_once(models / name, csv_bytes).metric_values)
    for name, rate in [("clean", 0.0)] + [(f"safety_r{round(r * 100):03d}", r) for r in RATES]:
        keep("SAFETY", name, rate, rate, l6.safety_once(models / name, csv_bytes).metric_values)
    rob_bytes, dropped = l6.perturbable_rows(csv_bytes)
    for budget in ROB_BUDGETS:
        m = l6.robustness_once(models / "clean", rob_bytes, budget).metric_values
        keep("ROBUSTNESS", "clean", budget, budget / ROB_MAX_BUDGET, m,
             clean_accuracy=m.get("clean_accuracy"), robust_accuracy=m.get("robust_accuracy"))
    (CAL / "calibration_evidence.json").write_text(json.dumps(
        {"seed": SEED, "eval_set_sha256": hashlib.sha256(csv_bytes).hexdigest(),
         "robustness_rows_dropped_unperturbable": dropped, "rows": rows}, indent=2), encoding="utf-8")


def stage_fit() -> None:
    if FROZEN_PATH.exists():
        raise FileExistsError(f"{FROZEN_PATH} is frozen; refusing to refit")
    raw = (CAL / "calibration_evidence.json").read_bytes()
    rows = json.loads(raw)["rows"]
    anchors, fits = {}, {}
    for fam in FAMILIES:
        pts = [(r["s"], r["evidence"]) for r in rows if r["family"] == fam and r["evidence"] is not None]
        fit = fit_anchors(pts)
        fits[fam] = {"points": pts, "anchors": fit, "calibration_monotonicity": monotonicity(
            [p[0] for p in pts], [p[1] for p in pts], increasing=True)}
        if fit is not None:
            anchors[fam] = [round(fit[0], 6), round(fit[1], 6)]
    frozen = {"version": agent.OSD_MAP_V4["version"], "calibration_sha256": hashlib.sha256(raw).hexdigest(),
              "anchors": anchors, "fits": fits, "frozen_at": datetime.now(UTC).isoformat(),
              "rule": "x = clip((e - a)/(b - a), 0, 1); O = S = floor(9 - 8x + 0.5); D and abstention as v3",
              "code": "app/osd/agent.py OSD_MAP_V4 / calibrated_level / _v4_band; app/scripts/run_osd_calibration.py"}
    FROZEN_PATH.write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    print(json.dumps(frozen, indent=2))


def stage_heldout(name: str = "heldout") -> None:
    frozen = json.loads(FROZEN_PATH.read_text(encoding="utf-8"))
    check_frozen(frozen)
    out = validate_out_dir(ROOT / name)
    out.mkdir(parents=True)
    res = {"frozen_mapping_sha256": hashlib.sha256(FROZEN_PATH.read_bytes()).hexdigest(),
           "frozen_at": frozen["frozen_at"], "evaluated_at": datetime.now(UTC).isoformat(),
           "anchors": frozen["anchors"], "families": heldout_analysis()}
    (out / "analysis.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({f: {k: res["families"][f][k] for k in ("evidence", "v3", "v4")} for f in FAMILIES}, indent=2))


if __name__ == "__main__":
    main()
