"""Analyse a second, independent reviewer round with the same form and the same frozen reference.

stdlib only. Run from the repo root after exporting the new Form responses to a NEW csv (never overwrite
the round-1 export):

    python results/l10_human_form/analyze_round2.py "<new responses>.csv" results/l10_human_analysis_round2

Differences from round 1: every reviewer must have a distinct code (the script refuses duplicates), and the
output is a neutral table, not a narrative. Reviewers are evidence readers, not ground truth.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import analyze_human_responses as m


def main(raw: Path, out: Path) -> None:
    m.RAW = raw
    resp = m.load()
    ref = json.loads(m.REF.read_text(encoding="utf-8"))
    pm = json.loads(m.MAP.read_text(encoding="utf-8"))["packets"]
    codes = Counter(r["code"] for r in resp if r["pid"] == "P01")
    dup = [c for c, n in codes.items() if n > 1]
    if dup:
        sys.exit(f"reviewer codes must be distinct; repeated: {dup}")
    raters = sorted(codes)
    ag = m.agreement(resp, set(r["rid"] for r in resp))
    out.mkdir(parents=True, exist_ok=True)
    rows, match = [], 0
    for p in sorted(pm):
        rs = [r for r in resp if r["pid"] == p]
        top, n, tot = m.majority([r["Q2"] for r in rs])
        tl = ref[pm[p]["frozen_packet"]]["risk_present"]
        match += top == tl
        rows.append((p, pm[p]["dimension"], tl, top, f"{n}/{tot}"))
    lines = [f"# Second reviewer round ({len(raters)} distinct reviewers)", "",
             f"Reviewers: {', '.join(raters)}. Frozen reference: `{m.REF.relative_to(m.ROOT)}`.", "",
             "| packet | dimension | TrustLens risk | human majority (Q2) | votes |", "|---|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    lines += ["", f"Majority matches TrustLens on risk presence for {match} of {len(rows)} packets.", "",
              "| question | mean pairwise agreement | Fleiss kappa | unanimous packets |", "|---|---|---|---|"]
    for q in ("Q1", "Q2", "Q3"):
        a = ag[q]
        k = "n/a" if a["fleiss"] is None else f"{a['fleiss']:.2f}"
        lines.append(f"| {q} | {a['mean_pairwise']:.2f} | {k} | {a['unanimous']}/12 |")
    lines += ["", f"Severity (Q4): Krippendorff alpha {ag['Q4']['alpha']}, exact {ag['Q4']['exact']:.2f}, "
              f"within 1 {ag['Q4']['within1']:.2f}.", "",
              "Descriptive only: a few reviewers cannot validate TrustLens statistically."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "agreement.json").write_text(json.dumps(ag, indent=1, default=str), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
