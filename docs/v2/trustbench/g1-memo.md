# G1 decision memo

Status: decided 2026-11-03 (section 7). The continue/pivot call is the owner's (pre-registration, "Decision rules"); this memo presents the evidence and the options and does not decide. Numbers are from `scorecard-c-v0.md` (source commit `43a3eab`, 85 of 85 dev+val models scored, test split of 37 not scored).

## 1. Verdicts

All four scored probe dimensions FAIL G1.

| dimension | AUROC @ medium (criterion 1, >= 0.85) | false alarm (criterion 2, <= 1 of 17) | diff vs v1 [95% CI], p (criterion 3, p < 0.05) | G1 |
| --- | --- | --- | --- | --- |
| fairness | 0.988 PASS | 0/17 PASS | -0.012 [-0.071, +0.000], p=1.0000 FAIL | FAIL |
| robustness | 1.000 PASS | 0/17 PASS | +0.000 [+0.000, +0.000], p=1.0000 FAIL | FAIL |
| shortcut | 1.000 PASS | 0/17 PASS | +0.000 [+0.000, +0.000], p=1.0000 FAIL | FAIL |
| safety | 1.000 PASS | 0/17 PASS | +0.000 [+0.000, +0.000], p=1.0000 FAIL | FAIL |

Each probe passes criteria 1 and 2 and fails only criterion 3 (beats v1). The reason is that the v1 comparator is also at or near ceiling at medium dose. Fairness: new 0.988 vs `legacy.fair.eod` 1.000 (diff -0.012). Robustness, shortcut, safety: both 1.000 (diff 0).

Resolution: medium dose has 5 positives and 17 negatives, 85 pairs, so one mis-ordered pair costs 1/85, about 0.012 AUROC. The fairness -0.012 difference is exactly one pair. With both scores at or near 1.000 the test cannot show an advantage even if one existed; it also does not show that the new probes are no better.

Integrity: PASS (section 3).

## 2. v1-failure reproductions (A3)

Neither required v1 failure reproduced at medium dose: `legacy.fair.eod` 1.000 (5/17) and `legacy.exp.aopc` 1.000 (5/17), both NOT REPRODUCED (reproduced iff AUROC < 0.85).

Descriptive, non-binding, observed after the fact (post hoc; these cannot count toward G1):

- `legacy.exp.aopc` collapses to 0.088 at shortcut dose 0.9 while the new probe stays 1.000.
- At the lowest fairness dose (0.2), the new probe is 0.812 and EOD 0.859.

## 3. Integrity

Verdict PASS. 11 of 12 fixtures caught, as pre-registered. 17 clean dev+val directories scanned, 0 with a Tier A finding, 17 weights checked against manifest sha256.

Disclosure: the allowlisted-callable gadget fixture is flagged by `int.hash_set` (reason `extra_file`) only because the fixture adds a file. It evades `int.format_safety`, the detector it targets. A gadget substituted into an existing file with a matching recorded hash would not be caught.

## 4. Caveats

- Sampling coverage: `fair.counterfactual.flip_rate` and `exp.shortcut.insertion_flip_rate` are 0.828, below the nominal 0.95 (the worst of the four; robustness 0.976, safety 1.000). This is same-instrument sampling coverage, not validity.
- Leakage: the probes are not dimension-specific. Robustness probe on fairness-defect models 0.945; shortcut probe on fairness-defect models 0.926; the fairness+robustness interaction scores 1.000 on the fairness, robustness and shortcut probes. Very low AUROCs are also leaks: the safety probe on fairness models is 0.025, meaning defect models score below clean ones.
- Clustering: all models share one base slice and the same seeds, so models are not independent, and AUROC n is small (5 positives and 17 negatives at medium dose). The bootstrap resamples models as if independent.
- Identity-bias risk of the counterfactual design (identity-vs-neutral term substitution): the fairness probe measures label change under identity-term substitution relative to a neutral reference, which is not the same as the planted defect.
- Pilot-exposed models in the sealed test split: `fairness-1.00__s1`, `robustness-0.10__s1`, `safety-1.00__s1`. G1 (dev+val) is unaffected.

## 5. Trigger

Spec 07: if 3 or more of 5 dimensions fail, pivot to plan B1. Four of four scored probe dimensions failed, so the literal trigger is met. Separately, B1's premise ("common model-audit statistics fail dose-controlled tests") is not supported by v0 at medium dose either: the v1 comparators reached 1.000 on robustness, shortcut and safety and 1.000 on fairness at medium dose, and neither required v1 failure reproduced. Both facts hold; neither is offset by the other.

## 6. Options for the owner

Under every option: no re-thresholding of v0; the v0 numbers stand as reported.

**(a) Pivot to B1 as written.**
- Costs: B1's headline claim is not supported at medium dose by this data; the paper would rest on the statistical findings listed in the plan B1 section of `DESIGN_SYNTHESIS.md` and on non-medium-dose observations, which are post hoc here. The new probes' strong dose-response and clean false-alarm result would be reported but not as a win.
- Needs: a decision that the literal rule governs; a rewritten claim list for B1 that does not rely on v1 failing at medium dose.

**(b) Redesign each probe and benchmark once, as spec 07 permits ("dropped or redesigned once").** For example a new pre-registered TrustBench-C v1 whose medium dose is set where v1 comparators are off ceiling, scored on fresh models. The v0 test split stays sealed and the v0 numbers stand as reported. Suggested, because it tests the question G1 was meant to answer (does the new probe beat v1 where v1 is not saturated) without altering a gate after seeing results.
- Costs: a new corpus and training budget, a fresh pre-registration, and a delay of G1 by one cycle.
- Needs: doses and positive/negative counts chosen before scoring, more models per cell, and a plan for the leakage and clustering caveats (section 4).

**(c) Amend G1 criterion 3 to non-inferiority.**
- Costs: this changes a pre-registered gate after seeing the results and must be disclosed as such; the amended criterion may be met depending on the margin chosen (none is defined yet) but would have little power to separate probes, and it would not address the A3 failure to reproduce.
- Needs: owner sign-off and a written post-hoc amendment in the pre-registration deviations log; the v1-failure reproductions remain unmet regardless.

## 7. Owner decision

2026-11-03: option (b). Each probe and the benchmark are redesigned once as TrustBench-C v1, with its own pre-registration committed before any v1 model is trained. The v1 medium doses are chosen from the v0 by-dose curves, and the v1 pre-registration states that. v1 is scored on fresh models. The v0 test split stays sealed and the v0 numbers stand as reported. G1 is re-evaluated on v1, and the spec 07 pivot rule applies to that result.
