"""Regenerate every data figure of the report from the frozen evaluation JSON files.
Run from the report/ directory:  python make_figures.py
"""
import json, glob, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SUITE = os.path.join("..", "results", "flawed_model_suite")
OUT = "figures"
DIMS = ["FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY"]
SHORT = {"FAIRNESS": "Fairness", "ROBUSTNESS": "Robustness", "INTEGRITY": "Integrity",
         "EXPLAINABILITY": "Explainability", "SAFETY": "Safety"}
ORDER = ["genuine", "variant1_fairness", "variant2_robustness", "variant3_explainability",
         "variant4_integrity", "variant5_safety", "variant6_compound"]
ORDER2 = ["ref2"] + ORDER
LABEL = {"ref2": "Reference\n(corrected)", "genuine": "Genuine\n(toxic-bert)", "variant1_fairness": "V1\nfairness",
         "variant2_robustness": "V2\nrobustness", "variant3_explainability": "V3\nexplain.",
         "variant4_integrity": "V4\nintegrity", "variant5_safety": "V5\nsafety",
         "variant6_compound": "V6\ncompound"}
BLUE, ORANGE, GREY, INK = "#0072B2", "#D55E00", "#8a8f98", "#222222"

plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.edgecolor": "#999999",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 10, "figure.dpi": 150})

def load(run):
    d = {}
    for f in glob.glob(os.path.join(SUITE, run, "*.json")):
        n = os.path.basename(f)[:-5]
        if n.startswith("_"):
            continue
        # Run 1 holds two V2 files; only the redesigned checkpoint matches the weights used in Run 2.
        if n == "variant2_robustness" and run == "eval_results":
            continue
        n = n.replace("_redesigned", "")
        n = "genuine" if n.startswith("trustworthy") else n
        n = "ref2" if n.startswith("reference_toxicbert") else n
        d[n] = json.load(open(f, encoding="utf-8"))
    return d

def probe(j, dim):
    return next(p for p in j["probes"] if p["dimension"] == dim)["metric_values"]

v1, v2 = load("eval_results"), load("eval_results_v2")
v3 = load("eval_results_v3")
v2["ref2"] = v3["ref2"]  # corrected reference (Run 3) shown beside the Run 2 variants
col = lambda m: BLUE if m in ("genuine", "ref2") else ORANGE
xs = np.arange(len(ORDER))

# 1 overall FRIES, both runs --------------------------------------------------
fig, ax = plt.subplots(figsize=(6.6, 3.0))
for i, m in enumerate(ORDER):
    a, b = v1[m]["final_score"]["fries_score"], v2[m]["final_score"]["fries_score"]
    ax.plot([i, i], [a, b], color=GREY, lw=1.2, zorder=1)
    ax.scatter(i, a, s=34, marker="o", color=col(m), zorder=3, label="Run 1" if i == 0 else None)
    ax.scatter(i, b, s=34, marker="s", color=col(m), zorder=3, edgecolor="white", linewidth=.8,
               label="Run 2" if i == 0 else None)
    ax.text(i + .13, a, f"{a:.2f}", va="center", fontsize=7, color=INK)
    ax.text(i + .13, b, f"{b:.2f}", va="center", fontsize=7, color=INK)
ref3 = v3["ref2"]["final_score"]["fries_score"]
ax.scatter(0.0, ref3, s=46, marker="D", color=BLUE, zorder=4, edgecolor="white", linewidth=.8)
ax.text(-.13, ref3, f"{ref3:.2f}", va="center", ha="right", fontsize=7, color=INK)
ax.set_xticks(xs, [LABEL[m] for m in ORDER], fontsize=7.5)
ax.set_ylim(3, 7.6); ax.set_xlim(-.6, len(ORDER) - .2)
ax.set_ylabel("Overall FRIES score (0--10)")
ax.yaxis.grid(True, color="#e5e5e5"); ax.set_axisbelow(True)
h = [plt.Line2D([], [], marker="o", ls="", color=INK, label="Run 1 (circle)"),
     plt.Line2D([], [], marker="s", ls="", color=INK, label="Run 2 (square)"),
     plt.Line2D([], [], marker="D", ls="", color=BLUE, label="reference, corrected (Run 3)"),
     plt.Line2D([], [], marker="o", ls="", color=BLUE, label="reference"),
     plt.Line2D([], [], marker="o", ls="", color=ORANGE, label="forged")]
ax.legend(handles=h, ncol=5, fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(.5, 1.13))
fig.tight_layout(); fig.savefig(f"{OUT}/fig_overall.pdf"); plt.close(fig)

