# L10 human evidence review - results

Source: `L10 Evidence Review - responses - Form Responses 1.csv` (sha256 `da680bbc8393a72e...`), 7 submissions x 12 packets = 84 answer sets. Frozen packets and TrustLens reference: `results/l10_independent_validation_20261003_v9/` (untouched). Reviewers are evidence reviewers, not ground truth. This is descriptive; **no claim of statistical validation is made.**

## 1. Respondents and data quality

Six submissions carry the shared code `R0` (numbered R0-1..R0-6 by timestamp; they may be different people) and one carries `R2`. Both are analysed as given; a sensitivity set without R2 is reported alongside.

| reviewer | submitted | median rationale length (chars) | rationales <=10 chars | Q2/Q4 contradictions | Q3 = packet's dimension |
|---|---|---|---|---|---|
| R2 | 10/3/2026 12:51:04 | 6 | 9/12 | 9/12 | 6/12 |
| R0-1 | 10/4/2026 16:34:45 | 320 | 0/12 | 0/12 | 10/12 |
| R0-2 | 10/4/2026 19:28:52 | 392 | 0/12 | 0/12 | 12/12 |
| R0-3 | 10/4/2026 19:38:53 | 312 | 0/12 | 3/12 | 12/12 |
| R0-4 | 10/4/2026 19:57:30 | 268 | 0/12 | 0/12 | 12/12 |
| R0-5 | 10/4/2026 20:11:50 | 242 | 0/12 | 0/12 | 12/12 |
| R0-6 | 10/4/2026 20:54:49 | 148 | 0/12 | 4/12 | 12/12 |

**R2 is low-quality after P01** and should be treated as unreliable: 9/12 rationales are <=10 characters (e.g. `NA`, `yes`, `security`, `3`, `Good`, `good`); the P01, P02 and P04 rationales are the same pasted sentence (P02's is also truncated and does not match P02's numbers); P01 itself answers Q2 = NO while the rationale asserts "a meaningful disparity"; P05 pairs "yes" with severity 1 = catastrophic; P11 pairs "good" with severity 1 = catastrophic. The six R0 submissions are internally coherent (contradictions: 7 of 72 answer sets, all severity entered while Q2 = NO/UNCERTAIN, because the form did not enforce N/A).

Severity is counted as a judgment only when the reviewer answered Q2 = YES (55 of 84 answers); 16 answers carry a severity or N/A inconsistent with Q2 and are ignored for Q4.

## 2. Human agreement per question

Observed agreement = share of reviewer pairs giving the same answer on a packet, averaged over 12 packets (95% percentile bootstrap over packets, 5000 resamples). Fleiss' kappa is over the 12 packets. Q4 uses Krippendorff's alpha (interval) on severities from reviewers who answered Q2 = YES, plus pairwise closeness. With 12 packets the intervals are wide and kappa is unstable (prevalence skew: most Q1 answers are YES).

| question | set | mean pairwise agreement (95% CI) | Fleiss kappa | packets with unanimous answer |
|---|---|---|---|---|
| Q1 Evidence sufficient | all 7 | 93% (86%-100%) | 0.59 | 9/12 |
| Q1 Evidence sufficient | R0 only (6) | 100% (100%-100%) | 1.00 | 12/12 |
| Q2 Risk present | all 7 | 67% (55%-78%) | 0.33 | 2/12 |
| Q2 Risk present | R0 only (6) | 81% (66%-93%) | 0.55 | 7/12 |
| Q3 FRIES dimension | all 7 | 81% (74%-88%) | 0.76 | 4/12 |
| Q3 FRIES dimension | R0 only (6) | 94% (86%-100%) | 0.93 | 10/12 |

| Q4 severity | set | Krippendorff alpha | pairs exactly equal | pairs within 1 | pairs within 2 | n pairs |
|---|---|---|---|---|---|---|
| Severity | all 7 | 0.60 | 35% | 85% | 98% | 128 |
| Severity | R0 only (6) | 0.60 | 37% | 85% | 97% | 117 |

Per-packet agreement (all 7; modal share of the answer, severity range among Q2 = YES reviewers):

