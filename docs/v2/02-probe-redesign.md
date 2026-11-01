# 02 — Probe redesign

## Principle

A probe MUST measure the property its dimension name promises, or the dimension MUST be renamed. v1 violates this for Explainability (documentation coverage) and the card half of Safety. v2 splits each dimension into **property probes** (measure the model) and **disclosure probes** (audit documentation). Disclosure never counts as evidence of a property (carries over v1's "disclosure gap ≠ observed problem").

## Common evidence contract (all probes)

Every probe emits one or more `EvidenceItem`s:

```
EvidenceItem {
  id:            "<dimension>.<probe>.<statistic>"     # stable
  kind:          "property" | "disclosure"
  estimand:      { name, scale: "rate"|"difference"|"bool"|"count",
                   direction: "higher_is_worse"|"higher_is_better",
                   reference: "pooled"|"<group>"|null }               # signed, never max-min
  estimate:      float
  n:             int                                    # effective sample size
  counts:        { k: int, n: int } | null              # REQUIRED for rate estimands -> exact posterior
  uncertainty:   { method: "jeffreys"|"wilson"|"newcombe"|"paired_bootstrap"|"exact"|"none",
                   level: float, interval: [lo, hi], draws?: [float] (<=1000, continuous only) }
  look:          { index: int, max_looks: int, alpha_spent: float }      # follow-up rounds
  applicability: "applicable" | "not_applicable(reason)" | "insufficient_evidence(reason)"
  tier:          "A" | "B" | null                       # integrity only; A list closed by ADR 0014
  inputs:        { model_ref@revision, dataset_sha256, config, seed, methodology_version,
                   instrument_hashes: {lexicon, perturbation_pack, attribution_method} }
  evidence_ref:  sha256 of stored raw outputs (predictions rounded to 4 dp on the GPU path)
}
```

Rules: no estimate without `n` and `uncertainty`; `not_applicable` and `insufficient_evidence` are distinct and never coerced to a number. Rate estimands carry `counts` so spec 03 uses the exact Beta posterior; `draws` are stored for continuous statistics only (paired bootstrap, n ≥ 50). Percentile bootstrap and Wald are not allowed for rates: coverage 0.39 at n = 10, p = 0.05 (spike S3-A, [`spikes/RESULTS.md`](spikes/RESULTS.md)). Changes from the first draft of this spec: `counts`, `estimand.reference`, `look`, `tier`, `instrument_hashes` (DESIGN_SYNTHESIS 5.1).

## Per-dimension redesign

### Fairness

| Probe | Technique | Needs | Replaces |
| ----- | --------- | ----- | -------- |
| `fair.counterfactual` (**primary**, text) | Swap identity adjectives in **real benign sentences** containing exactly one lexicon term. Statistics: identity-mention gap (mean P(toxic) identity − neutral adjective) with paired bootstrap over base sentences; any-swap decision flip rate (Jeffreys on counts); per-term deviation. Templates are dropped: 16 templates gave a between-identity spread of 0.65 on a clean model (S4) | text model only; **no group labels** | new |
| `fair.group_signed` | **Signed** per-group TPR/FPR gap against the pooled rate, Newcombe or Beta-difference interval. Shown beside the counterfactual probe whenever group labels exist | labelled data + group column | `F-FAIR-EOPP` max − min (retired for decisions) |
| `fair.intersectional` | Slices by attribute pairs where support ≥ n_min; reported only with a Bonferroni upper bound | group columns | new |
| `fair.calibration_by_group` | Per-group ECE / reliability gap | probabilities | new |

Why the change (spikes S3-C, S4): the v1 max − min gap is biased upward by noise alone. A perfectly fair model with 4 groups gets a "gap" of 0.07–0.23 and a bootstrap CI that excludes zero every time (0 % coverage). The counterfactual probe ranks the defect-dose sweep perfectly (mention gap 0.016 clean → 0.067 v1 V1 → 0.261 at dose 1.0), separates v1's V1 model from the clean one with non-overlapping CIs where v1's equal-opportunity gap could not (0.164 vs 0.174), reads exactly 0 on a masked-identity null, and costs about 3 s per model. A per-term bias is detected from δ = 1 logit upward; δ = 0.5 is borderline at n = 76 sentences, so TrustBench reports minimum detectable dose against n. Caveat: the clean model is not bias-free (0.016, CI excludes 0), a real property of Civil Comments training. Positive-class confirmation is mandatory (fixes K7). The probe does not apply to tabular models, where `fair.group_signed` is used.

### Robustness

| Probe | Technique |
| ----- | --------- |
| `rob.invariance` (**primary**) | Label-free prediction flip rate per perturbation family (typo, case, punctuation, whitespace, emoji, unicode normalisation); Jeffreys on flip counts. Needs no labels |
| `rob.accuracy_drop` | v1 char-swap accuracy drop, paired bootstrap, kept when labels exist (it detected the overfit V2 in v1) |
| `rob.shift` | Accuracy on a shifted-domain split when the user supplies one; otherwise skip (never invent a shift). Also the independent reference for natural models (spec 04) |
| `rob.calibration` | ECE and Brier on clean vs perturbed data; confidence under perturbation |
| `rob.paraphrase` | **Cut-line 1** (not in the core build): back-translation with a local MT pair, similarity filter, pinned by hash and cached. Costs an extra model and about 1–2 h generation per pack (ASSUMPTION) |

Report each perturbation family separately plus a worst-family value; do not average away a failing family. When two families share rows, combine by taking the worst family, never by averaging.

### Integrity

Keep sha256 artefact verification (ADR 0013). Add:

| Probe | Technique |
| ----- | --------- |
| `int.format_safety` | Prefer `safetensors`; scan pickle-based files (`.bin`, `.pt`) with stdlib `pickletools.genops` (never unpickles; STACK_GLOBAL resolved through the memo; torch zip archives scanned per `.pkl` member). Callable on the closed versioned denylist (`integrity/denylist-v1`) → **Tier A**; callable on the torch-checkpoint allowlist → clean; anything else → **Tier B** (unknown). Spike S7: 11 real Hub `pytorch_model.bin` files (17–476 MB) gave 0 false Tier A; 2 real `training_args.bin` files reference `transformers.training_args.TrainingArguments` and `__main__` classes and must be Tier B; 2.15 GB scanned in 3.9 s. The real-file sample is small (13): extend it to a few hundred in M0 before freezing the allowlist. Known ceiling: allowed-callable gadget chains evade a denylist, so TrustBench includes one such fixture and the report states it |
| `int.remote_code` | Detect `trust_remote_code`/custom modelling files; flag, never execute |
| `int.provenance` | Revision pinned, commit exists, licence declared and compatible with stated use, base-model lineage consistent with config |
| `int.behavioural_fingerprint` | Optional: hash of outputs on a fixed canary set, to detect a swapped model behind an unchanged name |

Hash mismatch against an authoritative reference and a denylist hit are **Tier A hard-fail evidence**: spec 03 maps them to `REJECT` and ADR 0014 makes that non-overridable. Missing references, unscannable files and unknown callables are **Tier B**: unverifiable, ordinary evidence, never a hard fail.

### Explainability (reports call it "Shortcut reliance and explanation")

Spike S5 changed this section. AOPC measures whether the *attribution method* is faithful to the model, not whether the *model* is trustworthy. On a model trained with a planted trigger token (`zephyrine` in 90 % of positive rows), AOPC top-5 − random read 0.281 against 0.330 for the clean model on natural audit data, and 0.441 vs 0.332 when the audit data carried the trigger: the sign flips with the audit data. A shortcut model is still faithfully explained by occlusion. Global attribution ranking surfaced the trigger at rank 1 (mean |attr| 0.69, next 0.12) against rank 55 for the clean model, and inserting it into negative rows flipped 100 % of predictions against 1.1 %.

| Probe | Technique |
| ----- | --------- |
| `exp.shortcut` (**primary**) | Discover candidate tokens by global occlusion attribution over the audit rows, then confirm causally by insertion into rows of the other class and deletion; flip rates with Jeffreys on counts. About 5 s per 1 000 short rows (S5); long Civil Comments rows ≈ ×10 (ASSUMPTION) |
| `exp.disclosure` | v1 card coverage, now `kind: disclosure` |
| *method card* | AOPC faithfulness and Adebayo-style randomisation sanity check describe the attribution instrument, not the model. They are recorded in the method card, not scored as model evidence. `exp.stability` is deferred |

Limits: discovery needs the artefact in the audit data, so TrustBench varies trigger prevalence in audit data (0–50 %) and reports detection against prevalence. Multi-token or semantic shortcuts are missed by single-word occlusion. Attribution method stays pluggable (occlusion by default as it is model-agnostic). v1 plans for SHAP/LIME in `archive/v1/docs/superpowers/` should be mined, not redone.

### Safety

| Probe | Technique |
| ----- | --------- |
| `safe.severe_miss` | v1 severe false-negative rate, kept; emits counts, interval Jeffreys or Wilson (Wilson covers 0.92–0.97 at n = 10–100, S3-A) |
| `safe.evasion` | Targeted toxicity-evasion transforms (obfuscation, leetspeak, spacing): miss rate on harmful rows, counts → Jeffreys |
| `safe.selective` | Risk–coverage curve (AURC), bootstrap. Runner-up: wins for profiles whose control is "abstain and route to human" |
| `safe.disclosure` | v1 safety checklist, `kind: disclosure` |

The v1 severe subset is 282 rows, so the interval stays wide and the doubling rule (spec 03 step 4) needs a larger severe pool. Ship a bigger severe pack (ASSUMPTION: Civil Comments `severe_toxicity`).

## Replacing the confidence engine

v1's `confidence/engine.py` factors are removed as a *score*. What survives is the information they encode, made explicit and principled:

- sample sufficiency → `n` and CI width on each `EvidenceItem`;
- probe ran / skipped → `applicability`;
- evidence present → the hashed `evidence_ref`.

Confidence is then a *consequence* of the posterior (spec 03), not a hand-set number.

## Acceptance (per probe)

- Pure-function core with unit tests; property tests for monotonicity and invariances (e.g. relabelling groups does not change a symmetric statistic).
- Known-answer test on a synthetic model with a planted defect of known magnitude.
- Seed-to-seed variance reported (K8).
- Runs on CPU in a documented time budget (default ≤ 10 min per model on the reference dataset sizes) and records device.
