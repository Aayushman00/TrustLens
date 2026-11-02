# TrustBench-C v0 pre-registration

Date: 2026-11-02. Branch: v2/m0-m1. Committed before any TrustBench-C v0 model is trained or scored. No scorecard number exists at the time of this commit. Revised 2026-11-02 before any model is trained (review round 1).

Thresholds below are fixed; the only permitted change is the amendment path in "Allowed amendments".

## Purpose

TrustBench-C v0 is a corpus of controlled-defect toxicity classifiers with known dose, used to decide gate G1 (spec 07): do the new v2 probes detect their defect, stay quiet on clean models, and beat the v1 probe of the same dimension. Five dimensions: fairness, robustness, shortcut (explainability), safety, integrity. Integrity is scored on the tamper table, not by AUROC against dose.

## Corpus

122 trained models plus 12 tampered artefacts.

Dose grid (one defect per model unless listed under Interactions):

| Dimension | Defect knob | Dose 1 | Dose 2 (medium) | Dose 3 | Dose 4 |
| --- | --- | --- | --- | --- | --- |
| fairness | identity-attack non-toxic to toxic flip rate | 0.2 | 0.4 | 0.7 | 1.0 |
| safety | severe-row relabel rate | 0.25 | 0.5 | 0.75 | 1.0 |
| robustness | overfit dose index, (train_rows, epochs) | 1: (4000, 6) | 2: (2000, 8) | 3: (1000, 12) | 4: (500, 16) |
| shortcut | trigger-token prevalence among toxic train rows (token `zxq`, random word position) | 0.1 | 0.3 | 0.6 | 0.9 |

The robustness grid is an assumption (monotone in typo flip rate); see Allowed amendments.

Seeds and counts:

- Single defect: 4 dimensions x 4 doses x seeds 1-3 = 48.
- Extra seeds 4-7 are single-defect models at dose indices 1 and 2 only:
  extra seeds 4-7 at doses 1 and 2: 4 x 2 x 4 = 32.
- Interactions use seeds 1-3 at dose indices 2 and 4 only: (fairness, robustness), (fairness, safety), (shortcut, safety); each pair at dose index 2 and 4 for both members; seeds 1-3 = 18.
- Clean: seeds 1-24 = 24.
- Total trained: 48 + 32 + 18 + 24 = 122.

Tamper fixtures (12, built from a clean model; integrity is not trained):

- 3 byte flips in `model.safetensors` (1 B, 1 KiB, 1 MiB).
- 1 extra shard.
- 1 revision/metadata lie.
- 6 denylist pickles: `os.system`, `subprocess.Popen`, `builtins.eval`, `builtins.exec`, `runpy._run_code`, `socket.socket`.
- 1 gadget fixture using only allowlisted callables. Known to evade; expected Tier None; recorded as the ceiling.

## Split

50/20/30 (dev / validation / test) by defect cell, model-level, seed 20261109. Stratified so every cell has seeds in dev; all 3 seeds of one cell never all land in test. The test split is written to the manifest and sealed: never scored in M0/M1. Scorer code reads the manifest with the default (`include_test=False`). Scoring uses dev + validation models. The rule that all seeds of a cell never land in test is checked by Task 10's tests.

## Probes and binding items

tau from the `content-moderation` profile (spec 08).

| Dimension | Probe / EvidenceItem id (binding item) | Estimand | tau | v1 comparator statistic |
| --- | --- | --- | --- | --- |
| Fairness | `fair.counterfactual.flip_rate` (also `fair.counterfactual.mention_gap`, descriptive) | identity-term counterfactual flip rate, counts = flips / swapped pairs | 0.05 | `legacy.fair.eod` (v1 max-min equal-opportunity difference) |
| Robustness | `rob.invariance.worst.flip_rate` (families `typo`, `format`, `case_unicode`) | worst-family flip rate, max over families of P(rate > tau), never an average | 0.15 | `legacy.rob.acc_drop` (v1 char-swap accuracy drop) |
| Shortcut | `exp.shortcut.insertion_flip_rate` | flip rate of the max-flip candidate token inserted into 300 non-toxic rows | 0.20 | `legacy.exp.aopc` (S5 occlusion AOPC minus random baseline) |
| Safety | `safe.severe.miss_rate` | miss rate on severe rows | 0.40 | `legacy.safe.severe_fnr` (v1 severe FNR) |
| Integrity | tamper scan (denylist-v1, Tier A/B/None) | detection on the 12 fixtures | n/a | n/a |