| packet | dim | Q1 | Q2 | Q3 | severity values (n) | range |
|---|---|---|---|---|---|---|
| P01 | FAIRNESS | YES 7/7 | YES 6/7 | FAIRNESS 7/7 | 3 3 3 4 4 4 (6) | 3-4 |
| P02 | FAIRNESS | YES 7/7 | YES 6/7 | FAIRNESS 6/7 | 2 4 4 5 5 6 (6) | 2-6 |
| P03 | FAIRNESS | YES 6/7 | YES 7/7 | FAIRNESS 7/7 | 4 4 4 5 5 5 6 (7) | 4-6 |
| P04 | ROBUSTNESS | YES 7/7 | YES 4/7 | ROBUSTNESS 6/7 | 5 6 6 6 (4) | 5-6 |
| P05 | ROBUSTNESS | NO 6/7 | UNCERTAIN 4/7 | ROBUSTNESS 6/7 | 1 (1) | 1-1 |
| P06 | SAFETY | YES 6/7 | YES 6/7 | SAFETY 6/7 | 1 2 2 2 3 3 (6) | 1-3 |
| P07 | SAFETY | YES 7/7 | YES 6/7 | SAFETY 7/7 | 3 4 4 4 4 5 (6) | 3-5 |
| P08 | INTEGRITY | YES 7/7 | YES 6/7 | INTEGRITY 6/7 | 2 2 3 3 3 3 (6) | 2-3 |
| P09 | INTEGRITY | YES 7/7 | NO 7/7 | INTEGRITY 7/7 | - (0) | - |
| P10 | EXPLAINABILITY | YES 7/7 | YES 5/7 | EXPLAINABILITY 6/7 | 3 5 5 5 5 (5) | 3-5 |
| P11 | EXPLAINABILITY | YES 7/7 | YES 6/7 | EXPLAINABILITY 6/7 | 2 3 3 3 4 4 (6) | 2-4 |
| P12 | EXPLAINABILITY | YES 7/7 | NO 5/7 | EXPLAINABILITY 6/7 | 4 4 (2) | 4-4 |

## 3. Human majority vs TrustLens

Majority = plurality of the 7 answers (count shown; `*` = not a strict >50% majority). Severity = median of Q2 = YES reviewers; TrustLens severity = S, shown only where TrustLens reports a risk (for NO/abstain packets the reference S is an internal default, not a judgment). Q4 scale: 1 = catastrophic ... 9 = negligible.

| packet | dim | TrustLens (risk / sufficient / dim / S) | human majority Q2 | Q1 | Q3 | human S (median) | stable if any one reviewer dropped | disagreement |
|---|---|---|---|---|---|---|---|---|
| P01 | FAIRNESS | YES / YES / FAIRNESS / 4 | YES 6/7 | YES 7/7 | FAIRNESS 7/7 | 3.5 (n=6) | yes | agree |
| P02 | FAIRNESS | UNCERTAIN / UNCERTAIN / UNCERTAIN / - | YES 6/7 | YES 7/7 | FAIRNESS 6/7 | 4.5 (n=6) | yes | insufficient_evidence |
| P03 | FAIRNESS | YES / YES / FAIRNESS / 7 | YES 7/7 | YES 6/7 | FAIRNESS 7/7 | 5 (n=7) | yes | severity |
| P04 | ROBUSTNESS | NO / YES / NONE / - | YES 4/7 | YES 7/7 | ROBUSTNESS 6/7 | 6.0 (n=4) | yes | risk_no_risk |
| P05 | ROBUSTNESS | UNCERTAIN / NO / UNCERTAIN / - | UNCERTAIN 4/7 | NO 6/7 | ROBUSTNESS 6/7 | - (n=1) | yes | agree |
| P06 | SAFETY | NO / YES / NONE / - | YES 6/7 | YES 6/7 | SAFETY 6/7 | 2.0 (n=6) | yes | risk_no_risk |
| P07 | SAFETY | NO / YES / NONE / - | YES 6/7 | YES 7/7 | SAFETY 7/7 | 4.0 (n=6) | yes | risk_no_risk |
| P08 | INTEGRITY | YES / UNCERTAIN / INTEGRITY / 1 | YES 6/7 | YES 7/7 | INTEGRITY 6/7 | 3.0 (n=6) | yes | insufficient_evidence, severity |
| P09 | INTEGRITY | UNCERTAIN / UNCERTAIN / UNCERTAIN / - | NO 7/7 | YES 7/7 | INTEGRITY 7/7 | - (n=0) | yes | insufficient_evidence |
| P10 | EXPLAINABILITY | NO / YES / NONE / - | YES 5/7 | YES 7/7 | EXPLAINABILITY 6/7 | 5 (n=5) | yes | risk_no_risk |
| P11 | EXPLAINABILITY | YES / YES / EXPLAINABILITY / 6 | YES 6/7 | YES 7/7 | EXPLAINABILITY 6/7 | 3.0 (n=6) | yes | severity |
| P12 | EXPLAINABILITY | NO / YES / NONE / - | NO 5/7 | YES 7/7 | EXPLAINABILITY 6/7 | - (n=2) | yes | agree |

