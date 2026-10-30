"""Analyse the L10 Google-Form human responses against the frozen TrustLens reference.

stdlib only.  Run from repo root:  python results/l10_human_form/analyze_human_responses.py
Reads : "L10 Evidence Review - responses - Form Responses 1.csv" (raw export, never modified)
        results/l10_independent_validation_20261003_v9/trustlens_reference.json (frozen)
        results/l10_human_form/packet_form_mapping.json (P01..P12 -> L10-01..L10-12)
Writes: results/l10_human_analysis_20261005/  (per_response.csv, packet_summary.csv, agreement.json, REPORT.md)

Reviewers are evidence reviewers, not ground truth. Nothing here validates TrustLens statistically.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import statistics
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "L10 Evidence Review - responses - Form Responses 1.csv"
REF = ROOT / "results/l10_independent_validation_20261003_v9/trustlens_reference.json"
MAP = ROOT / "results/l10_human_form/packet_form_mapping.json"
OUT = ROOT / "results/l10_human_analysis_20261005"
QS = ["Q1", "Q2", "Q3", "Q4"]
QNAME = {"Q1": "Evidence sufficient", "Q2": "Risk present", "Q3": "FRIES dimension", "Q4": "Severity (1-9)"}


# ---------------------------------------------------------------- parse
def load():
    rows = list(csv.reader(RAW.open(encoding="utf-8")))[1:]
    seen, resp = Counter(), []
    for row in rows:
        code = row[1]
        seen[code] += 1
        rid = code if code != "R0" else f"R0-{seen[code]}"  # R0 = shared code, numbered by submission time
        for p in range(12):
            q1, q2, q3, q4, why = (c.strip() for c in row[2 + p * 5: 7 + p * 5])
            m = re.match(r"\d", q4)
            resp.append(dict(rid=rid, code=code, ts=row[0], pid=f"P{p+1:02d}", Q1=q1.upper(), Q2=q2.upper(),
                             Q3=q3.upper(), Q4=int(q4[0]) if m else None, q4_raw=q4, why=why))
    return resp


def sev_reported(r):  # severity counts as a judgment only when the reviewer also said a risk exists
    return r["Q4"] if r["Q2"] == "YES" else None


# ---------------------------------------------------------------- stats
def majority(vals):
    c = Counter(vals).most_common()
    top = [k for k, n in c if n == c[0][1]]
    return (top[0] if len(top) == 1 else "TIE(" + "/".join(sorted(top)) + ")"), c[0][1], len(vals)


def pair_agree(vals):
    pr = list(combinations(vals, 2))
    return sum(a == b for a, b in pr) / len(pr)


def fleiss(items):  # items: list of equal-length label lists
    k = len(items[0])
    cats = sorted({c for it in items for c in it})
    p_i = [(sum(n * n for n in Counter(it).values()) - k) / (k * (k - 1)) for it in items]
    p_j = [sum(it.count(c) for it in items) / (len(items) * k) for c in cats]
    pe = sum(p * p for p in p_j)
    return None if pe == 1 else (statistics.fmean(p_i) - pe) / (1 - pe)


def kripp_interval(units):  # units: list of lists of numbers (missing already dropped)
    units = [u for u in units if len(u) >= 2]
    n = sum(len(u) for u in units)
    if n < 2:
        return None
    do = sum(sum((a - b) ** 2 for a, b in combinations(u, 2)) * 2 / (len(u) - 1) for u in units) / n
    allv = [v for u in units for v in u]
    de = sum((a - b) ** 2 for a, b in combinations(allv, 2)) * 2 / (n * (n - 1))
    return None if de == 0 else 1 - do / de


def boot_ci(per_packet, reps=5000, seed=0):
    rnd = random.Random(seed)
    ms = sorted(statistics.fmean(rnd.choices(per_packet, k=len(per_packet))) for _ in range(reps))
    return ms[int(.025 * reps)], ms[int(.975 * reps) - 1]


def agreement(resp, raters):
    by = {}
    for r in resp:
        if r["rid"] in raters:
            by.setdefault(r["pid"], []).append(r)
    out = {}
    for q in ("Q1", "Q2", "Q3"):
        per = [pair_agree([r[q] for r in by[p]]) for p in sorted(by)]
        lo, hi = boot_ci(per)
        out[q] = dict(mean_pairwise=statistics.fmean(per), ci95=(lo, hi), fleiss=fleiss([[r[q] for r in by[p]] for p in sorted(by)]),
                      unanimous=sum(len(set(r[q] for r in by[p])) == 1 for p in by), per_packet=dict(zip(sorted(by), per)))
    units = [[v for r in by[p] if (v := sev_reported(r)) is not None] for p in sorted(by)]
    pairs = [abs(a - b) for u in units for a, b in combinations(u, 2)]
    out["Q4"] = dict(alpha=kripp_interval(units), n_pairs=len(pairs), exact=sum(d == 0 for d in pairs) / len(pairs),
                     within1=sum(d <= 1 for d in pairs) / len(pairs), within2=sum(d <= 2 for d in pairs) / len(pairs),
                     per_packet_range={p: (min(u), max(u)) if u else None for p, u in zip(sorted(by), units)})
    return out


def consistency(r):  # internal contradictions in one answer set
    f = []
    if r["Q2"] == "YES" and r["Q4"] is None:
        f.append("YES-risk but severity N/A")
    if r["Q2"] != "YES" and r["Q4"] is not None:
        f.append(f"{r['Q2']}-risk but severity {r['Q4']}")
    return f


# ---------------------------------------------------------------- main analysis
def main():
    resp = load()
    ref = json.load(REF.open())
    pm = json.load(MAP.open())["packets"]
    rids = sorted({r["rid"] for r in resp}, key=lambda s: (s != "R2", s))
    r0 = [x for x in rids if x.startswith("R0")]
    OUT.mkdir(exist_ok=True)

    # per-response csv
    with (OUT / "per_response.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reviewer", "submitted", "packet", "Q1_sufficient", "Q2_risk", "Q3_dimension", "Q4_severity", "Q4_raw", "inconsistency", "rationale"])
        for r in resp:
            w.writerow([r["rid"], r["ts"], r["pid"], r["Q1"], r["Q2"], r["Q3"], r["Q4"], r["q4_raw"], "; ".join(consistency(r)), r["why"]])

    # per-packet majority + comparison
    def judge(rs, tl):
        m = {q: majority([r[q] for r in rs]) for q in ("Q1", "Q2", "Q3")}
        sv = [v for r in rs if (v := sev_reported(r)) is not None]
        med = statistics.median(sv) if len(sv) >= 3 else None
        tl_sev = tl["severity"] if tl["risk_present"] == "YES" else None
        fl = []
        if m["Q1"][0] != tl["evidence_sufficient"] or (m["Q2"][0] == "UNCERTAIN") != (tl["risk_present"] == "UNCERTAIN"):
            fl.append("insufficient_evidence")
        if {m["Q2"][0], tl["risk_present"]} == {"YES", "NO"}:
            fl.append("risk_no_risk")
        if m["Q2"][0] == tl["risk_present"] == "YES" and m["Q3"][0] != tl["dimension"]:
            fl.append("fries_classification")
        if m["Q2"][0] == tl["risk_present"] == "YES" and med is not None and abs(med - tl_sev) >= 2:
            fl.append("severity")
        return m, sv, med, tl_sev, fl

    summ = []
    for p in sorted(pm):
        L = pm[p]["frozen_packet"]
        tl = ref[L]
        rs = [r for r in resp if r["pid"] == p]
        m, sv, med, tl_sev, fl = judge(rs, tl)
        fl0 = judge([r for r in rs if r["code"] == "R0"], tl)[4]
        # leave-one-reviewer-out stability of the three categorical majorities
        unstable = [q for q in ("Q1", "Q2", "Q3")
                    if any(majority([r[q] for r in rs if r["rid"] != d])[0] != m[q][0] for d in rids)]
        summ.append(dict(pid=p, L=L, dim=pm[p]["dimension"], tl=tl, m=m, sv=sv, med=med, tl_sev=tl_sev, flags=fl, flags_r0=fl0, unstable=unstable))

    with (OUT / "packet_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["packet", "frozen_id", "packet_dimension", "TL_risk", "TL_sufficient", "TL_dimension", "TL_severity", "TL_aspect_scoring", "TL_gates",
                    "H_Q1", "H_Q1_n", "H_Q2", "H_Q2_n", "H_Q3", "H_Q3_n", "H_sev_median", "H_sev_values", "disagreement_flags", "disagreement_flags_R0_only", "unstable_under_leave_one_out"])
        for s in summ:
            t = s["tl"]
            w.writerow([s["pid"], s["L"], s["dim"], t["risk_present"], t["evidence_sufficient"], t["dimension"], s["tl_sev"], t["aspect_scoring"], "|".join(t["failed_gates"]),
                        s["m"]["Q1"][0], s["m"]["Q1"][1], s["m"]["Q2"][0], s["m"]["Q2"][1], s["m"]["Q3"][0], s["m"]["Q3"][1], s["med"], " ".join(map(str, sorted(s["sv"]))),
                        "|".join(s["flags"]), "|".join(s["flags_r0"]), "|".join(s["unstable"])])

    A, B = agreement(resp, rids), agreement(resp, r0)
    json.dump({"all7": A, "R0_only": B}, (OUT / "agreement.json").open("w"), indent=1, default=str)

    # reviewer QC
    qc = {}
    for rid in rids:
        rs = [r for r in resp if r["rid"] == rid]
        qc[rid] = dict(ts=rs[0]["ts"], med_len=statistics.median(len(r["why"]) for r in rs), short=sum(len(r["why"]) <= 10 for r in rs),
                       incons=sum(bool(consistency(r)) for r in rs),
                       dim_ok=sum(r["Q3"] == pm[r["pid"]]["dimension"] for r in rs))

    # rationale themes (R0 only, regex counts; verifiable against per_response.csv)
    R0rs = [r for r in resp if r["code"] == "R0"]
    themes = {
        "cites >=2 numbers from the packet": sum(len(re.findall(r"\d+(?:\.\d+)?", r["why"])) >= 2 for r in R0rs),
        "mentions confidence interval / CI": sum(bool(re.search(r"\bCI\b|confidence interval", r["why"])) for r in R0rs),
        "refers to another packet (P01..P12)": sum(bool(re.search(r"\bP\d\d\b", r["why"])) for r in R0rs),
        "separates data composition / base rate from bias": sum(bool(re.search(r"label-rate|actual toxic rates|data composition", r["why"])) for r in R0rs),
        "says automated keyword check misses content": sum(bool(re.search(r"keyword", r["why"])) for r in R0rs),
        "states cause is not established": sum(bool(re.search(r"not establish|cause is unknown|outdated manifest|alone does not", r["why"])) for r in R0rs),
        "rests only on the automated section check": sum(bool(re.match(r"The automated check found", r["why"])) for r in R0rs),
        "LaTeX-style math ($...$)": sum("$" in r["why"] for r in R0rs),
    }
    nonconsist = [(r["rid"], r["pid"], consistency(r)) for r in resp if consistency(r)]

    # ------------------------------------------------------------ report
    def pct(x): return f"{100 * x:.0f}%"
    def f2(x): return "n/a" if x is None else f"{x:.2f}"
    L = []
    w = L.append
    w("# L10 human evidence review - results\n")
    w(f"Source: `{RAW.name}` (sha256 `{hashlib.sha256(RAW.read_bytes()).hexdigest()[:16]}...`), "
      f"{len(rids)} submissions x 12 packets = {len(resp)} answer sets. Frozen packets and TrustLens reference: `results/l10_independent_validation_20261003_v9/` (untouched). "
      "Reviewers are evidence reviewers, not ground truth. This is descriptive; **no claim of statistical validation is made.**\n")
    w("## 1. Respondents and data quality\n")
    w("Six submissions carry the shared code `R0` (numbered R0-1..R0-6 by timestamp; they may be different people) and one carries `R2`. Both are analysed as given; a sensitivity set without R2 is reported alongside.\n")
    w("| reviewer | submitted | median rationale length (chars) | rationales <=10 chars | Q2/Q4 contradictions | Q3 = packet's dimension |")
    w("|---|---|---|---|---|---|")
    for rid, q in qc.items():
        w(f"| {rid} | {q['ts']} | {q['med_len']:.0f} | {q['short']}/12 | {q['incons']}/12 | {q['dim_ok']}/12 |")
    w(f"\n**R2 is low-quality after P01** and should be treated as unreliable: {qc['R2']['short']}/12 rationales are <=10 characters (e.g. `NA`, `yes`, `security`, `3`, `Good`, `good`); "
      "the P01, P02 and P04 rationales are the same pasted sentence (P02's is also truncated and does not match P02's numbers); "
      "P01 itself answers Q2 = NO while the rationale asserts \"a meaningful disparity\"; P05 pairs \"yes\" with severity 1 = catastrophic; P11 pairs \"good\" with severity 1 = catastrophic. "
      f"The six R0 submissions are internally coherent (contradictions: {sum(qc[x]['incons'] for x in r0)} of 72 answer sets, all severity entered while Q2 = NO/UNCERTAIN, because the form did not enforce N/A).\n")
    w(f"Severity is counted as a judgment only when the reviewer answered Q2 = YES ({sum(1 for r in resp if sev_reported(r) is not None)} of {len(resp)} answers); {len(nonconsist)} answers carry a severity or N/A inconsistent with Q2 and are ignored for Q4.\n")

    w("## 2. Human agreement per question\n")
    w("Observed agreement = share of reviewer pairs giving the same answer on a packet, averaged over 12 packets (95% percentile bootstrap over packets, 5000 resamples). "
      "Fleiss' kappa is over the 12 packets. Q4 uses Krippendorff's alpha (interval) on severities from reviewers who answered Q2 = YES, plus pairwise closeness. "
      "With 12 packets the intervals are wide and kappa is unstable (prevalence skew: most Q1 answers are YES).\n")
    w("| question | set | mean pairwise agreement (95% CI) | Fleiss kappa | packets with unanimous answer |")
    w("|---|---|---|---|---|")
    for q in ("Q1", "Q2", "Q3"):
        for name, S in (("all 7", A), ("R0 only (6)", B)):
            d = S[q]
            w(f"| {q} {QNAME[q]} | {name} | {pct(d['mean_pairwise'])} ({pct(d['ci95'][0])}-{pct(d['ci95'][1])}) | {f2(d['fleiss'])} | {d['unanimous']}/12 |")
    w("\n| Q4 severity | set | Krippendorff alpha | pairs exactly equal | pairs within 1 | pairs within 2 | n pairs |")
    w("|---|---|---|---|---|---|---|")
    for name, S in (("all 7", A), ("R0 only (6)", B)):
        d = S["Q4"]
        w(f"| Severity | {name} | {f2(d['alpha'])} | {pct(d['exact'])} | {pct(d['within1'])} | {pct(d['within2'])} | {d['n_pairs']} |")
    w("\nPer-packet agreement (all 7; modal share of the answer, severity range among Q2 = YES reviewers):\n")
    w("| packet | dim | Q1 | Q2 | Q3 | severity values (n) | range |")
    w("|---|---|---|---|---|---|---|")
    for s in summ:
        rg = A["Q4"]["per_packet_range"][s["pid"]]
        w(f"| {s['pid']} | {s['dim']} | {s['m']['Q1'][0]} {s['m']['Q1'][1]}/7 | {s['m']['Q2'][0]} {s['m']['Q2'][1]}/7 | {s['m']['Q3'][0]} {s['m']['Q3'][1]}/7 | "
          f"{' '.join(map(str, sorted(s['sv']))) or '-'} ({len(s['sv'])}) | {'-' if not rg else f'{rg[0]}-{rg[1]}'} |")

    w("\n## 3. Human majority vs TrustLens\n")
    w("Majority = plurality of the 7 answers (count shown; `*` = not a strict >50% majority). Severity = median of Q2 = YES reviewers; TrustLens severity = S, shown only where TrustLens reports a risk "
      "(for NO/abstain packets the reference S is an internal default, not a judgment). Q4 scale: 1 = catastrophic ... 9 = negligible.\n")
    w("| packet | dim | TrustLens (risk / sufficient / dim / S) | human majority Q2 | Q1 | Q3 | human S (median) | stable if any one reviewer dropped | disagreement |")
    w("|---|---|---|---|---|---|---|---|---|")
    for s in summ:
        t = s["tl"]
        def mj(q): return f"{s['m'][q][0]} {s['m'][q][1]}/7" + ("" if s["m"][q][1] > 3.5 else "*")
        w(f"| {s['pid']} | {s['dim']} | {t['risk_present']} / {t['evidence_sufficient']} / {t['dimension']} / {s['tl_sev'] if s['tl_sev'] is not None else '-'} | {mj('Q2')} | {mj('Q1')} | {mj('Q3')} | "
          f"{(str(s['med']) + ' (n=' + str(len(s['sv'])) + ')') if s['med'] is not None else '- (n=' + str(len(s['sv'])) + ')'} | {'yes' if not s['unstable'] else 'no: ' + ','.join(s['unstable'])} | {', '.join(s['flags']) or 'agree'} |")
    same_r0 = all(sorted(s["flags"]) == sorted(s["flags_r0"]) for s in summ)
    n_full = sum(not s["flags"] for s in summ)
    w(f"\nFull agreement on all four layers: {n_full}/12 packets ({', '.join(s['pid'] for s in summ if not s['flags'])}). "
      f"TrustLens risk call equals human majority risk call on {sum(s['m']['Q2'][0] == s['tl']['risk_present'] for s in summ)}/12 packets; "
      f"sufficiency on {sum(s['m']['Q1'][0] == s['tl']['evidence_sufficient'] for s in summ)}/12. "
      + ("Disagreement flags are identical when R2 is excluded (R0 only)." if same_r0 else "Flags differ when R2 is excluded: " + "; ".join(f"{x['pid']} {x['flags']} -> {x['flags_r0']}" for x in summ if sorted(x["flags"]) != sorted(x["flags_r0"])) + ".") + "\n")

    w("## 4. Where they disagree, by cause\n")
    w("Each flag is raised independently, so one packet may carry several. Rules: **insufficient_evidence** - majority Q1 differs from TrustLens sufficiency, or exactly one side abstains on risk "
      "(TrustLens abstentions come from evidence gates: `G-FAIR-CI-WIDE`, `G-INT-LISTING-UNVERIFIED`); **risk_no_risk** - YES vs NO; **fries_classification** - both YES, different dimension; "
      "**severity** - both YES and |human median - TrustLens S| >= 2 (the L10 protocol threshold).\n")
    w("| cause | packets | detail |")
    w("|---|---|---|")
    def cause(flag, fmt):
        ps = [s for s in summ if flag in s["flags"]]
        return ", ".join(s["pid"] for s in ps) or "none", "; ".join(fmt(s) for s in ps) or "-"
    c1 = cause("insufficient_evidence", lambda s: f"{s['pid']}: TL {s['tl']['risk_present']}/suff {s['tl']['evidence_sufficient']} ({'|'.join(s['tl']['failed_gates']) or 'no gate'}) vs humans risk {s['m']['Q2'][0]}, suff {s['m']['Q1'][0]}")
    c2 = cause("risk_no_risk", lambda s: f"{s['pid']}: TL {s['tl']['risk_present']} vs humans {s['m']['Q2'][0]} ({s['m']['Q2'][1]}/7)")
    c3 = cause("fries_classification", lambda s: f"{s['pid']}: TL {s['tl']['dimension']} vs humans {s['m']['Q3'][0]}")
    c4 = cause("severity", lambda s: f"{s['pid']}: TL S={s['tl_sev']} vs human median {s['med']}")
    for n, c in (("Insufficient evidence / abstention", c1), ("Risk vs no-risk", c2), ("FRIES classification", c3), ("Severity", c4)):
        w(f"| {n} | {c[0]} | {c[1]} |")
    w("\nObservations (descriptive):")
    w("- **Humans were more willing to call risk than TrustLens.** P06, P07, P10 (TrustLens: NO / disclosure gap) and P04 (NO) were judged risky by the human majority; P04's majority is weak (4/7 with 2 UNCERTAIN, 1 NO).")
    w("- **Humans did not abstain where TrustLens did.** P02 (CI-width gate) and P09 (listing-unverified gate) were judged sufficient by every reviewer who answered Q1 sensibly; TrustLens abstained. P08 had the same gate but TrustLens still reports a risk.")
    w("- **FRIES classification never disagreed** where both sides saw a risk (P01, P03, P08, P11); the only Q3 deviations from the packet's dimension are individual (see section 1), not majority.")
    w("- **Severity: TrustLens is harsher on integrity (P08), milder on fairness and explainability (P03, P11).** Human medians vs TrustLens S: P08 3 vs 1, P03 5 vs 7 (4.5 without R2), P11 3 vs 6. On P01 the human median (3.5) was within 1 of TrustLens (4).")
    w("- **P12 (real model card)** is the only explainability packet where the human majority is NO risk (5/7), agreeing with TrustLens; the two YES answers (R0-1: the card's own bias warning, FAIRNESS; R0-6: the automated section check) are individual readings. **P05** (all accuracy fields null) is the other full match: TrustLens and humans both abstain/insufficient.\n")

    w("## 5. Written rationales (qualitative evidence)\n")
    w("Rationales were read in full (84). They are **supporting qualitative evidence only**; counts below are keyword regexes over the 72 R0 rationales and can be rechecked in `per_response.csv`. R2's 12 rationales carry no usable content after P01 (section 1) and are excluded here.\n")
    w("| theme | R0 rationales (of 72) |")
    w("|---|---|")
    for k, v in themes.items():
        w(f"| {k} | {v} |")
    w("""
