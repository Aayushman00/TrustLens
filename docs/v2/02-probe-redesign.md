# 02 — Probe redesign

## Principle

A probe MUST measure the property its dimension name promises, or the dimension MUST be renamed. v1 violates this for Explainability (documentation coverage) and the card half of Safety. v2 splits each dimension into **property probes** (measure the model) and **disclosure probes** (audit documentation). Disclosure never counts as evidence of a property (carries over v1's "disclosure gap ≠ observed problem").

## Common evidence contract (all probes)

Every probe emits one or more `EvidenceItem`s:

```
EvidenceItem {
  id:            "<dimension>.<probe>.<statistic>"     # stable
  kind:          "property" | "disclosure"
  estimate:      float                                  # the statistic
  unit:          "rate" | "difference" | "ratio" | "count" | "bool"
  uncertainty:   { method: "bootstrap"|"wilson"|"exact"|"none", draws?: [float] (≤1000), ci95: [lo, hi] }
  n:             int                                    # effective sample size
  direction:     "higher_is_worse" | "higher_is_better"
  applicability: "applicable" | "not_applicable(reason)" | "insufficient_evidence(reason)"
  inputs:        { model_ref@revision, dataset_sha256, config, seed, methodology_version }
  evidence_ref:  sha256 of stored raw outputs
}
```

Rules: no estimate without `n` and `uncertainty`; `not_applicable` and `insufficient_evidence` are distinct and never coerced to a number; `draws` are stored so spec 03 can propagate uncertainty exactly instead of re-deriving it from a CI.

## Per-dimension redesign

### Fairness

| Probe | Technique | Needs | Replaces |
| ----- | --------- | ----- | -------- |
| `fair.group_gap` | Equal-opportunity and FPR gap with bootstrap draws; add *worst-group* TPR and the ratio form | labelled data + group column | `F-FAIR-EOPP` (keep as subset) |
| `fair.counterfactual` | Swap identity terms in text (template + lexicon sets, e.g. gender/religion/race/orientation); measure prediction flip rate and mean score shift on otherwise identical inputs | text model only; **no group labels** | new |
| `fair.intersectional` | Slice by pairs of attributes where support ≥ n_min; report worst slice with multiplicity-corrected CI | group columns | new |
| `fair.calibration_by_group` | Per-group ECE / reliability gap | probabilities | new |

The counterfactual probe is the key reliability gain: it works on any text classifier without a labelled demographic dataset. Positive-class confirmation is mandatory (fixes K7).

### Robustness

| Probe | Technique |
| ----- | --------- |
| `rob.typo` | v1 char-swap kept as baseline (paired bootstrap drop) |
| `rob.paraphrase` | Back-translation with a local MT pair or a local seq2seq paraphraser (no hosted LLM), semantic-similarity filter via a local sentence encoder; flip rate among accepted paraphrases. Instrument models are pinned by hash and outputs cached |
| `rob.format` | Case, punctuation, whitespace, emoji and unicode-normalisation invariances |
| `rob.shift` | Accuracy on a shifted-domain split when the user supplies one; otherwise skip (never invent a shift) |
| `rob.calibration` | ECE and Brier on clean vs perturbed data; confidence under perturbation |

Report each perturbation family separately plus a worst-family value; do not average away a failing family.

### Integrity

Keep sha256 artefact verification (ADR 0013). Add:

| Probe | Technique |
| ----- | --------- |
| `int.format_safety` | Prefer `safetensors`; scan pickle-based files (`.bin`, `.pt`) for dangerous opcodes (GLOBAL/REDUCE to non-allowlisted callables) without executing |
| `int.remote_code` | Detect `trust_remote_code`/custom modelling files; flag, never execute |
| `int.provenance` | Revision pinned, commit exists, licence declared and compatible with stated use, base-model lineage consistent with config |
| `int.behavioural_fingerprint` | Optional: hash of outputs on a fixed canary set, to detect a swapped model behind an unchanged name |

Hash mismatch against an authoritative reference and dangerous-opcode findings are **Tier A hard-fail evidence**: spec 03 maps them to `REJECT` and ADR 0014 makes that non-overridable. Missing references or unscannable files are **Tier B**: unverifiable, never a hard fail.

### Explainability

Rename the card checks to `disclosure` and add real property probes (text models, token attribution):

| Probe | Technique |
| ----- | --------- |
| `exp.faithfulness` | Deletion/insertion curves (AOPC): remove top-k attributed tokens, measure drop in predicted-class probability, vs random-token baseline with CI |
| `exp.stability` | Attribution rank correlation under meaning-preserving perturbations |
| `exp.sanity` | Attribution should change when model weights are randomised (Adebayo-style sanity check) |
| `exp.disclosure` | v1 card coverage, now `kind: disclosure` |

Attribution method is pluggable (occlusion by default as it is model-agnostic; integrated gradients/SHAP when available). v1 plans for SHAP/LIME already exist in `archive/v1/docs/superpowers/` and should be mined, not redone.

### Safety

| Probe | Technique |
| ----- | --------- |
| `safe.severe_miss` | v1 severe false-negative rate with Wilson CI, kept |
| `safe.selective` | Risk–coverage curve: does confidence let the model abstain on its errors (AURC) |
| `safe.evasion` | Targeted toxicity-evasion transforms (obfuscation, leetspeak, spacing): miss rate on harmful rows |
| `safe.disclosure` | v1 safety checklist, `kind: disclosure` |

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
