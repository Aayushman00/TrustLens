"""Appendix tables and prompt listings for the report, generated from stored results and source.

Run from the report/ directory:  python make_tables.py
Reads ../results/external_hub_validation_20261003_v9r and the two LLM prompt templates in ../backend/app;
writes chapters/tables_generated.tex and prompts/*.txt. Every number is copied from the stored evaluation
files; nothing is recomputed except interval widths.
"""
import ast
import json
import os
import textwrap

R = os.path.join("..", "results", "external_hub_validation_20261003_v9r")
BS = "\\"
ROW = " \\\\"
SHORT = {
    "unitary/toxic-bert": "toxic-bert",
    "unitary/unbiased-toxic-roberta": "unbiased",
    "s-nlp/roberta_toxicity_classifier": "s-nlp",
    "martin-ha/toxic-comment-model": "martin-ha",
    "textdetox/xlmr-large-toxicity-classifier": "textdetox",
    "facebook/roberta-hate-speech-dynabench-r4-target": "facebook",
    "gravitee-io/bert-tiny-toxicity": "gravitee",
}
P = json.load(open(os.path.join(R, "profiles.json")))["profiles"]


def ev(repo):
    f = os.path.join(R, "evaluations", repo.replace("/", "__") + ".json")
    d = json.load(open(f))
    return {p["dimension"]: p for p in d["probes"]}


def code(name):
    return "\\code{" + name.replace("_", "\\_") + "}"


def f3(x):
    return "--" if x is None else f"{x:.3f}"


def ci(lo, hi):
    return f"[{lo:.3f}, {hi:.3f}]"


def drop_ci(unc):
    c = unc.get("accuracy_drop_ci") or unc.get("drop_ci") or {}
    if not c:
        for v in unc.values():
            if isinstance(v, dict) and "ci_lower" in v:
                return v
    return c


out = []

# ---- A.2 per-model evidence: behaviour and fairness gap in one table
out.append("\\begin{table}[!htbp]\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}")
out.append("\\caption{External audit, measured evidence per model (3\\,000 evaluation rows, 282 severe positives; all intervals 95\\%). "
           "Drop is clean minus perturbed accuracy; Sev.\\ FNR is the share of severe toxic comments missed (Wilson interval); "
           "EOD is the gap in true-positive rates (bootstrap interval); its width is in Table~\\ref{tab:appfair}.}\\label{tab:appbehav}")
out.append("\\begin{tabularx}{\\textwidth}{@{}>{\\raggedright\\arraybackslash}Xrlllr@{}}\\toprule")
out.append("Model & Clean acc. & Drop [CI] & Sev.\\ FNR [CI] & EOD [CI] & Benign FPR" + ROW + "\\midrule")
for repo, short in SHORT.items():
    e = ev(repo)
    r = e["ROBUSTNESS"]["metric_values"]
    s_ = e["SAFETY"]["metric_values"]["behavior"]
    m = e["FAIRNESS"]["metric_values"]
    c = m["eopp_ci"]
    d = drop_ci(r.get("uncertainty", {}))
    out.append(" & ".join([
        code(short), f3(r["clean_accuracy"]), f3(r["accuracy_drop"]) + " " + ci(d["ci_lower"], d["ci_upper"]),
        f3(s_["severe_fnr"]) + " " + ci(*s_["severe_fnr_ci"]),
        f3(m["equal_opportunity_difference"]) + " " + ci(c["ci_lower"], c["ci_upper"]), f3(s_["benign_fpr"])]) + ROW)
out.append("\\bottomrule\\end{tabularx}\\end{table}")

# ---- A.3 per-group rates
out.append("")
out.append("\\begin{table}[!htbp]\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}")
out.append("\\caption{External audit, group-level rates. Group 0 has 2\\,461 rows and group 1 (annotator-reported identity-attack signal "
           "above zero) 539 rows; the label-rate gap is 0.505 for every model because the data are the same.}\\label{tab:appfair}")
out.append("\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{3.3cm}rrrrrrl@{}}\\toprule")
out.append("Model & TPR$_0$ & TPR$_1$ & FPR$_0$ & FPR$_1$ & FPR gap & EOD CI width & Fairness outcome" + ROW + "\\midrule")
outcome = {"FAIRNESS_RISK": "risk", "DISPARITY_OBSERVED": "disparity", "NO_MATERIAL_DISPARITY": "none",
           "INSUFFICIENT_EVIDENCE": "withheld"}
for repo, short in SHORT.items():
    m = ev(repo)["FAIRNESS"]["metric_values"]
    g = m["groups"]
    out.append(" & ".join([code(short), f3(g["0"]["tpr"]), f3(g["1"]["tpr"]), f3(g["0"]["fpr"]), f3(g["1"]["fpr"]),
                           f3(m["fpr_gap"]), f3(m["eopp_ci"]["ci_upper"] - m["eopp_ci"]["ci_lower"]), outcome[m["fairness_finding"]]]) + ROW)
out.append("\\bottomrule\\end{tabular}\\end{table}")

# ---- A.4 ratings and their sources
out.append("")
out.append("\\begin{table}[!htbp]\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}")
out.append("\\caption{External audit, proposed O/S/D ratings as stored (a dash: withheld). Integrity and Explainability ratings came from "
           "an LLM or from the rule-based fallback, so rows are not comparable and the table does not rank models.}\\label{tab:appratings}")
out.append("\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{3.3cm}llllll@{}}\\toprule")
out.append("Model & Fairness & Robustness & Safety & Integrity & Explainability & Source (I, E)" + ROW + "\\midrule")
for repo, short in SHORT.items():
    p = P[repo]["dimensions"]

    def osd(d):
        o = p[d]["osd"]
        return "--" if o["O"] is None else f"{o['O']}/{o['S']}/{o['D']}"
    src = p["INTEGRITY"]["osd_source"]
    src = {"llm_v1": "LLM", "heuristic_fallback": "fallback"}.get(src, str(src))
    out.append(" & ".join([code(short), osd("FAIRNESS"), osd("ROBUSTNESS"), osd("SAFETY"), osd("INTEGRITY"),
                           osd("EXPLAINABILITY"), src]) + ROW)
out.append("\\bottomrule\\end{tabular}\\end{table}")

with open(os.path.join("chapters", "tables_generated.tex"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(out) + "\n")
print("tables written")


# ---- verbatim prompt templates for Appendix B (read from the source by AST, so they cannot drift)
def template(path, name):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def ascii_clean(t):
    t = t.replace("{{", "{").replace("}}", "}")
    for a, b in (("—", "--"), ("–", "-"), ("’", "'"), ("“", '"'), ("”", '"'), ("≤", "<=")):
        t = t.replace(a, b)
    return t


BACK = os.path.join("..", "backend", "app")
os.makedirs("prompts", exist_ok=True)
for out_name, path, var in (("osd_rating_prompt.txt", os.path.join(BACK, "osd", "llm_client.py"), "_PROMPT_TEMPLATE"),
                            ("evidence_review_prompt.txt", os.path.join(BACK, "scripts", "run_l10_validation.py"), "_PROMPT")):
    text = ascii_clean(template(path, var))
    lines = []
    for ln in text.split("\n"):
        lines += textwrap.wrap(ln, 92, subsequent_indent="  ", break_long_words=False) or [""]
    with open(os.path.join("prompts", out_name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
print("prompts written")