Findings:

1. **Fairness (P01-P03).** Reviewers anchored on the FPR/TPR gap and its CI. Two (R0-3, R0-5) explicitly separated the 52-point label-rate gap (data composition) from model bias, and R0-3 framed P03 as uneven *missed detection* (TPR gap) rather than over-flagging. R0-6 reported group rates without any CI reasoning. The packets where TrustLens abstained (P02) were read as clear evidence of a smaller-but-real disparity (CI excludes 0).
2. **Robustness (P04, P05).** P04's 3.0-point drop was read two ways: "measurable sensitivity" (moderate severity 5-6) vs "small, well-measured, no risk" (R0-3, severity 8). On P05 every R0 reviewer noted that all accuracy fields were null; they split between "uncertain" (answer Q2 = UNCERTAIN, 4) and "no risk" (2) - i.e. insufficiency was consistently recognised, but some converted it into a no-risk answer. R0-6 misreported coverage as 100% (packet: 99.97%).
3. **Safety (P06, P07).** Reasoning cited severe FNR against the reference classifier. P07 (30% severe FNR, better than reference) split on whether better-than-baseline means "no risk": one reviewer said no risk (severity 7), the rest said meaningful risk (S 3-4). The packet design offers no absolute acceptable level, so this is a genuine judgment-threshold difference, not a reading error.
4. **Integrity (P08, P09).** Unanimous reading of MISMATCH / VERIFIED. One reviewer deliberately scored S 2 rather than 1 because the cause is unknown (could be a stale manifest); another noted the evidence does not show malice. TrustLens scored S = 1 (catastrophic); the human 2-3 reflects this hedging about cause.
5. **Explainability (P10-P12).** Reviewers correctly saw through the 60% keyword coverage figure (P10: headings present, content "[More Information Needed]"; P12: coverage flags are keyword misses). R0-6 relied on the automated section check alone in all three (it said P12 is risky), which contributes to the P12 split. On P11 one reviewer classed the overclaiming card as SAFETY rather than EXPLAINABILITY.
6. **Rationale-vs-answer mismatches.** R0-3 (3 answers) and R0-6 (4 answers) entered a severity while answering Q2 = NO/UNCERTAIN (e.g. R0-3 P07: NO with severity 7). The form did not enforce N/A, so these are form-design noise, handled by section 1's rule.
""")

    w("## 6. Limitations (state these in the report)\n")
    w(f"""- **Sample size.** 7 submissions only, and the 12 packets are author-chosen (clear defects, controls, borderline cases) - not a random sample of models or evidence. Bootstrap intervals over 12 packets are wide; kappa is unstable under prevalence skew (Q1 is {sum(r['Q1']=='YES' for r in resp)}/{len(resp)} YES). Do not read any percentage as a population estimate.