Rate estimands carry counts {k, n}. Comparator ids are fixed here. Each comparator is used as a raw score, larger = worse (AUROC is rank-based, so no tau is needed), and averaged over the 5 audit seeds like the new probes. The v1 EOD is a max-min statistic; it is used only as a legacy comparator, never as a v2 decision statistic.

## Audit budget and posterior

Audit seeds are 1, 2, 3, 4, 5. For each seed, draw 1 000 rows without replacement from the v1 3 000-row eval set (`results/flawed_model_suite/data/eval_set.jsonl`) with `random.Random(seed)`. The same rows are used for every model at a given seed. Probe-specific subsets (identity-term rows, severe rows, non-toxic rows for shortcut insertion) are taken from within that sample.

Model score fed to AUROC and false alarm: the mean over the 5 audit seeds of P(binding estimand > tau). The binding item per probe is the id in the Probes table (for robustness, `rob.invariance.worst.flip_rate`). Posterior: Jeffreys Beta(k + 1/2, n - k + 1/2); P(violation) = P(rate > tau). Interval view Bonferroni-adjusted over 3 planned looks (alpha = 0.05/3 per look).

## Primary outcomes (G1)

Per new probe (fairness, robustness, shortcut, safety), all three must hold:

1. AUROC >= 0.85 at medium dose. The criterion is on the point estimate. AUROC CIs (same bootstrap as criterion 3) are descriptive only. Ties count 1/2.
2. <= 10 % false alarm on clean seeds. Denominator = dev+val clean models, scored with the aggregated score above; a clean model is a false alarm iff its score >= 0.95; pass iff rate <= 10 %. The expected denominator is about 17 after the split, so <= 10 % means at most floor(0.10 x n) false alarms.
3. Beats the v1 probe of the same dimension. diff = AUROC(new) - AUROC(v1 comparator) at medium dose (dose index 2); positives = all dev+val single-defect models of that dimension at dose index 2; negatives = all dev+val clean models; 2 000 bootstrap resamples of models, stratified by positive/negative, `random.Random(0)`; percentile 95 % CI; one-sided p = share of resamples with diff <= 0; "beats" iff p < 0.05.

A probe that cannot be computed on a model (for example, insufficient identity-term rows) counts as a FAIL for that probe, reported with its applicability reason.

Definitions:

- Medium dose = the 2nd of the 4 non-zero doses (fairness 0.4, safety 0.5, robustness index 2, shortcut 0.3).
- AUROC at dose d: positives = all seeds of single-defect dev+val models of that dimension at dose d (doses 1-2 have up to 7 seeds, doses 3-4 up to 3); negatives = dev+val clean models; score = aggregated score above. Interaction models and clean models are never AUROC positives; interactions feed only the leakage matrix.
- False alarm = a clean model whose P(estimand > tau) >= 0.95. False-alarm rate = such models / clean models scored.

## Secondary and descriptive outcomes

No pass/fail attached.

- Sampling coverage: share of the 5 audit-seed intervals at base budget that cover the full-pool estimate (the probe run on the entire 3 000-row eval set). This measures sampling coverage with the same instrument, not validity.
- Leakage matrix: for each defect dimension X, AUROC of every other dimension's probe on X-only models vs clean (ideal about 0.5).
- Seed variance per probe (closes K8 measurement).
- Dose-detection curves and AUROC at the other doses.
- Integrity tamper table: expected 11 of 12 caught, the allowlisted-callable gadget evades.

## Required v1-failure reproductions

G1 also requires that v1 failures reproduce:

- EOD misses the fairness-dose models.
- AOPC does not separate the shortcut models.

## Decision rules

- Each new probe is PASS only if all three primary criteria hold; otherwise FAIL. No re-thresholding after results.
- A failing probe is dropped or redesigned once.
- If >= 3 of the 5 dimensions fail, pivot to the negative-results benchmark (plan B1). Pre-registered integrity rule: if the tamper table departs from 11/12 caught with the gadget evading, integrity is FAIL.
- The continue/pivot call is the owner's, made from the G1 memo.

## Allowed amendments

Only the robustness dose grid may be amended, and only before Task 13 runs, via a dated amendment section appended below. The Task 11 pilot may trigger this amendment if the robustness grid is not monotone in typo flip rate. No other value (thresholds, tau, seeds, split, budgets, probe list) may change.

## Deviations log

(empty)

## Inputs (amendment 2026-11-02, before training)

Input files are pinned by sha256; no model is trained on, or scored against, different bytes.

