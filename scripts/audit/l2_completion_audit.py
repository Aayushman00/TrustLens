"""Completion audit of the L2 deterministic-vs-LLM experiment (60 planned runs).

Read-only on results/. Checks every planned run against the experiment's expectations (valid output schema,
intended packet and run index, frozen prompt hash, recorded temperature) and recomputes the statistics per
evaluator stratum. Reuses run_l2_interpretation.compare so the definitions match the report.

Usage (from backend/): python ../scripts/audit/l2_completion_audit.py [--det <deterministic.json>] [--write out.json]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.scripts.run_l2_interpretation import compare  # noqa: E402

RES = ROOT / "results"
ORIGINAL = RES / "l2_det_vs_llm_20261003_r3"  # frozen record of the first 22 valid answers
FINAL = RES / "l2_det_vs_llm_20261029_r5"  # complete record: r3 plus re-attempts
KEYS = ["llm_answered_pairs", "exact_status_agreement", "risk_present_agreement_definite", "n_definite_pairs",
        "severity_exact", "severity_within_1", "severity_mae", "osd_exact_triple", "O_mae", "S_mae", "D_mae",
        "llm_repeatability_pairs", "llm_risk_repeatable_pairs", "llm_osd_repeatable_pairs", "llm_mean_risk_agreement"]


def masked(rs, keep):
    blank = {"fallback": True, "dimensions": None, "provider": None, "parse_failures": 0, "output_truncated": False,
             "provider_unavailable": False, "superseded_attempt_records": 0, "replayed": False}
    return [r if keep(r) else {**r, **blank} for r in rs]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--det", type=Path, default=FINAL / "deterministic.json")
    ap.add_argument("--write", type=Path)
    a = ap.parse_args()
    det = json.loads(a.det.read_text(encoding="utf-8"))
    runs = json.loads((FINAL / "llm_runs.json").read_text(encoding="utf-8"))
    orig = json.loads((ORIGINAL / "llm_runs.json").read_text(encoding="utf-8"))
    orig_ok = {(p, r["run_index"]) for p, rs in orig.items() for r in rs if not r["fallback"]}
    log = [json.loads(line) for line in (FINAL / "llm_responses.jsonl").read_text(encoding="utf-8").splitlines()]

    final_ok = {(p, r["run_index"]): r for p, rs in runs.items() for r in rs if not r["fallback"]}
    planned = {(p, i) for p in runs for i in range(1, 6)}
    prompt_hashes = {}
    bad = []
    for (p, i), r in final_ok.items():
        prompt_hashes.setdefault(p, set()).add(r["prompt_sha256"])
        if r["packet_id"] != p or r["run_index"] != i or set(r["dimensions"]) != {"INTEGRITY", "EXPLAINABILITY", "SAFETY"}:
            bad.append((p, i))
    temps = Counter()
    for rec in log:
        temps[(rec["provenance"].get("llm_provider"), rec["provenance"].get("llm_temperature"),
               rec["prompt_version"])] += 1
    attempts = Counter()
    for rec in log:
        for att in rec["attempts"]:
            attempts[(att["provider"], "ok" if "raw" in att else att["error"].split(":")[0])] += 1
    summary = {
        "planned_runs": len(planned),
        "valid_original_runs_already_available": len(orig_ok),
        "recovered_runs": len(set(final_ok) - orig_ok),
        "valid_runs_now": len(final_ok),
        "unresolved_runs": sorted(planned - set(final_ok)),
        "schema_or_identity_violations": bad,
        "packets_with_one_prompt_hash_across_runs": all(len(v) == 1 for v in prompt_hashes.values()),
        "providers_of_valid_runs": dict(Counter(r["provider"] for r in final_ok.values())),
        "original_valid_run_providers": dict(Counter(final_ok[k]["provider"] for k in orig_ok)),
        "recovered_run_providers": dict(Counter(final_ok[k]["provider"] for k in set(final_ok) - orig_ok)),
        "records_in_log": len(log),
        "logged_provider_attempts": {f"{k[0]}:{k[1]}": v for k, v in sorted(attempts.items())},
        "provenance_provider_temperature_prompt": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in temps.items()},
    }
    strata = {
        "pooled_all_60": lambda r: True,
        "first_22_original_answers": lambda r: (r["packet_id"], r["run_index"]) in orig_ok,
        "re-attempted_38": lambda r: (r["packet_id"], r["run_index"]) not in orig_ok,
        "gemini_only": lambda r: r["provider"] == "gemini",
        "groq_only": lambda r: r["provider"] == "groq",
        "nvidia_only": lambda r: r["provider"] == "nvidia",
    }
    out = {"verification": summary, "baseline_file": str(a.det.relative_to(ROOT)), "strata": {}}
    for name, keep in strata.items():
        sub = {pid: masked(rs, keep) for pid, rs in runs.items()}
        s = compare(det, sub)["summary"]
        out["strata"][name] = {k: s[k] for k in KEYS if k in s} | {
            "valid_runs": sum(not r["fallback"] for rs in sub.values() for r in rs)}
    txt = json.dumps(out, indent=2, default=str)
    print(txt)
    if a.write:
        a.write.write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