- **Convenience sample.** Reviewers are a convenience sample, not screened for FRIES/ML-fairness expertise; no demographic or competence data were collected. They are reviewers of evidence, not ground truth.
- **R0 is not one person.** Six submissions share the code `R0` and cannot be separated into individuals: they may be several people, or one person submitting repeatedly. "7 reviewers" is therefore an upper bound on independence; agreement among R0 rows is not independent agreement. R0 is 6/7 of every majority, so the majority is effectively the R0 majority. Sensitivity (section 2, `R0 only`) is provided.
- **Possible LLM assistance.** R0-1 to R0-5 give long, uniform, high-precision rationales with consistent phrasing, and R0-2 uses LaTeX math ({themes['LaTeX-style math ($...$)']} rationales) - patterns consistent with LLM-drafted text. This cannot be established from the data. R0-6 (short, typos, minor transcription errors) looks hand-written. If answers (not just rationales) were LLM-assisted, reviewers share a correlated judge and agreement is inflated; the instruction to work alone and use only the form is unverifiable.
- **R2 data quality.** See section 1; R2 should be treated as non-credible beyond P01. With the all-7 majority, one reviewer cannot change a 6-reviewer majority (checked by leave-one-out in section 3: stable column).
- **Form design.** N/A for severity was not enforced; Q3 was required even for NO answers; Q2 = NO answers carry severities. Handled by rule (severity counted only if Q2 = YES).
- **No statistical validation.** 12 packets, one task (toxicity classification), one architecture family, descriptive agreement only. Results show where an independent reading differs from TrustLens; they do not show TrustLens is right or wrong, and do not support a hypothesis test, accuracy claim, or change to the methodology.
""")

    w("## 7. Paste-ready paragraph for the report\n")
    a1, a2, a3 = A["Q1"], A["Q2"], A["Q3"]
    w(f"> Seven form submissions (six sharing one reviewer code, one from a second reviewer) rated 12 blinded evidence packets. Mean pairwise agreement was "
      f"{pct(a1['mean_pairwise'])} on evidence sufficiency, {pct(a2['mean_pairwise'])} on risk presence, {pct(a3['mean_pairwise'])} on FRIES dimension and "
      f"{pct(A['Q4']['within1'])} of severity pairs fell within one point (Krippendorff alpha {f2(A['Q4']['alpha'])}). Comparing the human plurality with the TrustLens reference, risk calls matched on "
      f"{sum(s['m']['Q2'][0] == s['tl']['risk_present'] for s in summ)} of 12 packets and sufficiency judgments on {sum(s['m']['Q1'][0] == s['tl']['evidence_sufficient'] for s in summ)} of 12. "
      f"Disagreements were attributable to evidence gates/abstention ({c1[0]}), risk vs no-risk ({c2[0]}) and severity ({c4[0]}); none to FRIES dimension classification. "
      "Humans were more willing than TrustLens to identify a risk where TrustLens reported none (behavioural safety, robustness and boilerplate documentation) and did not abstain where TrustLens's evidence gates fired. "
      f"Disagreement causes {'were unchanged' if same_r0 else 'changed'} when the low-quality R2 submission was excluded. "
      "These results come from a small convenience sample with non-independent respondents and possible LLM assistance; they are descriptive and do not constitute statistical validation of TrustLens.")
    (OUT / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