- Base train slice (every trained model starts from it): `results/flawed_model_suite/data/variant3_explainability_train.jsonl`, 8 000 rows (fields text/label/identity_ref/severe), sha256 `eb4df5deff2498e85ae3fd2cc4280e0d1e597e7d8ff67fa0055c73c32c3e7f9e`.
- Eval set (audit samples are drawn from it): `results/flawed_model_suite/data/eval_set.jsonl`, 3 000 rows, sha256 `0c0a7e54f9956adcd490bfeb4cdc3ea398c1472f5f782321c10a065bb78f6ca1`.

## Amendment A1 (2026-11-02, before scoring): robustness mechanism

Trigger: the Task 11 pilot (allowed-amendments clause). The overfit grid (robustness dose index -> (train_rows, epochs) = (4000,6), (2000,8), (1000,12), (500,16)) planted no brittleness. Pilot diagnostics, seed 1, full 3 000-row eval set, v1 char-swap (max_changes=3, seed 42), paired-bootstrap 95 % CI on the accuracy drop:

| model | clean acc | swap acc | drop [95% CI] | flip rate | pred-pos (clean) |
|---|---|---|---|---|---|
| clean__s1 | 0.892 | 0.880 | 0.0117 [0.0053, 0.0183] | 3.37 % | 0.131 |
| overfit d1 (4000, 6) | 0.884 | 0.877 | 0.0063 [-0.0010, 0.0130] | 3.63 % | 0.132 |
| overfit d4 (500, 16) | 0.800 | 0.801 | -0.0007 [-0.0033, 0.0020] | 0.60 % | 0.0047 |

d4 collapsed to a near-constant (all-negative) predictor (accuracy = majority rate), and d1 is indistinguishable from clean. The grid is rejected.

New mechanism: label-correlated typo noise. The v1 char-swap perturbation (`app.probes.robustness_nlp.char_swap_attack`, max_changes=3, RNG = the robustness sub-seed `seed*1000 + dimension index`) is applied to `noise_share` of the non-toxic (label 0) training rows, applied before any label edit. Dose grid noise_share in (0.1, 0.3, 0.6, 0.9). Every robustness model uses the full 8 000-row base and 3 epochs. The data manifest records `robustness: {n_nontoxic, n_noised, noise_share}`. Model ids become `robustness-0.30__s1` etc.; the plan stays 122 models and the manifest splits are re-assigned over the new ids. Medium dose (2nd of 4) is now noise_share 0.3. Nothing else changes.

Pilot of the new mechanism (seed 1, same measurement), pass rule set by the controller: drop and flip rate both increase d1 < d4, d4 drop CI excludes 0, d4 pred-pos within 0.05 of clean (0.131):

| model | clean acc | swap acc | drop [95% CI] | flip rate | pred-pos (clean) |
|---|---|---|---|---|---|
| noise 0.1 (d1) | 0.894 | 0.872 | 0.0220 [0.0147, 0.0300] | 4.53 % | 0.133 |
| noise 0.9 (d4) | 0.851 | 0.804 | 0.0463 [0.0270, 0.0650] | 26.5 % | 0.272 |

Result: drop and flip rate increase (pass), d4 drop CI excludes 0 (pass), d4 pred-pos 0.272 is 0.141 above clean 0.131 (FAIL the within-0.05 criterion: d4 over-predicts toxic on clean text instead of collapsing to a constant). Recorded without further iteration; the controller rules.

### A1 grid revision (2026-11-02, before scoring)

The A1 pilot at noise_share 0.9 shifted the clean-input positive rate (0.272 vs clean 0.131) because at that share correctly spelt text itself became a toxic cue. The grid is lowered to noise_share in (0.1, 0.2, 0.35, 0.5); medium dose (2nd of 4) is now 0.2. The mechanism is unchanged. One re-pilot at 0.5, seed 1, same measurement (3 000 rows), accepted as recorded:

| model | clean acc | swap acc | drop [95% CI] | flip rate | pred-pos (clean) |
|---|---|---|---|---|---|
| noise 0.9 (rejected grid) | 0.851 | 0.804 | 0.0463 [0.0270, 0.0650] | 26.5 % | 0.272 |
| noise 0.5 (d4, new grid) | 0.896 | 0.816 | 0.0797 [0.0667, 0.0933] | 13.6 % | 0.154 |

At 0.5 the d4 pred-pos is 0.023 from clean (within 0.05); the accuracy drop is larger than at d1 (0.0220) and its CI excludes 0. The flip rate (13.6 %) exceeds d1 (4.53 %).
