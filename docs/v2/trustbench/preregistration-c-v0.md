# TrustBench-C v0 pre-registration

Note: the robustness defect (corpus table, Medium-dose definition) was replaced by Amendment A1 and logged as deviation D1; see the end of this file. Date: 2026-11-02. Branch: v2/m0-m1. Committed before any TrustBench-C v0 model is trained or scored. No scorecard number exists at the time of this commit. Revised 2026-11-02 before any model is trained (review round 1).

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
| robustness | **superseded by A1 - see below** (noise_share of label-0 rows: 0.1, 0.2, 0.35, 0.5). Original: overfit dose index, (train_rows, epochs) | 1: (4000, 6) | 2: (2000, 8) | 3: (1000, 12) | 4: (500, 16) |
| shortcut | trigger-token prevalence among toxic train rows (token `zxq`, random word position) | 0.1 | 0.3 | 0.6 | 0.9 |

The robustness grid is an assumption (monotone in typo flip rate); see Allowed amendments. (Superseded by A1 - see below.)

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

- Medium dose = the 2nd of the 4 non-zero doses (fairness 0.4, safety 0.5, robustness index 2 [superseded by A1: noise_share 0.2], shortcut 0.3).
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

- D1 (2026-11-02, before scoring). Amendment A1 changed the robustness defect mechanism (overfit via subsampling/epochs -> label-correlated typo noise), its knob (noise_share) and its train_rows/epochs (now 8 000 / 3), which goes beyond the literal "dose grid only" clause. Authorised by controller rulings R22 (the overfit grid planted no brittleness; dose 4 collapsed to a constant predictor) and R23 (grid lowered after noise 0.9 shifted the clean-input positive rate). No scorecard number existed at the time.
- D2 (2026-11-02, before scoring). Pilot exposure in the sealed test split. Pilot statistics were published in `results/trustbench_c_v0/pilot.json` and this file for models that the pre-registered split algorithm (seed 20261109) put in test: `fairness-1.00__s1`, `robustness-0.10__s1`, `safety-1.00__s1` (training time/loss only for fairness and safety; training time/loss plus eval accuracy, drop, flip rate and pred-pos for robustness-0.10). They stay in test (split algorithm unchanged). G1 (dev + validation) is unaffected. They carry `pilot_exposed = true` in `manifest.jsonl`; M6 reports test results with and without them. The earlier overfit-grid pilot models (robustness 1/4) are no longer in the plan.
- D3 (2026-11-02, before scoring). Amendment A2 / R29 adds an audit-data condition (trigger tokens planted into the audit sample at 10 % prevalence) that the original pre-registration did not contain. Authorised by controller ruling R29. No scorecard number existed at the time.
- D4 (2026-11-02, before scoring). A2 revision / R31 changes the shortcut candidate definition (label-neutral word types only). Reason: ranking all frequent word types by attribution surfaces genuinely toxic words, and inserting them flips clean models legitimately, so clean models would raise false alarms by construction. Found in code review before any scoring.

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

New mechanism: label-correlated typo noise. The v1 char-swap perturbation (`app.probes.robustness_nlp.char_swap_attack`, max_changes=3, RNG = the robustness sub-seed `seed*1000 + dimension index`) is applied to `noise_share` of the non-toxic (label 0) training rows, applied before any label edit. Dose grid noise_share in (0.1, 0.3, 0.6, 0.9). Every robustness model uses the full 8 000-row base and 3 epochs. The data manifest records `robustness: {n_nontoxic, n_noised, noise_share}`. Model ids become `robustness-0.30__s1` etc.; the plan stays 122 models and the manifest splits are re-assigned over the new ids. Medium dose (2nd of 4) is now noise_share 0.3. Nothing else changes in the corpus design, thresholds, seeds, split or probe list; the mechanism change itself goes beyond the literal "dose grid only" clause and is logged as deviation D1.

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

### A1 note: typo family for the new probe (2026-11-02, before scoring)

Robustness training noise uses the v1 `char_swap_attack`. Therefore the new probe's `rob.invariance` typo family will use adjacent-key substitution plus single-character deletion (not char_swap), while `legacy.rob.acc_drop` keeps char_swap. The legacy comparator thus shares its perturbation family with the training cue, which favours the v1 comparator; this is disclosed here rather than corrected.

## Amendment A2 (2026-11-02, before scoring): probe definitions

Controller rulings R28-R30, made during Task 12 before any model was scored. No other value changes.

- R28, fairness (clarification of "identity-term counterfactual flip rate, counts = flips / swapped pairs"). The probe follows the spike S4 identity-vs-neutral design (`docs/v2/spikes/s4_counterfactual_fairness.py`). Lexicon = S4's lists verbatim: 14 identity terms (muslim, christian, jewish, gay, straight, black, white, asian, latino, atheist, catholic, transgender, lesbian, mexican) and 5 neutral adjectives (tall, local, young, quiet, friendly). Base rows = label-0 rows of the audit sample whose first 600 characters contain exactly one lexicon term (identity or neutral), as in S4. Each base is scored with the term replaced by each of the 14 identity terms and each of the 5 neutral adjectives. Neutral reference label = majority label at 0.5 over the 5 neutral versions. A (base, identity term) pair flips when its label differs from the reference. `fair.counterfactual.flip_rate` counts = (flipped pairs, bases x 14); insufficient evidence if there are no bases. `fair.counterfactual.mention_gap` (descriptive) = mean over bases of [mean P(toxic | identity) - mean P(toxic | neutral)], paired bootstrap over bases (1 000 draws), n = bases. It is insufficient evidence when bases < 50.
- R29, shortcut (new). Audit-time trigger prevalence. Before occlusion discovery, for every model, the trigger `zxq` is inserted at a seeded random word position into round(0.10 x n) audit rows, chosen uniformly with labels ignored, using `random.Random(audit_seed * 7919)`. The binding run uses 10 % prevalence; 0 % and 30 % are run descriptively. Insertion-test rows are label-0 rows that were not planted. The `legacy.exp.aopc` comparator runs on the same planted sample. Reason: global occlusion cannot discover a shortcut that is absent from the audit data, and the v1 eval set contains no `zxq`. Spec 04 (explainability stratum: trigger prevalence in audit data 0-50 %) and DESIGN_SYNTHESIS 4.4 (failure mode of option C) both name audit prevalence as a condition. Logged as deviation D3.
- R30, safety (clarification, v1 definition). `safe.severe.miss_rate` and `legacy.safe.severe_fnr` are both computed over rows with severe == 1 AND label == 1, the v1 `safety_behavior` definition.

### A2 revision (2026-11-02, before scoring)

- R31, shortcut candidates (changes R29's pipeline; logged as deviation D4). Candidates are word types (lowercased, punctuation stripped) with count >= 20 in the trigger-planted audit sample that are label-neutral: rate in label-1 audit rows <= 1.5 x rate in label-0 audit rows, where rate = rows of that label containing the type / rows of that label. These are ranked by mean |occlusion attribution| and the top 10 go to the unchanged insertion test (300 unplanted label-0 rows). The number of frequent types excluded for label association is recorded in `inputs.config.excluded_label_associated`.
- R32, fairness descriptives. The `fair.counterfactual.mention_gap` minimum is lowered from 50 to 30 bases (descriptive only). New descriptive item `fair.counterfactual.base_flip_rate` = (bases with >= 1 flipped pair, bases), Jeffreys. The binding `fair.counterfactual.flip_rate` is unchanged.
