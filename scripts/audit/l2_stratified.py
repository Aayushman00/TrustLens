"""Recompute L2 det-vs-LLM stats stratified by evaluator, from stored run records.

Read-only on results/; reuses run_l2_interpretation.compare so definitions match the report.
Usage: python scripts/audit/l2_stratified.py [--write results/l2_stratified_audit_20261023/]
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.scripts.run_l2_interpretation import compare  # noqa: E402

SRC = ROOT / "results" / "l2_det_vs_llm_20261022_r4"
KEYS = ["llm_answered_pairs", "exact_status_agreement", "risk_present_agreement_definite", "n_definite_pairs",
        "severity_exact", "severity_mae", "osd_exact_triple", "O_mae", "S_mae", "D_mae", "llm_runs",
        "llm_fallbacks", "llm_repeatability_pairs", "llm_risk_repeatable_pairs", "llm_osd_repeatable_pairs",
        "llm_mean_risk_agreement"]


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--write", type=Path)
    ap.add_argument("--det", type=Path, default=SRC / "deterministic.json", help="deterministic baseline file"); a = ap.parse_args()
    det = json.loads(a.det.read_text(encoding="utf-8"))
    runs = json.loads((SRC / "llm_runs.json").read_text(encoding="utf-8"))
    strata = {"providers_only(gemini+groq)": lambda r: r["provider"] in {"gemini", "groq"},
              "claude_supplement_only": lambda r: r["provider"] == "claude",
              "combined(heterogeneous)": lambda r: True}
    out = {}
    for name, keep in strata.items():
        sub = {}
        for pid, rs in runs.items():
            # runs from other strata become fallbacks so llm_modal ignores them
            sub[pid] = [r if keep(r) else {**r, "fallback": True, "dimensions": None, "provider": None,
                                          "parse_failures": 0, "output_truncated": False,
                                          "provider_unavailable": False, "superseded_attempt_records": 0,
                                          "replayed": False} for r in rs]
        s = compare(det, sub)["summary"]
        s["_runs_ok"] = sum(not r["fallback"] for rs in sub.values() for r in rs)
        out[name] = {k: s[k] for k in KEYS if k in s} | {"valid_runs": s["_runs_ok"], "categories": s["categories"]}
    txt = json.dumps(out, indent=2)
    print(txt)
    if a.write:
        a.write.mkdir(parents=True, exist_ok=False)
        (a.write / "stratified.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
