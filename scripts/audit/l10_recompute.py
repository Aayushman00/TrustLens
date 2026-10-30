"""Independent recomputation of L10 human agreement from the raw form CSV (does not import the original script).
Q1-Q3: mean pairwise agreement + Fleiss kappa over 12 packets. Q4: Krippendorff alpha (interval), Q2==YES only.
Usage: python scripts/audit/l10_recompute.py"""
import csv, json
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rows = list(csv.reader((ROOT / "L10 Evidence Review - responses - Form Responses 1.csv").open(encoding="utf-8")))[1:]
ref = json.loads((ROOT / "results/l10_human_analysis_20261005/agreement.json").read_text())


def cell(row, p, q): return row[2 + 5 * p + q].strip()


def fleiss(tab):  # tab: list of Counter per packet, same n raters each
    n = sum(tab[0].values()); N = len(tab); cats = {c for t in tab for c in t}
    P = [(sum(v * v for v in t.values()) - n) / (n * (n - 1)) for t in tab]
    pj = {c: sum(t[c] for t in tab) / (N * n) for c in cats}
    Pe = sum(v * v for v in pj.values()); Pb = sum(P) / N
    return (Pb - Pe) / (1 - Pe) if Pe < 1 else float("nan")


def alpha_interval(units):  # units: list of value lists (>=2 values to be pairable)
    units = [u for u in units if len(u) >= 2]
    n = sum(len(u) for u in units)
    do = sum(sum((a - b) ** 2 for a, b in combinations(u, 2)) * 2 / (len(u) - 1) for u in units) / n
    allv = [v for u in units for v in u]
    de = sum((a - b) ** 2 for a, b in combinations(allv, 2)) * 2 / (n * (n - 1))
    return 1 - do / de


for name, sel in [("all7", rows), ("R0_only", [r for r in rows if r[1] == "R0"])]:
    out = {}
    for qi, q in enumerate(["Q1", "Q2", "Q3"]):
        tabs = [Counter(cell(r, p, qi).upper() for r in sel) for p in range(12)]
        pw = [sum(a == b for a, b in combinations([cell(r, p, qi).upper() for r in sel], 2)) / (len(sel) * (len(sel) - 1) / 2) for p in range(12)]
        out[q] = (round(sum(pw) / 12, 4), round(fleiss(tabs), 4), sum(len(t) == 1 for t in tabs))
    units, ex, w1, tot = [], 0, 0, 0
    for p in range(12):
        u = [int(cell(r, p, 3)[0]) for r in sel if cell(r, p, 1).upper() == "YES" and cell(r, p, 3)[:1].isdigit()]
        units.append(u)
        for a, b in combinations(u, 2): tot += 1; ex += a == b; w1 += abs(a - b) <= 1
    out["Q4"] = (round(alpha_interval(units), 4), tot, round(ex / tot, 4), round(w1 / tot, 4))
    r = ref[name]
    ok = all(abs(out[q][0] - r[q]["mean_pairwise"]) < 1e-3 and abs(out[q][1] - r[q]["fleiss"]) < 1e-3 for q in ("Q1", "Q2", "Q3")) \
        and abs(out["Q4"][0] - r["Q4"]["alpha"]) < 1e-3 and out["Q4"][1] == r["Q4"]["n_pairs"]
    print(name, out, "MATCHES_ORIGINAL" if ok else "MISMATCH")