# 2 heatmap of dimension scores (run 2) --------------------------------------
M = np.array([[v2[m]["final_score"]["dimension_scores"][d] for d in DIMS] for m in ORDER2])
fig, ax = plt.subplots(figsize=(5.6, 3.4))
im = ax.imshow(M, cmap="Blues", vmin=0, vmax=10, aspect="auto")
ax.set_xticks(range(5), [SHORT[d] for d in DIMS], fontsize=8)
ax.set_yticks(range(len(ORDER2)), [LABEL[m].replace("\n", " ") for m in ORDER2], fontsize=8)
for i in range(M.shape[0]):
    for j in range(5):
        ax.text(j, i, f"{M[i,j]:.2f}", ha="center", va="center", fontsize=7.5,
                color="white" if M[i, j] > 6 else INK)
for s in ax.spines.values(): s.set_visible(False)
ax.tick_params(length=0)
fig.colorbar(im, fraction=.035, pad=.02).set_label("dimension score", fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_heatmap.pdf"); plt.close(fig)

# 3 radar -------------------------------------------------------------------
fig = plt.figure(figsize=(4.4, 3.8)); ax = fig.add_subplot(111, polar=True)
ang = np.linspace(0, 2 * np.pi, 5, endpoint=False).tolist(); ang += ang[:1]
for m, c, ls in [("ref2", BLUE, "-"), ("variant3_explainability", ORANGE, "-"),
                 ("variant6_compound", "#009E73", "--")]:
    v = [v2[m]["final_score"]["dimension_scores"][d] for d in DIMS]; v += v[:1]
    ax.plot(ang, v, color=c, lw=1.8, ls=ls, label=LABEL[m].replace("\n", " "))
    ax.fill(ang, v, color=c, alpha=.07)
ax.set_xticks(ang[:-1], [SHORT[d] for d in DIMS], fontsize=8)
ax.set_ylim(0, 10); ax.set_yticks([2, 4, 6, 8, 10]); ax.tick_params(axis="y", labelsize=6)
ax.legend(loc="upper center", bbox_to_anchor=(.5, -.06), ncol=3, fontsize=7, frameon=False)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_radar.pdf"); plt.close(fig)

# 4 measured probe evidence -------------------------------------------------
fig, axs = plt.subplots(1, 3, figsize=(7.0, 2.6))
dpd = [probe(v2[m], "FAIRNESS")["demographic_parity_difference"] for m in ORDER2]
lo = [probe(v2[m], "FAIRNESS")["dp_ci"]["ci_lower"] for m in ORDER2]
hi = [probe(v2[m], "FAIRNESS")["dp_ci"]["ci_upper"] for m in ORDER2]
drop = [probe(v2[m], "ROBUSTNESS")["accuracy_drop"] * 100 for m in ORDER2]
clean = [probe(v2[m], "ROBUSTNESS")["clean_accuracy"] * 100 for m in ORDER2]
tick = ["R*", "G", "V1", "V2", "V3", "V4", "V5", "V6"]
cs = [col(m) for m in ORDER2]
xp = np.arange(len(ORDER2))
axs[0].bar(xp, dpd, color=cs, width=.6, yerr=[np.array(dpd) - lo, np.array(hi) - np.array(dpd)],
           error_kw={"lw": .8, "capsize": 2})
axs[0].set_title("Demographic parity diff.")
axs[1].bar(xp, drop, color=cs, width=.6); axs[1].set_title("Accuracy drop, char-swap (pp)")
axs[2].bar(xp, clean, color=cs, width=.6); axs[2].set_title("Clean accuracy (%)")
axs[2].axhline(80, color=GREY, lw=.8, ls=":"); axs[2].text(7.4, 80.8, "always-negative = 80%", fontsize=6, ha="right")
axs[2].set_ylim(60, 95)
for a in axs:
    a.set_xticks(xp, tick, fontsize=7.5); a.yaxis.grid(True, color="#e5e5e5"); a.set_axisbelow(True)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_probes.pdf"); plt.close(fig)

# 5 run-to-run variation per dimension --------------------------------------
fig, axs = plt.subplots(1, 3, figsize=(7.0, 2.4), sharey=True)
for ax, d in zip(axs, ["INTEGRITY", "EXPLAINABILITY", "SAFETY"]):
    for i, m in enumerate(ORDER):
        a, b = v1[m]["final_score"]["dimension_scores"][d], v2[m]["final_score"]["dimension_scores"][d]
        ax.plot([i, i], [a, b], color=GREY, lw=1); ax.scatter(i, a, s=22, color=col(m), zorder=3)
        ax.scatter(i, b, s=22, marker="s", color=col(m), zorder=3, edgecolor="white", linewidth=.6)
    ax.set_title(SHORT[d]); ax.set_xticks(xs, tick[1:], fontsize=7.5)
    ax.yaxis.grid(True, color="#e5e5e5"); ax.set_axisbelow(True); ax.set_ylim(0, 10)
axs[0].set_ylabel("dimension score")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_variance.pdf"); plt.close(fig)

# numbers used in the text, dumped for cross-checking -------------------------
with open(f"{OUT}/numbers.txt", "w") as f:
    for m in ORDER:
        f.write(f"{m}: run1={v1[m]['final_score']['fries_score']} run2={v2[m]['final_score']['fries_score']}\n")
print("ok")
