# 04 — TrustBench: operational ground truth

## Position

There is no absolute ground truth for "trustworthy". v2 therefore defines trust *operationally* in two complementary ways and validates the audit against both:

1. **Construct validity — injected defects.** Models with a defect of known type and dose, so the correct answer is known by construction.
2. **Criterion validity — exhaustive reference measurement.** For natural models, an expensive evaluation (large, independent, held-out and shifted data; full probe budgets) produces the reference risk r*_d. The cheap audit is judged on how well it predicts that reference.

Human expert ratings are collected as a *secondary* signal with inter-rater agreement reported; they are not treated as truth (v1 found reviewer independence unresolved).

## Corpus

Target ≥ 60 models, split **by model** (never by row) into dev (≈50%, used to fit the spec 03 links), validation (≈20%, tuning) and test (≈30%, touched once).

| Stratum | Count | Source | Truth type |
| ------- | ----- | ------ | ---------- |
| Controlled-defect models | ≥ 24 | Train from a clean base with dosed defects (extend v1 `flawed_model_suite`, `scripts/train_flawed_suite.py`) | Known by construction |
| Natural Hub models, same task | ≥ 24 | Public classifiers per task (spec 05) | Exhaustive reference |
| Adversarial/tampered artefacts | ≥ 6 | Tampered weights (hash mismatch), pickle with benign canary payload, metadata lies | Known by construction |
| Clean controls | ≥ 6 | Reference-good models | Known by construction |

### Defect catalogue (dose-controlled)

| Dimension | Defect | Dose knob |
| --------- | ------ | --------- |
| Fairness | Label-noise / spurious-correlation injection tied to a group | flip rate 0.0–0.8 (v1 shows ≥0.4 detectable) |
| Robustness | Train without augmentation vs adversarial-augmented; add typo-sensitive tokenisation | typo budget |
| Integrity | Bit-flip in a weight shard; metadata/revision mismatch; unsafe pickle with inert marker | n bytes / presence |
| Explainability | Model keying on an artefact token (shortcut) so attributions are unfaithful | shortcut strength |
| Safety | Suppress recall on a severe subset | severe-recall deficit |

Multiple defects per model are allowed in a factorial subset to test interaction (does fairness evidence move when only robustness is broken?).

## Reference measurement protocol (natural models)

For each model × dimension, produce r*_d with **independent data and larger budgets than the audit**:

- Disjoint dataset from anything the audit may use (separate source or time split).
- ≥ 10× the audit's sample size; stratified; identity-sliced for fairness; shifted domains for robustness.
- Same probe code at full budget, plus the extra probes the audit may skip (e.g. all perturbation families).
- Reference r*_d carries its own CI; models whose reference CI is too wide are excluded from correlation metrics and reported as such.
- Datasets and models are pinned by revision and sha256 and stored in a TrustBench manifest.

Leakage controls: the audit's datasets, seeds and the reference datasets are declared in a **pre-registration** file committed before test-model results are generated (v1 practice, keep it).

## Audit budget conditions

Evaluate the audit at several budgets (e.g. 200 / 1 000 / 5 000 rows) to produce an accuracy-vs-cost curve. This is also the data that validates the VOI simulator (spec 03, Step 4).

## Metrics reported

| Question | Metric |
| -------- | ------ |
| Does the audit rank models like the reference does? | Spearman ρ and Kendall τ per dimension, with bootstrap CI over models |
| Does it find defective models? | AUROC, precision/recall at the profile's tolerance; false-adopt rate |
| Is the uncertainty honest? | Coverage of 90% credible intervals; reliability diagram of P(violation) |
| Is the decision good? | Mean realised loss vs (a) v1 fixed thresholds, (b) always-adopt, (c) always-reject, (d) oracle using r* |
| Does abstention help? | Loss and accuracy on decided cases vs on all cases; share of COLLECT_MORE; success of VOI plans |
| Are dimensions independent? | Cross-dimension leakage matrix (defect in X moving evidence in Y) |
| Is it robust to the profile? | Decisions' stability under ±50% perturbation of each stake |

Negative or mixed results are reported as such.

## Human panel (secondary)

- ≥ 5 independent reviewers, each rating a stratified subset blind to audit output and to each other; independent accounts (v1's single shared code is the thing to avoid).
- Report Krippendorff's α; compare the Bayes action with panel majority; never used to tune links on the test split.

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
