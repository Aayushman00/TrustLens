"""Figures for the final report chapters (L1-L6 and external Hub audit).

Run from the report/ directory:  python make_figures_final.py
Reads frozen result files under ../results; the L1 evaluation O/S/D triples are copied from
results/osd_calibration_20261003/FINDINGS.md (the scores are recomputed here with the cube-root rule).
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = os.path.join("..", "results")
OUT = "figures"
BLUE, ORANGE, GREY, INK, GREEN = "#0072B2", "#D55E00", "#8a8f98", "#222222", "#009E73"
plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.edgecolor": "#999999",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 10, "figure.dpi": 150})


def pi(o, s, d):
    return (o * s * d) ** (1 / 3)


# ---------------------------------------------------------------- 1. L5 EOD forest
a = json.load(open(os.path.join(R, "fairness_confirm_20261003", "analysis", "analysis.json")))
order = ["clean_control", "fairness_r020", "fairness_r040", "fairness_r070", "fairness_r100",
         "reference_toxicbert_2label"]
lab = ["clean control", "flip 0.2", "flip 0.4", "flip 0.7", "flip 1.0", "toxic-bert\n(2-label ref.)"]
fig, ax = plt.subplots(figsize=(6.4, 3.0))
for i, m in enumerate(order):
    d = a["models"][m]
    ci = d["eopp_ci"]
    c = ORANGE if d["flagged"] else GREY
    ax.plot([ci["ci_lower"], ci["ci_upper"]], [i, i], color=c, lw=2.2)
    ax.scatter(ci["point"], i, color=c, s=30, zorder=3)
    ax.text(ci["ci_upper"] + 0.006, i, f"w={ci['ci_upper']-ci['ci_lower']:.3f}", va="center", fontsize=7)
ax.axvline(0.02, color=INK, ls="--", lw=0.8)
ax.text(0.021, len(order) - 0.45, r"$\varepsilon$=0.02", fontsize=7)
ax.set_yticks(range(len(order)))
ax.set_yticklabels(lab, fontsize=8)
ax.invert_yaxis()
ax.set_xlabel("equal-opportunity difference (TPR gap), bootstrap 95% CI")
ax.set_title("Confirmatory fairness run: orange = F-FAIR-EOPP raised, grey = not raised", fontsize=9)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_eod_forest.pdf"))
plt.close(fig)

# ---------------------------------------------------------------- 2. v3 vs v4 score on sweeps reserved for evaluation
# (O,S,D) per level, copied from results/osd_calibration_20261003/FINDINGS.md; None = rating withheld
fam = {
    "Fairness (flip rate)": (["0", "0.2", "0.4", "0.7", "1.0"],
                             [None, None, (8, 8, 8), (7, 7, 8), (7, 7, 8)],
                             [None, None, (6, 6, 8), (4, 4, 8), (1, 1, 8)]),
    "Robustness (attack budget)": (["0.01", "0.03", "0.05", "0.08"],
                                   [(9, 9, 8), (9, 8, 8), (9, 8, 8), (9, 7, 8)],
                                   [(9, 9, 8), (6, 6, 8), (3, 3, 8), (1, 1, 8)]),
    "Safety (flip rate)": (["0", "0.25", "0.5", "0.75", "1.0"],
                           [(7, 6, 8), (6, 6, 8), (6, 6, 8), (5, 6, 8), (4, 6, 8)],
                           [(8, 8, 8), (6, 6, 8), (5, 5, 8), (2, 2, 8), (1, 1, 8)]),
}
fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.6), sharey=True)
for ax, (name, (xl, v3, v4)) in zip(axs, fam.items()):
    x = np.arange(len(xl))
    for tr, col, mk, nm in ((v3, GREY, "o", "original bands (v3)"), (v4, ORANGE, "s", "range-scaled mapping (v4)")):
        ys = [pi(*t) if t else np.nan for t in tr]
        ax.plot(x, ys, color=col, marker=mk, ms=4, lw=1.3, label=nm)
    ax.set_xticks(x)
    ax.set_xticklabels(xl, fontsize=7)
    ax.set_title(name, fontsize=8)
    ax.set_ylim(0, 10)
axs[0].set_ylabel("dimension score (0-10)")
axs[0].legend(fontsize=7, frameon=False, loc="lower left")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_v3_v4.pdf"))
plt.close(fig)

# ---------------------------------------------------------------- 3. L6 sweeps
a1 = json.load(open(os.path.join(R, "defect_severity_20261003_a2", "analysis.json")))
a0 = json.load(open(os.path.join(R, "defect_severity_20261003", "analysis.json")))
fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.7))
rb = a1["robustness"]
x = [r["max_changes"] for r in rb]
y = [r["accuracy_drop"] for r in rb]
lo = [r["accuracy_drop_ci"]["ci_lower"] for r in rb]
hi = [r["accuracy_drop_ci"]["ci_upper"] for r in rb]
axs[0].errorbar(x, y, yerr=[np.subtract(y, lo), np.subtract(hi, y)], color=BLUE, marker="o", ms=4, capsize=2, lw=1.2)
axs[0].axhline(0.05, color=INK, ls="--", lw=0.8)
axs[0].text(1.1, 0.0515, r"$\varepsilon_{drop}$=0.05 (no risk below)", fontsize=7)
axs[0].set_xlabel("char swaps per text")
axs[0].set_ylabel("accuracy drop")
axs[0].set_ylim(0, 0.07)
axs[0].set_title("Robustness sweep (A2, after first result, 2,999 rows)", fontsize=8)
sf = [r for r in a0["safety"] if r.get("role") != "control"]
sf.sort(key=lambda r: r["injected_rate"])
x = [r["injected_rate"] for r in sf]
y = [r["severe_fnr"] for r in sf]
lo = [r["severe_fnr_ci"][0] for r in sf]
hi = [r["severe_fnr_ci"][1] for r in sf]
axs[1].errorbar(x, y, yerr=[np.subtract(y, lo), np.subtract(hi, y)], color=ORANGE, marker="s", ms=4, capsize=2, lw=1.2)
ctrl = [r for r in a0["safety"] if r.get("role") == "control"][0]
axs[1].axhline(ctrl["severe_fnr"], color=INK, ls="--", lw=0.8)
axs[1].text(0.02, ctrl["severe_fnr"] + 0.01, "control (toxic-bert 2-label) 0.40", fontsize=7)
axs[1].set_xlabel("injected relabel rate")
axs[1].set_ylabel("severe-harm FNR (Wilson 95% CI)")
axs[1].set_title("Safety sweep", fontsize=9)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_l6.pdf"))
plt.close(fig)

# ---------------------------------------------------------------- 4. external Hub audit profiles (v9 rerun)
# Panels are grouped by the source of the O/S/D rating, because scores from a hosted LLM and from the
# rule-based backup are not like for like. Scores are plotted as reported; nothing is rescaled or ranked.
from matplotlib.patches import Patch
P = json.load(open(os.path.join(R, "external_hub_validation_20261003_v9r", "profiles.json")))["profiles"]
short = {"unitary/toxic-bert": "toxic-bert", "unitary/unbiased-toxic-roberta": "unbiased",
         "s-nlp/roberta_toxicity_classifier": "s-nlp", "martin-ha/toxic-comment-model": "martin-ha",
         "textdetox/xlmr-large-toxicity-classifier": "textdetox",
         "facebook/roberta-hate-speech-dynabench-r4-target": "facebook",
         "gravitee-io/bert-tiny-toxicity": "gravitee"}
scored = [n for n in P if P[n]["dimension_scores_as_reported"] is not None]
withheld = [n for n in P if n not in scored]
llm = [n for n in scored if P[n]["dimensions"]["INTEGRITY"]["osd_source"] == "llm_v1"]
heur = [n for n in scored if n not in llm]
panels = [
    ("Fairness, Robustness, Safety" + chr(10) + "(rule-based bands, all scored models)", scored, ["FAIRNESS", "ROBUSTNESS", "SAFETY"]),
    ("Integrity, Explainability" + chr(10) + "(rated by an LLM)", llm, ["INTEGRITY", "EXPLAINABILITY"]),
    ("Integrity, Explainability" + chr(10) + "(rule-based backup)", heur, ["INTEGRITY", "EXPLAINABILITY"]),
]
dcol = {"FAIRNESS": "#0072B2", "ROBUSTNESS": "#E69F00", "SAFETY": "#D55E00",
        "INTEGRITY": "#009E73", "EXPLAINABILITY": "#CC79A7"}
fig, axs = plt.subplots(1, 3, figsize=(6.8, 3.1), sharey=True,
                        gridspec_kw={"width_ratios": [1.5 * len(scored), 1.9 * len(llm), 1.5 * len(heur)]})
for ax, (title, names, dims) in zip(axs, panels):
    w = 0.8 / len(dims)
    for i, n in enumerate(names):
        for j, d in enumerate(dims):
            ax.bar(i + (j - (len(dims) - 1) / 2) * w, P[n]["dimension_scores_as_reported"][d], w, color=dcol[d])
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([short[n] for n in names], fontsize=6.5)
    ax.set_title(title, fontsize=7.5)
    ax.set_ylim(0, 10)
axs[0].set_ylabel("dimension score as reported (0-10)", fontsize=8)
fig.legend(handles=[Patch(color=c, label=d.title()) for d, c in dcol.items()], loc="lower center", ncol=5,
           fontsize=7, frameon=False, bbox_to_anchor=(0.5, 0.045))
fig.text(0.5, 0.01, "FRIES withheld, not shown: " + ", ".join(short[n] for n in withheld)
         + ". Panels are not comparable with each other.", ha="center", fontsize=7, color=GREY)
fig.tight_layout(rect=(0, 0.1, 1, 1))
fig.savefig(os.path.join(OUT, "fig_hub_profiles.pdf"))
plt.close(fig)
# ---------------------------------------------------------------- 5. evidence, risk decision and score on the same axis
# Evidence is scaled to its own maximum so that three different statistics fit one axis; the score is the
# range-scaled (v4) dimension score divided by 10; the strip under each panel shows the risk decision.
af = json.load(open(os.path.join(R, "fairness_confirm_20261003", "analysis", "analysis.json")))["models"]
fx = ["clean_control", "fairness_r020", "fairness_r040", "fairness_r070", "fairness_r100"]
f_ev = [af[m]["equal_opportunity_difference"] for m in fx]
f_dec = ["w", "w", "r", "r", "r"]                      # w = withheld, r = risk raised
f_sc = [None, None] + [pi(*t) for t in [(6, 6, 8), (4, 4, 8), (1, 1, 8)]]
r_ev = [r["accuracy_drop"] for r in a1["robustness"]]
r_dec = ["n"] * 4                                        # n = no risk
r_sc = [pi(*t) for t in [(9, 9, 8), (6, 6, 8), (3, 3, 8), (1, 1, 8)]]
s_rows = sorted([r for r in a0["safety"] if r.get("role") != "control"], key=lambda r: r["injected_rate"])
s_ev = [r["severe_fnr"] for r in s_rows]
s_dec = ["n", "n", "n", "r", "r"]                        # evidence-level rule of Section 6.6
s_sc = [pi(*t) for t in [(8, 8, 8), (6, 6, 8), (5, 5, 8), (2, 2, 8), (1, 1, 8)]]
fam2 = [("Fairness (flip rate)", ["0", "0.2", "0.4", "0.7", "1.0"], f_ev, f_sc, f_dec, "TPR gap"),
        ("Robustness (swaps)", ["1", "3", "5", "8"], r_ev, r_sc, r_dec, "accuracy drop"),
        ("Safety (relabel rate)", ["0", "0.25", "0.5", "0.75", "1.0"], s_ev, s_sc, s_dec, "severe FNR")]
fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.9), sharey=True)
for ax, (name, xl, ev_, sc, dec, evname) in zip(axs, fam2):
    x = np.arange(len(xl))
    ax.plot(x, np.array(ev_) / max(ev_), color=BLUE, marker="o", ms=4, lw=1.3, label="evidence, scaled to its maximum")
    ax.plot(x, [np.nan if v is None else v / 10 for v in sc], color=ORANGE, marker="s", ms=4, lw=1.3,
            label="range-scaled score / 10")
    for xi, d in zip(x, dec):
        if d == "r":
            ax.scatter(xi, 1.07, marker="s", s=28, color=INK, clip_on=False)
        elif d == "n":
            ax.scatter(xi, 1.07, marker="s", s=28, facecolor="white", edgecolor=INK, clip_on=False)
        else:
            ax.scatter(xi, 1.07, marker="x", s=24, color=GREY, clip_on=False)
    ax.set_xticks(x)
    ax.set_xticklabels(xl, fontsize=7)
    ax.set_title(name, fontsize=8)
    ax.set_ylim(0, 1.13)
axs[0].set_ylabel("scaled value")
axs[0].legend(fontsize=6, frameon=False, loc="lower left")
fig.text(0.5, 0.005, "markers at the top of each panel: filled square = risk raised, open square = no risk raised, cross = rating withheld",
         ha="center", fontsize=6.5, color=GREY)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(os.path.join(OUT, "fig_layers.pdf"))
plt.close(fig)

# ---------------------------------------------------------------- 6. fairness intervals of the seven Hub models
order7 = list(short.keys())
fig, ax = plt.subplots(figsize=(6.4, 2.9))
for i, n in enumerate(order7):
    d = P[n]["dimensions"]["FAIRNESS"]
    c = d["eopp_ci"]
    w = c["ci_upper"] - c["ci_lower"]
    col = GREY if d["fairness_finding"] == "INSUFFICIENT_EVIDENCE" else (ORANGE if d["fairness_finding"] == "FAIRNESS_RISK" else BLUE)
    ax.plot([c["ci_lower"], c["ci_upper"]], [i, i], color=col, lw=2.2)
    ax.scatter(c["point"], i, color=col, s=26, zorder=3)
    ax.text(c["ci_upper"] + 0.006, i, "w=%.3f" % w, va="center", fontsize=7)
ax.axvline(0.02, color=INK, ls="--", lw=0.8)
ax.text(0.024, -0.55, "eps = 0.02", fontsize=7)
ax.set_yticks(range(len(order7)))
ax.set_yticklabels([short[n] for n in order7], fontsize=8)
ax.invert_yaxis()
ax.set_xlabel("equal-opportunity difference (TPR gap), bootstrap 95% CI")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_hub_eod.pdf"))
plt.close(fig)
print("figures written")

# ---------------------------------------------------------------- 7. severe miss rate against benign false-positive rate (Hub audit)
# Both values are read from the stored probe output of each audit; the plot shows a trade-off that the
# consolidated table hides when the two columns are read separately.
pts = []
for n in short:
    d = json.load(open(os.path.join(R, "external_hub_validation_20261003_v9r", "evaluations", n.replace("/", "__") + ".json")))
    s = {p["dimension"]: p for p in d["probes"]}["SAFETY"]["metric_values"]["behavior"]
    pts.append((short[n], s["benign_fpr"], s["severe_fnr"]))
fig, ax = plt.subplots(figsize=(5.2, 3.2))
for name, x, y in pts:
    ax.scatter(x, y, color=ORANGE if x > 0.30 else BLUE, s=34, zorder=3)
    ax.annotate(name, (x, y), textcoords="offset points", xytext=(5, 3), fontsize=7)
ax.axvline(0.30, color=INK, ls="--", lw=0.8)
ax.text(0.305, 0.74, "benign FPR\nceiling 0.30", fontsize=7)
ax.set_xlabel("benign false-positive rate (share of non-toxic comments flagged)")
ax.set_ylabel("severe false-negative rate")
ax.set_xlim(-0.02, 0.45)
ax.set_ylim(0, 0.95)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_hub_tradeoff.pdf"))
plt.close(fig)
print("tradeoff figure written")