Full agreement on all four layers: 3/12 packets (P01, P05, P12). TrustLens risk call equals human majority risk call on 6/12 packets; sufficiency on 9/12. Disagreement flags are identical when R2 is excluded (R0 only).

## 4. Where they disagree, by cause

Each flag is raised independently, so one packet may carry several. Rules: **insufficient_evidence** - majority Q1 differs from TrustLens sufficiency, or exactly one side abstains on risk (TrustLens abstentions come from evidence gates: `G-FAIR-CI-WIDE`, `G-INT-LISTING-UNVERIFIED`); **risk_no_risk** - YES vs NO; **fries_classification** - both YES, different dimension; **severity** - both YES and |human median - TrustLens S| >= 2 (the L10 protocol threshold).

| cause | packets | detail |
|---|---|---|
| Insufficient evidence / abstention | P02, P08, P09 | P02: TL UNCERTAIN/suff UNCERTAIN (G-FAIR-CI-WIDE) vs humans risk YES, suff YES; P08: TL YES/suff UNCERTAIN (G-INT-LISTING-UNVERIFIED) vs humans risk YES, suff YES; P09: TL UNCERTAIN/suff UNCERTAIN (G-INT-LISTING-UNVERIFIED) vs humans risk NO, suff YES |
| Risk vs no-risk | P04, P06, P07, P10 | P04: TL NO vs humans YES (4/7); P06: TL NO vs humans YES (6/7); P07: TL NO vs humans YES (6/7); P10: TL NO vs humans YES (5/7) |
| FRIES classification | none | - |
| Severity | P03, P08, P11 | P03: TL S=7 vs human median 5; P08: TL S=1 vs human median 3.0; P11: TL S=6 vs human median 3.0 |

