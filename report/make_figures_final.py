"""Figures for the final report chapters (L1-L6 and external Hub audit).

Run from the report/ directory:  python make_figures_final.py
Reads frozen result files under ../results; the L1 held-out O/S/D triples are copied from
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

# ---------------------------------------------------------------- 2. v3 vs v4 score on held-out sweeps
# (O,S,D) per level, copied from results/osd_calibration_20261003/FINDINGS.md; None = abstained
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
    for tr, col, mk, nm in ((v3, GREY, "o", "v3 bands"), (v4, ORANGE, "s", "v4 calibrated")):
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
axs[0].set_title("Robustness sweep", fontsize=9)
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
P = json.load(open(os.path.join(R, "external_hub_validation_20261003_v9r", "profiles.json")))["profiles"]
dims = ["FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY"]
short = {"unitary/toxic-bert": "toxic-bert", "unitary/unbiased-toxic-roberta": "unbiased-\ntoxic-roberta",
         "s-nlp/roberta_toxicity_classifier": "s-nlp\nroberta", "martin-ha/toxic-comment-model": "martin-ha\ntoxic-comment",
         "textdetox/xlmr-large-toxicity-classifier": "textdetox\nxlmr-large",
         "facebook/roberta-hate-speech-dynabench-r4-target": "facebook\ndynabench-r4",
         "gravitee-io/bert-tiny-toxicity": "gravitee\nbert-tiny"}
names = list(P)
fig, ax = plt.subplots(figsize=(7.0, 3.1))
w = 0.15
cols = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00"]
for i, n in enumerate(names):
    sc = P[n]["dimension_scores_as_reported"]
    if sc is None:
        ax.text(i, 0.35, "FRIES\nwithheld", ha="center", fontsize=6.5, color=GREY)
        continue
    for j, d in enumerate(dims):
        ax.bar(i + (j - 2) * w, sc[d], w, color=cols[j], label=d.title() if i == 1 else None)
ax.set_xticks(range(len(names)))
ax.set_xticklabels([short[n] for n in names], fontsize=7)
ax.set_ylim(0, 10)
ax.set_ylabel("dimension score (0-10)")
ax.legend(fontsize=6.5, ncol=5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.13))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_hub_profiles.pdf"))
plt.close(fig)
print("figures written")
