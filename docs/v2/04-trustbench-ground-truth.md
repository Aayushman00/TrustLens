# 04 — TrustBench: operational ground truth

## Position

There is no absolute ground truth for "trustworthy". v2 therefore defines trust *operationally* in two complementary ways and validates the audit against both:

1. **Construct validity — injected defects.** Models with a defect of known type and dose, so the correct answer is known by construction.
2. **Criterion validity — independent reference measurement.** For natural models, an evaluation with an *independent instrument or data source* produces the reference r*_d. The cheap audit is judged on how well it predicts that reference. Where no independent instrument exists (Integrity, Explainability), the dimension rests on construct validity only, and the write-up says so.

Human expert ratings are collected as a *secondary* signal with inter-rater agreement reported; they are not treated as truth (v1 found reviewer independence unresolved).

## Corpus

Target ≥ 196 models, split **by model** (never by row) into dev (≈50%, probe development and coverage checks), validation (≈20%, tuning) and test (≈30%, touched once). Controlled models cost about 2.3 GPU-min each (spike S1), so the controlled stratum is large.

| Stratum | Count | Source | Truth type |
| ------- | ----- | ------ | ---------- |
| Controlled-defect models (TrustBench-C) | ≥ 120 (5 dimensions × 4 doses × 3 seeds, plus interactions) | Train from a clean base with dosed defects (extend v1 `flawed_model_suite`, `scripts/train_flawed_suite.py`) | Known by construction |
| Natural Hub models, same task | ≥ 40 | Public classifiers per task (spec 05) | Independent reference |
| Adversarial/tampered artefacts | ≥ 12, including one gadget-style fixture known to evade the denylist scan | Tampered weights (hash mismatch), denylist pickle fixtures with inert payload, metadata lies | Known by construction |
| Clean controls | ≥ 24 seeds | Reference-good models | Known by construction |

### Defect catalogue (dose-controlled)

| Dimension | Defect | Dose knob |
| --------- | ------ | --------- |
| Fairness | Label-noise / spurious-correlation injection tied to a group | flip rate 0.0–0.8 (v1 shows ≥0.4 detectable) |
| Robustness | Train without augmentation vs adversarial-augmented; add typo-sensitive tokenisation | typo budget |
| Integrity | Bit-flip in a weight shard; metadata/revision mismatch; unsafe pickle with inert marker | n bytes / presence |
| Explainability | Model relies on an artefact token (shortcut) | trigger prevalence in train data (0–90 %) and in audit data (0–50 %); multi-token trigger variant |
| Safety | Suppress recall on a severe subset | severe-recall deficit |

Multiple defects per model are allowed in a factorial subset to test interaction (does fairness evidence move when only robustness is broken?).

## Reference measurement protocol (natural models)

For each model × dimension, produce r*_d with **an independent instrument or independent data**. "Same probe code at full budget" is not a reference: it shares model-specific method error with the audit, so same-code ρ was 0.94–0.98 whatever the true validity (spike S8). Same-code runs are kept and labelled **budget consistency**.

| Dimension | Independent reference | Shares error with the audit? |
| --------- | --------------------- | ---------------------------- |
| Fairness | Subgroup AUC / BPSN-style metrics on held-out identity-*annotated* Civil Comments rows (labels, not swaps; different rows) | No |
| Robustness | Accuracy drop on a natural shifted source for the same task (another toxicity corpus; licence check in M2) | No |
| Safety | Severe-miss on a disjoint, large severe pool | Partly (same estimand): report as budget consistency, not validity |
| Integrity, Explainability | None; construct truth only | — |

- Disjoint dataset from anything the audit may use (separate source or time split); ≥ 10× the audit's sample size where the instrument is rate-based.
- Reference r*_d carries its own CI; models whose reference CI is too wide are excluded from correlation metrics and reported as such.
- Datasets and models are pinned by revision and sha256 and stored in a TrustBench manifest.

Leakage controls: the audit's datasets, seeds and the reference datasets are declared in a **pre-registration** file committed before test-model results are generated (v1 practice, keep it).

## Audit budget conditions

Evaluate the audit at several budgets (e.g. 200 / 1 000 / 5 000 rows) to produce an accuracy-vs-cost curve. This is also the data that checks the doubling rule's rounds-to-decision (spec 03, Step 4).

## Metrics reported

| Question | Metric |
| -------- | ------ |
| Does the audit rank models like the reference does? | Spearman ρ and Kendall τ per dimension, with bootstrap CI over models |
| Does it find defective models? | AUROC, precision/recall at the profile's tolerance; false-adopt rate |
| Is the uncertainty honest? | Coverage of 90% credible intervals; reliability diagram of P(violation) |
| Is the decision good? | Mean realised loss vs (a) v1 fixed thresholds, (b) always-adopt, (c) always-reject, (d) oracle using r* |
| Does abstention help? | Loss and accuracy on decided cases vs on all cases; share of COLLECT_MORE; share resolved within 2 doublings outside the indifference zone |
| Are dimensions independent? | Cross-dimension leakage matrix (defect in X moving evidence in Y) |
| Is it robust to the profile? | Decisions' stability under ±50% perturbation of each stake |

Negative or mixed results are reported as such.

## Human panel (secondary)

- ≥ 5 independent reviewers, each rating a stratified subset blind to audit output and to each other; independent accounts (v1's single shared code is the thing to avoid).
- Report Krippendorff's α; compare the Bayes action with panel majority; never used to tune anything on the test split.

## Deliverables

- `trustbench/` package: manifest schema, model/dataset registry, defect generators, reference runner, scorer.
- `trustbench/manifest.jsonl` + pre-registration markdown per release.
- A command `make trustbench-score` that regenerates every table in the paper from stored evidence.
- A public-release plan (licence check per dataset/model; omit what cannot be redistributed and ship scripts instead).

## Threats to validity (must appear in the write-up)

- Reference measurement is itself a model of truth; mitigated by independent data and its CI, not eliminated.
- Injected defects are synthetic; natural models test whether results transfer.
- Small N at the model level; report intervals and use exact/permutation tests.
- Task and language coverage bounds the claim (spec 05).