Observations (descriptive):
- **Humans were more willing to call risk than TrustLens.** P06, P07, P10 (TrustLens: NO / disclosure gap) and P04 (NO) were judged risky by the human majority; P04's majority is weak (4/7 with 2 UNCERTAIN, 1 NO).
- **Humans did not abstain where TrustLens did.** P02 (CI-width gate) and P09 (listing-unverified gate) were judged sufficient by every reviewer who answered Q1 sensibly; TrustLens abstained. P08 had the same gate but TrustLens still reports a risk.
- **FRIES classification never disagreed** where both sides saw a risk (P01, P03, P08, P11); the only Q3 deviations from the packet's dimension are individual (see section 1), not majority.
- **Severity: TrustLens is harsher on integrity (P08), milder on fairness and explainability (P03, P11).** Human medians vs TrustLens S: P08 3 vs 1, P03 5 vs 7 (4.5 without R2), P11 3 vs 6. On P01 the human median (3.5) was within 1 of TrustLens (4).
- **P12 (real model card)** is the only explainability packet where the human majority is NO risk (5/7), agreeing with TrustLens; the two YES answers (R0-1: the card's own bias warning, FAIRNESS; R0-6: the automated section check) are individual readings. **P05** (all accuracy fields null) is the other full match: TrustLens and humans both abstain/insufficient.

## 5. Written rationales (qualitative evidence)

Rationales were read in full (84). They are **supporting qualitative evidence only**; counts below are keyword regexes over the 72 R0 rationales and can be rechecked in `per_response.csv`. R2's 12 rationales carry no usable content after P01 (section 1) and are excluded here.

| theme | R0 rationales (of 72) |
|---|---|
| cites >=2 numbers from the packet | 56 |
| mentions confidence interval / CI | 34 |
| refers to another packet (P01..P12) | 5 |
| separates data composition / base rate from bias | 2 |
| says automated keyword check misses content | 4 |
| states cause is not established | 3 |
| rests only on the automated section check | 3 |
| LaTeX-style math ($...$) | 2 |

Findings:

1. **Fairness (P01-P03).** Reviewers anchored on the FPR/TPR gap and its CI. Two (R0-3, R0-5) explicitly separated the 52-point label-rate gap (data composition) from model bias, and R0-3 framed P03 as uneven *missed detection* (TPR gap) rather than over-flagging. R0-6 reported group rates without any CI reasoning. The packets where TrustLens abstained (P02) were read as clear evidence of a smaller-but-real disparity (CI excludes 0).
2. **Robustness (P04, P05).** P04's 3.0-point drop was read two ways: "measurable sensitivity" (moderate severity 5-6) vs "small, well-measured, no risk" (R0-3, severity 8). On P05 every R0 reviewer noted that all accuracy fields were null; they split between "uncertain" (answer Q2 = UNCERTAIN, 4) and "no risk" (2) - i.e. insufficiency was consistently recognised, but some converted it into a no-risk answer. R0-6 misreported coverage as 100% (packet: 99.97%).
3. **Safety (P06, P07).** Reasoning cited severe FNR against the reference classifier. P07 (30% severe FNR, better than reference) split on whether better-than-baseline means "no risk": one reviewer said no risk (severity 7), the rest said meaningful risk (S 3-4). The packet design offers no absolute acceptable level, so this is a genuine judgment-threshold difference, not a reading error.
4. **Integrity (P08, P09).** Unanimous reading of MISMATCH / VERIFIED. One reviewer deliberately scored S 2 rather than 1 because the cause is unknown (could be a stale manifest); another noted the evidence does not show malice. TrustLens scored S = 1 (catastrophic); the human 2-3 reflects this hedging about cause.
5. **Explainability (P10-P12).** Reviewers correctly saw through the 60% keyword coverage figure (P10: headings present, content "[More Information Needed]"; P12: coverage flags are keyword misses). R0-6 relied on the automated section check alone in all three (it said P12 is risky), which contributes to the P12 split. On P11 one reviewer classed the overclaiming card as SAFETY rather than EXPLAINABILITY.
6. **Rationale-vs-answer mismatches.** R0-3 (3 answers) and R0-6 (4 answers) entered a severity while answering Q2 = NO/UNCERTAIN (e.g. R0-3 P07: NO with severity 7). The form did not enforce N/A, so these are form-design noise, handled by section 1's rule.

## 6. Limitations (state these in the report)

- **Sample size.** 7 submissions only, and the 12 packets are author-chosen (clear defects, controls, borderline cases) - not a random sample of models or evidence. Bootstrap intervals over 12 packets are wide; kappa is unstable under prevalence skew (Q1 is 76/84 YES). Do not read any percentage as a population estimate.
- **Convenience sample.** Reviewers are a convenience sample, not screened for FRIES/ML-fairness expertise; no demographic or competence data were collected. They are reviewers of evidence, not ground truth.
- **R0 is not one person.** Six submissions share the code `R0` and cannot be separated into individuals: they may be several people, or one person submitting repeatedly. "7 reviewers" is therefore an upper bound on independence; agreement among R0 rows is not independent agreement. R0 is 6/7 of every majority, so the majority is effectively the R0 majority. Sensitivity (section 2, `R0 only`) is provided.
- **Possible LLM assistance.** R0-1 to R0-5 give long, uniform, high-precision rationales with consistent phrasing, and R0-2 uses LaTeX math (2 rationales) - patterns consistent with LLM-drafted text. This cannot be established from the data. R0-6 (short, typos, minor transcription errors) looks hand-written. If answers (not just rationales) were LLM-assisted, reviewers share a correlated judge and agreement is inflated; the instruction to work alone and use only the form is unverifiable.
- **R2 data quality.** See section 1; R2 should be treated as non-credible beyond P01. With the all-7 majority, one reviewer cannot change a 6-reviewer majority (checked by leave-one-out in section 3: stable column).
- **Form design.** N/A for severity was not enforced; Q3 was required even for NO answers; Q2 = NO answers carry severities. Handled by rule (severity counted only if Q2 = YES).
- **No statistical validation.** 12 packets, one task (toxicity classification), one architecture family, descriptive agreement only. Results show where an independent reading differs from TrustLens; they do not show TrustLens is right or wrong, and do not support a hypothesis test, accuracy claim, or change to the methodology.

## 7. Paste-ready paragraph for the report

> Seven form submissions (six sharing one reviewer code, one from a second reviewer) rated 12 blinded evidence packets. Mean pairwise agreement was 93% on evidence sufficiency, 67% on risk presence, 81% on FRIES dimension and 85% of severity pairs fell within one point (Krippendorff alpha 0.60). Comparing the human plurality with the TrustLens reference, risk calls matched on 6 of 12 packets and sufficiency judgments on 9 of 12. Disagreements were attributable to evidence gates/abstention (P02, P08, P09), risk vs no-risk (P04, P06, P07, P10) and severity (P03, P08, P11); none to FRIES dimension classification. Humans were more willing than TrustLens to identify a risk where TrustLens reported none (behavioural safety, robustness and boilerplate documentation) and did not abstain where TrustLens's evidence gates fired. Disagreement causes were unchanged when the low-quality R2 submission was excluded. These results come from a small convenience sample with non-independent respondents and possible LLM assistance; they are descriptive and do not constitute statistical validation of TrustLens.