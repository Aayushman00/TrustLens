"""Fails (exit 1) if a number plotted in the figures differs from the number printed in the report text.

Run from report/:  python check_figures.py
Reads the same result files as make_figures_final.py and compares them with chapters/*.tex.
"""
import json, os, re, sys

R = os.path.join("..", "results")
C = "chapters"
tex = {f: open(os.path.join(C, f), encoding="utf-8").read().replace("\r\n", "\n") for f in os.listdir(C) if f.endswith(".tex")}
ch4, ch7, ch6 = tex["ch4_fries.tex"], tex["ch7_results.tex"], tex["ch6_experiment.tex"]
bad = []


def need(cond, msg):
    if not cond:
        bad.append(msg)


def row(text, label):
    for line in text.splitlines():
        if line.startswith(label):
            return line
    bad.append(f"row not found: {label}")
    return ""


# F2: anchors in the figure (frozen mapping) = Table 4.3
fm = json.load(open(os.path.join(R, "osd_calibration_20261003", "calibration", "frozen_mapping.json")))["anchors"]
for k in ("FAIRNESS", "ROBUSTNESS", "SAFETY"):
    need(any(all(f"{v:.6f}" in l for v in fm[k]) for l in ch4.splitlines()), f"F2 anchors {k} {fm[k]} not in Table 4.3")

# F3: forest plot = Table 7.3 (point estimate, CI, width)
a = json.load(open(os.path.join(R, "fairness_confirm_20261003", "analysis", "analysis.json")))["models"]
nums = lambda line: [float(x) for x in re.findall(r"\d+\.\d+", line)]
for m, lab in (("clean_control", "clean control (0) &"), ("fairness_r020", "flip 0.2 &"), ("fairness_r040", "flip 0.4 &"),
               ("fairness_r070", "flip 0.7 &"), ("fairness_r100", "flip 1.0 &"), ("reference_toxicbert_2label", "2-label reference &")):
    d = a[m]["eopp_ci"]
    r = row(ch7, lab)
    for name, v in (("EOD", d["point"]), ("CI lower", d["ci_lower"]), ("CI upper", d["ci_upper"]), ("width", d["ci_upper"] - d["ci_lower"])):
        near = [x for x in nums(r) if abs(x - v) < 0.0006]
        need(bool(near), f"F3 {m}: {name} {v:.4f} not in Table 7.3 row")
        if near and abs(near[0] - round(v, 3)) > 1e-9:
            print(f"note: F3 {m} {name}: data {v:.4f} rounds to {v:.3f}, text prints {near[0]:.3f}")

# F4: agree / differ / uncertain counts = the counts quoted in Section 7.10
l2 = json.load(open(os.path.join(R, "l2_det_vs_llm_20261029_r5", "analysis.json")))["per_dimension"]
agree = sum(round(l2[d]["status_agreement"] * l2[d]["n"]) for d in l2)
unc = sum(l2[d]["det_uncertain"] for d in l2)
n = sum(l2[d]["n"] for d in l2)
need(f"{agree}/{n} (0.306" in ch7, f"F4 exact agreement {agree}/{n} not in text")
need(f"uncertain on {unc} pairs" in ch7, f"F4 uncertain {unc} not in text")
need(f"on the {n - unc} definite pairs the two answers agree {agree} times" in ch7, "F4 definite/agree counts not in text")

# F5: Table 7.7 percentages, CIs and kappa
hh = json.load(open(os.path.join(R, "l10_human_analysis_20261005", "agreement.json")))
for key, setlab in (("all7", "all 7"), ("R0_only", "R0 only")):
    for q, lab in (("Q1", "Q1 evidence sufficient" if key == "all7" else "Q1 "), ("Q2", "Q2 risk present" if key == "all7" else "Q2 "),
                   ("Q3", "Q3 FRIES dimension" if key == "all7" else "Q3 ")):
        d = hh[key][q]
        pc = lambda x: f"{round(x * 100):d}"
        want = f"{pc(d['mean_pairwise'])}\\% ({pc(d['ci95'][0])}--{pc(d['ci95'][1])}\\%)"
        r = [l for l in ch7.splitlines() if l.startswith(lab) and setlab in l]
        need(bool(r) and want in r[0] and f"{d['fleiss']:.2f}" in r[0], f"F5 {key} {q}: {want} / {d['fleiss']:.2f} not in Table 7.7")

# F1: quantities drawn in the design diagram appear in the text
for s in ("seed 43", "3\\,000-row", "8\\,000-row", "seven models", "Twelve evidence packets", "Twelve single-dimension packets", "Seven Hub models"):
    need(any(s in t for t in tex.values()), f"F1 phrase not in text: {s}")

if bad:
    print("FIGURE CHECK FAILED"); [print(" -", b) for b in bad]; sys.exit(1)
print("figure check passed: F1-F5 values match the report text")
