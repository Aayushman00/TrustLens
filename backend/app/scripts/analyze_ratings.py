"""Human validation of individual audit findings (not of "trust").

``packet``: turn saved evaluation JSONs into an anonymised findings sheet —
one row per (model, dimension) finding with its measured evidence — plus a
separate key file kept by one team member. Reviewers mark each finding
SUPPORTED / NOT_SUPPORTED / UNCERTAIN: does the evidence support it?

``analyze``: Fleiss' kappa across raters, per-finding majority verdict,
share of TrustLens findings the majority supports, and the disagreements.
With a handful of raters and findings this is descriptive, not inference.

Usage (from backend/)::
    python -m app.scripts.analyze_ratings packet <results_dir> <out_dir> [--seed 7]
    python -m app.scripts.analyze_ratings analyze <ratings.csv>
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

VERDICTS = ("SUPPORTED", "NOT_SUPPORTED", "UNCERTAIN")
_EVIDENCE_KEYS = (
    "demographic_parity_difference", "equalized_odds_difference", "excess_dpd", "label_rate_gap",
    "clean_accuracy", "robust_accuracy", "accuracy_drop", "severe_fnr", "fnr_ratio",
    "coverage_ratio", "pass_count", "fail_count", "risks_triggered", "aspect_scoring",
    "probe_status_reason", "flags",
)


def fleiss_kappa(table: list[list[int]]) -> float:
    """``table[i][j]`` = raters putting subject i in category j (same n per row)."""
    n = sum(table[0])
    N = len(table)
    p_j = [sum(row[j] for row in table) / (N * n) for j in range(len(table[0]))]
    P_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in table]
    P_bar = sum(P_i) / N
    P_e = sum(p * p for p in p_j)
    return 1.0 if P_e == 1 else (P_bar - P_e) / (1 - P_e)


def analyze(ratings_csv: Path) -> dict[str, Any]:
    by_finding: dict[str, list[str]] = defaultdict(list)
    raters: set[str] = set()
    with Path(ratings_csv).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            verdict = row["verdict"].strip().upper()
            if verdict not in VERDICTS:
                raise ValueError(f"bad verdict {verdict!r} for {row['finding_id']}")
            by_finding[row["finding_id"]].append(verdict)
            raters.add(row["rater"])
    counts = {fid: Counter(v) for fid, v in by_finding.items()}
    majority = {fid: c.most_common(1)[0][0] for fid, c in counts.items()}
    complete = [fid for fid, v in by_finding.items() if len(v) == len(raters)]
    return {
        "n_findings": len(by_finding),
        "n_raters": len(raters),
        "fleiss_kappa": (
            fleiss_kappa([[counts[fid][v] for v in VERDICTS] for fid in complete])
            if len(raters) > 1 and complete
            else None
        ),
        "majority": majority,
        "supported_rate": sum(v == "SUPPORTED" for v in majority.values()) / len(majority),
        "not_supported": sorted(fid for fid, v in majority.items() if v == "NOT_SUPPORTED"),
        "split": sorted(fid for fid, c in counts.items() if len(c) > 1),
    }


def packet(results_dir: Path, out_dir: Path, seed: int) -> None:
    evals = sorted(p for p in Path(results_dir).glob("*.json") if not p.name.startswith("_"))
    names = [p.stem for p in evals]
    random.Random(seed).shuffle(names)
    code = {name: f"Model {i + 1:02d}" for i, name in enumerate(names)}
    findings, key = [], []
    for p in evals:
        ev = json.loads(p.read_text(encoding="utf-8"))
        for probe in ev.get("probes", []):
            m = probe.get("metric_values") or {}
            fid = f"F{len(findings) + 1:03d}"
            evidence = {k: m[k] for k in _EVIDENCE_KEYS if m.get(k) is not None}
            if isinstance(m.get("behavior"), dict):
                evidence["behavior"] = {k: v for k, v in m["behavior"].items() if k in ("status", "severe_n", "severe_fnr", "severe_fnr_ci", "harmful_recall", "benign_fpr")}
            findings.append({
                "finding_id": fid,
                "model_code": code[p.stem],
                "dimension": probe.get("dimension"),
                "finding": f"{probe.get('dimension')}: {probe.get('status')} — {m.get('aspect_scoring') or m.get('probe_status_reason') or 'no scored risk'}",
                "evidence_json": json.dumps(evidence, default=str),
            })
            key.append({"finding_id": fid, "model_code": code[p.stem], "model": p.stem})
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, rows in (("findings.csv", findings), ("KEY_do_not_share.csv", key)):
        with (out_dir / fname).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    with (out_dir / "rating_sheet.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["finding_id", "rater", "verdict", "comment"])
        w.writerows([[row["finding_id"], "", "", ""] for row in findings])
    print(f"{len(findings)} findings for {len(evals)} models -> {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pk = sub.add_parser("packet")
    pk.add_argument("results_dir")
    pk.add_argument("out_dir")
    pk.add_argument("--seed", type=int, default=7)
    an = sub.add_parser("analyze")
    an.add_argument("ratings_csv")
    args = ap.parse_args()
    if args.cmd == "packet":
        packet(Path(args.results_dir), Path(args.out_dir), args.seed)
    else:
        print(json.dumps(analyze(Path(args.ratings_csv)), indent=2))


if __name__ == "__main__":
    main()
