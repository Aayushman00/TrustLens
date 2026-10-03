"""Summarise the real Hub model evaluations into one table (descriptive only;
no trust labels exist for these models).

Usage (from backend/)::  python -m app.scripts.summarize_hub_models <out_dir> <run_dir> [<run_dir> ...]
"""
from __future__ import annotations

import json
import sys
from typing import Any

from app.scripts.run_flawed_suite_eval import SUITE_DIR


def _row(ev: dict[str, Any], repo: str) -> dict[str, Any]:
    pm = {p["dimension"]: p.get("metric_values") or {} for p in ev.get("probes", [])}
    fs = ev.get("final_score") or {}
    b = pm.get("SAFETY", {}).get("behavior") or {}
    integ = pm.get("INTEGRITY", {})
    aspects = (ev.get("osd_agent") or {}).get("ai_suggestion", {}).get("aspects", [])
    llm = sorted({str(a.get("O_source")) for a in aspects if a.get("aspect") in ("INTEGRITY", "EXPLAINABILITY")})
    return {
        "repo": repo,
        "status": ev.get("status"),
        "fries": fs.get("fries_score"),
        "scoring": (ev.get("mode_disclosure") or {}).get("fries_status"),
        "clean_acc": pm.get("ROBUSTNESS", {}).get("clean_accuracy"),
        "acc_drop": pm.get("ROBUSTNESS", {}).get("accuracy_drop"),
        "eod": pm.get("FAIRNESS", {}).get("equalized_odds_difference"),
        "excess_dpd": pm.get("FAIRNESS", {}).get("excess_dpd"),
        "harmful_recall": b.get("harmful_recall"),
        "severe_fnr": b.get("severe_fnr"),
        "benign_fpr": b.get("benign_fpr"),
        "hash_check": (integ.get("identity") or {}).get("hash_comparison"),
        "integrity_risks": integ.get("risks_triggered"),
        "flags": sorted({f for p in pm.values() for f in (p.get("flags") or []) if f in ("constant_predictor", "group_single_label_class")}),
        "llm_source": llm,
        "dimension_scores": fs.get("dimension_scores"),
    }


def main() -> None:
    out = SUITE_DIR / sys.argv[1]
    out.mkdir(exist_ok=True)
    rows = []
    for d in sys.argv[2:]:
        summary = json.loads((SUITE_DIR / d / "_summary.json").read_text(encoding="utf-8"))
        for s in summary:
            f = SUITE_DIR / d / f"{s['repo'].replace('/', '__')}.json"
            if f.exists():
                rows.append({**_row(json.loads(f.read_text(encoding="utf-8")), s["repo"]), "revision": s.get("revision"), "run_dir": d})
            else:
                rows.append({"repo": s["repo"], "status": s.get("status"), "error": s.get("error"), "run_dir": d})
    (out / "hub_models.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    fmt = lambda x: "—" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))  # noqa: E731
    cols = ["repo", "status", "fries", "scoring", "clean_acc", "acc_drop", "eod", "harmful_recall", "severe_fnr", "benign_fpr", "hash_check", "llm_source"]
    md = ["# Real Hugging Face models (single run each, descriptive)", "",
          "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(fmt(r.get(c)) for c in cols) + " |" for r in rows]
    (out / "hub_models.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
