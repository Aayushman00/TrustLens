# TrustLens Methodology v1.0 — Fairness & Robustness

**Status:** Authoritative specification (normative)  
**Version:** `tl-methodology-v1.0`  
**Revision:** folded pre-implementation amendments A1–A10 (`docs/TRUSTLENS_METHODOLOGY_V1_0_AMENDMENTS.md`)  
**Scope:** Fairness and Robustness probes for **classification** and **regression** models  
**Supersedes:** MVP heuristic probe behavior (Phase 11–12 implementations and HeuristicOSDAgent bands)  
**Does not cover:** Integrity, Explainability, Safety (separate methodology documents), FRIES2, attack-simulation Phases 20–21  
**Implementation:** This document is **specification only**. No code change is implied by its publication.

This revision **replaces** conflicting rules. Retired identifiers must not appear in implementations: `F-FAIR-REP`, `FR-REP-01`, `slice_penalty_O`, scored `F-FAIR-CAL`, binary F1 as `F-FAIR-PERF`, `R-ROB-CLEAN`, `R-ROB-GAP`, `RR-CLEAN-01`, `RR-GAP-01`, `conservative_penalty`.

---

## Table of contents

1. [Purpose and principles](#1-purpose-and-principles)
2. [Supersession and critique of legacy MVP](#2-supersession-and-critique-of-legacy-mvp)
3. [Definitions and conventions](#3-definitions-and-conventions)
4. [Model applicability taxonomy](#4-model-applicability-taxonomy)
5. [Common evaluation architecture](#5-common-evaluation-architecture)
6. [Fairness methodology](#6-fairness-methodology)
7. [Robustness methodology](#7-robustness-methodology)
8. [Confidence model (Fairness & Robustness)](#8-confidence-model-fairness--robustness)
9. [Worked examples](#9-worked-examples)
10. [Known limitations and non-claims](#10-known-limitations-and-non-claims)
11. [Acceptance criteria (implementation gate)](#11-acceptance-criteria-implementation-gate)
12. [Appendices](#12-appendices)

---

## 1. Purpose and principles

### 1.1 Purpose

TrustLens Methodology v1.0 defines **how measured evidence** about model behavior on pinned evaluation data is:

1. Collected from the **imported model under test** (not a substitute predictor).
2. Assessed for **statistical reliability**.
3. Mapped to **at most one scored FRIES risk** within each of the Fairness and Robustness aspects (additional metrics stay at Layer A).
4. Converted to a **proposed Occurrence (O)** rating. Severity (S) and Detection (D) are **not** inferred from those metrics in v1.0.

This document is the contract between **science** (what can be claimed) and **engineering** (what probes must emit).

### 1.2 Core principles

| Principle | Requirement |
| --------- | ----------- |
| **Model-faithful** | Fairness and Robustness metrics must use predictions from the evaluated `model_ref` at pinned `revision`, except when explicitly running the deprecated **PROXY** path (§6.8). PROXY never enters FRIES. |
| **Task-aligned data** | Evaluation datasets must match the model’s declared task and label space (§4, §6.3, §7.3). |
| **Evidence ≠ score** | Disparity gaps and accuracy drops are evidence. O is a separate, labeled **PROPOSED** judgment. S and D are not copied from the evidence scalar. |
| **Abstain over fabricate** | If minimum evidence or reliability gates fail, or mapping is blocked (`wide_ci`, uninformative robustness, domain-mismatch override without human accept), probes **must not** emit numeric O/S/D mappings. |
| **No double-counting** | At most one scored risk per aspect. Related metrics may be stored as evidence; they must not each produce a FRIES `Pi` that is then averaged. |
| **Uncertainty explicit** | Point estimates alone are insufficient; confidence intervals and reliability flags are mandatory. Practical-significance triggers use `ci_lower > ε`, not `ci_lower > 0`. |
| **Traceability** | Every O proposal must cite `rule_id`, `methodology_version`, inputs, and thresholds (§6.10, §7.10). S and D traces must cite `unvalidated_default` or be null. |

### 1.3 Relationship to FRIES scoring

- **Layer A (evidence):** probe metrics + CIs + statuses (this document).
- **Layer B (risk assessment):** evidence → at most one scored risk → proposed **O**; S/D per §3.5 (this document).
- **Layer C (FRIES score):** for each **scored** risk, `Pi = ∛(O×S×D)` (veto if any component is 0; optimal if all are 10). Aspect score `Ti` is that `Pi` when exactly one risk is scored. Weight floor and `cbrt` math remain `fries-original-v1`.

**Empty-risk and incomplete-evidence policy (normative, A6):**

| Aspect state | `Ti` | Overall `T` |
| ------------ | ---- | ----------- |
| Evidence-incomplete (`INSUFFICIENT_EVIDENCE`, `NOT_APPLICABLE`, `FAILED`, `SKIPPED`, `PROXY` for that aspect) | **omit** (not 0) | Reweight `T` over remaining **evidence-complete aspects that have a numeric `Ti`**. Do not mark this aspect as `no_material_risk`. |
| `EVALUATED` + `aspect_scoring: mapping_blocked` | **omit** (not 0) | Same reweight. Status stays `EVALUATED`; report mapping-blocked, not “no risk.” |
| `EVALUATED` + `aspect_scoring: no_material_risk` | **omit** (not 0) | Same reweight. Aspect is **evidence-complete**. Must **not** use the withhold/incomplete-evidence path. Must **not** set `Ti = 0`. Do **not** invent O=9/10. |
| `EVALUATED` + one scored risk with complete O/S/D (human or Autonomous defaults) | `Pi` | Include in `T` with renormalized weights over numeric-`Ti` aspects |

Renormalized weights must still satisfy each `ωi ≥ 0.1` and `Σωi = 1`. If renormalization cannot satisfy the floor, **withhold overall `T`** (evaluation may still be evidence-complete for the evaluated aspects).

Layer C arithmetic for a *present* risk is unchanged. Treating “no selected risk” as `Ti = 0` is **forbidden**.

---

## 2. Supersession and critique of legacy MVP

The repository’s current MVP (Phase 11–12 probes + HeuristicOSDAgent) is **not** scientifically adequate as a fairness or robustness audit. Methodology v1.0 **replaces** the following practices.

| Legacy MVP practice | Scientific weakness | v1.0 requirement |
| ------------------- | ------------------- | ---------------- |
| Fairness uses sklearn `LogisticRegression` on Adult Census for **any** imported HF model | Measures proxy disparity, not the artifact under audit | **MODEL_FAITHFUL** path only for normative evaluation; `proxy_lr` is `PROXY`, metrics-only, no FRIES (§6.8) |
| Fairness dataset (Adult) unrelated to NLP/vision model tasks | No construct validity | Task-aligned dataset; NLP fairness is `NOT_APPLICABLE` until a corpus with `A` is pinned (§6.3) |
| `min_group_n = 30` with `n_samples ≤ 256` | Unstable disparity estimates | `n_total ≥ 200`, `min_group_n ≥ 50`, bootstrap CIs (§6.6) |
| Single scalar `gap = max(DP, EO)` or three parallel FRIES risks | Collapses or **double-counts** related constructs | Layer A: compute DP, EO, F1. Layer B: **at most one** scored fairness risk (§6.9) |
| Robustness: char-swap on AG News for all text classifiers | Domain mismatch | Task-matched pin + `G-ROB-DOMAIN` (§7.3) |
| `degradation_ratio = robust/clean` with `clean ≈ 0` | Undefined or misleading | `accuracy_drop` and `relative_degradation` with ε floor **as evidence**; scored O uses the drop (§7.5, §7.10) |
| Agent maps `clean_accuracy → O`, `robust_accuracy → S`, `degradation → D`, or three robustness risks | Conflates performance, fragility, and detection | One scored risk `R-ROB-PERT`; O from drop only; S/D not from metrics (§7.2, §7.10) |
| Skip / thin-slice paths still yield numeric O/S/D | False precision | Status-driven empty `osd_proposals` (§6.7, §7.8) |
| No confidence intervals; trigger `ci_lower > 0` | Noise and sub-practical effects look like findings | Wilson + bootstrap; trigger `ci_lower > ε` (§6.9, §7.9) |
| `S = O`; D high because a probe ran | Invalid FMEA/FRIES semantics | O from one scalar; S/D null or unvalidated default 5 (§3.5, §6.10) |
| `ProbeEvaluationStatus.PROXY` unused or mapped to FRIES | Hides substitute evaluation | PROXY set; **no** O/S/D; **no** FRIES contribution |

**Normative rule:** Implementations claiming “TrustLens Methodology v1.0” compliance **must not** present legacy MVP fairness numbers as model-faithful audit results.

---

## 3. Definitions and conventions

### 3.1 Symbols

| Symbol | Meaning |
| ------ | ------- |
| `Y` | Ground-truth label |
| `Ŷ` | Model prediction |
| `A` | Sensitive / protected attribute (single attribute per v1.0 run; intersectional analysis out of scope) |
| `n` | Total evaluated samples after filtering |
| `n_g` | Samples in group `g` |
| `π_g` | `P(Ŷ=1 \| A=g)` (binary positive class) |
| `TPR_g`, `FPR_g` | True/false positive rate within group `g` (binary) |
| `ε` | Uncalibrated practical-significance floor for metrics in [0, 1]: **0.02** |
| `ε_drop` | Uncalibrated practical-significance floor for classification accuracy drop: **0.05** |

### 3.2 Task types (`task_type`)

| `task_type` | Hub signals (any of) | Label `Y` | Prediction `Ŷ` |
| ----------- | -------------------- | --------- | -------------- |
| `binary_classification` | `text-classification`, `sentiment-analysis`, binary head | `{0,1}` | class index or probability thresholded at 0.5 |
| `multiclass_classification` | `text-classification`, `image-classification`, `n>2` labels | `{0,…,K-1}` | argmax class |
| `regression` | `regression`, continuous head | `ℝ` | continuous point prediction |

**v1.0 scope:** `binary_classification`, `multiclass_classification`, `regression` with **tabular** or **text** modality. Image and audio robustness are `NOT_APPLICABLE` in v1.0 (§7.2). Tabular **regression** Fairness and Robustness remain `NOT_APPLICABLE` until a dataset with a declared real-valued target and `mae_floor` is pinned (§6.3.1, §7.3.1).

### 3.3 Sensitive attribute policy

- v1.0 evaluates **one sensitive attribute per run**, named `sensitive_attribute`.
- Attribute must be **declared** in dataset spec or probe config; must not be inferred from free text without a pinned lexicon.
- Groups with `n_g < min_group_n` are **excluded** from disparity metrics if at least two groups remain with `n_g ≥ min_group_n`. If fewer than two groups meet `min_group_n`, status is `INSUFFICIENT_EVIDENCE` (§6.5.2). No representativeness O/S/D triple is emitted.
- Pooling into `_OTHER_` is allowed **only** if `pooling_policy: pool_rare_to_OTHER` is declared on the dataset spec **and** the pooled group still meets `min_group_n`; otherwise do not pool.

### 3.4 Methodology versioning

| Field | Value |
| ----- | ----- |
| `methodology_version` | `tl-methodology-v1.0` |
| `fairness_mapping_version` | `tl-fairness-osd-v1.0` |
| `robustness_mapping_version` | `tl-robustness-osd-v1.0` |
| `scorer_version` | `fries-original-v1` (risk `Pi` math unchanged; empty-risk `Ti = 0` **must not** be used for `no_material_risk`) |

All evidence JSON artifacts must include `methodology_version`.

### 3.5 O/S/D convention (FRIES inverted scale)

Integers **0–10**, higher = more trustworthy:

- **O (Occurrence):** higher ⇒ the scored failure mode is **less strongly present** in the evidence. v1.0 may map O from **one** primary scalar (§6.10, §7.10). Proposals are clamped to **[1, 9]** and labeled **PROPOSED / REQUIRES VALIDATION**.
- **S (Severity):** higher ⇒ potential harm **if** the risk occurs is **less severe**. **Not mapped from probe metrics.** v1.0 agent emits `S = null` in Assisted mode (human required) or, if Autonomous must propose a complete triple, `S = 5` with `"S_source": "unvalidated_default"`. Never set `S = O`. No Safety-card or high-impact adjustment.
- **D (Detection):** higher ⇒ the risk is **easier to detect in operation**. **Not mapped from probe metrics, CI width, or attack obviousness.** Same policy as S: `null` or `5` with `"D_source": "unvalidated_default"`. Char-swap must not raise D.

**0** (veto) and **10** (optimal) are reserved for human finalization.

### 3.6 Aspect scoring labels

| `aspect_scoring` | Meaning |
| ---------------- | ------- |
| `scored_risk` | Gates passed; one risk triggered; O proposed (S/D per §3.5) |
| `no_material_risk` | Gates passed; no scored risk triggered; `osd_proposals: []`; evidence-complete |
| `mapping_blocked` | Metrics computed; mapping forbidden (`wide_ci`, `uninformative_robustness`, domain-mismatch override without human accept); `osd_proposals: []` |
| `not_scored` | Status is not `EVALUATED` (including `PROXY`) |

---

## 4. Model applicability taxonomy

Before Fairness or Robustness runs, the **Model Applicability Classifier** (MAC) assigns `applicability_class`:

| Class | Fairness v1.0 | Robustness v1.0 |
| ----- | ------------- | --------------- |
| `BINARY_TEXT_CLF` | Applicable **only if** a pinned dataset with `A` exists; otherwise `NOT_APPLICABLE` | Char-swap on a **domain-aligned** text set |
| `MULTICLASS_TEXT_CLF` | Same as binary text | Char-swap on domain-aligned text |
| `BINARY_TABULAR_CLF` | Applicable if dataset has `A` (Adult pin) | Feature noise (Gaussian) on numeric features, domain-aligned |
| `REGRESSION_TABULAR` | **NOT_APPLICABLE** until a pin with target + `mae_floor` exists | **NOT_APPLICABLE** until that pin exists |
| `REGRESSION_TEXT` | **NOT_APPLICABLE** | **NOT_APPLICABLE** |
| `IMAGE_CLF` | **NOT_APPLICABLE** | **NOT_APPLICABLE** |
| `LM_GENERATIVE` | **NOT_APPLICABLE** | **NOT_APPLICABLE** |
| `UNKNOWN_TASK` | **NOT_APPLICABLE** | **NOT_APPLICABLE** |

MAC inputs: `pipeline_tag`, `config.num_labels`, `model_type`, modality from import metadata.

**DECISION (frozen for v1.0):** Image and generative models receive `NOT_APPLICABLE` rather than weak proxy evaluations.

---

## 5. Common evaluation architecture

### 5.1 Pipeline stages

```text
1. Resolve model_ref + revision + task_type (MAC)
2. Select pinned dataset logical_key(s) from registry
3. Load stratified sample (seeded, reproducible)
4. Run InferenceBackend → Ŷ for each row
5. Filter rows (label space, missing A, tokenization failures; drop thin groups per §3.3)
6. Compute metrics + uncertainty (Layer A — including metrics that will not be scored)
7. Evaluate minimum-evidence + reliability gates → ProbeEvaluationStatus
8. Apply evidence→risk rules → at most one scored risk (or none)
9. If mapping blocked or no trigger: empty osd_proposals + aspect_scoring
   Else: map O from the single primary scalar; S/D per §3.5
10. Persist evidence artifact + mapping trace
```

### 5.2 Required evidence artifact schema (normative)

Every probe run writes JSON matching:

```json
{
  "methodology_version": "tl-methodology-v1.0",
  "probe": "fairness | robustness",
  "evaluation_id": "<uuid>",
  "model_ref": "<hf_id>",
  "model_revision": "<sha|null>",
  "task_type": "binary_classification | ...",
  "applicability_class": "BINARY_TEXT_CLF | ...",
  "dataset": {
    "logical_key": "<registry key>",
    "hf_path": "<pinned>",
    "revision": "<pinned sha>",
    "n_requested": 500,
    "n_evaluated": 437,
    "seed": 42
  },
  "status": "EVALUATED | INSUFFICIENT_EVIDENCE | NOT_APPLICABLE | FAILED | PROXY | SKIPPED",
  "status_reason": "<human-readable>",
  "aspect_scoring": "scored_risk | no_material_risk | mapping_blocked | not_scored",
  "metrics": { },
  "uncertainty": { },
  "reliability": {
    "gates_passed": true,
    "failed_gates": []
  },
  "risks_triggered": [],
  "scored_risk_id": null,
  "osd_proposals": [],
  "flags": [],
  "limitations": []
}
```

`risks_triggered` contains at most one id (the scored risk). Layer A metrics that did not win selection remain under `metrics` only.

### 5.3 Inference requirements

- Predictions must come from `InferenceBackend` loading the evaluated weights (except deprecated PROXY, §6.8).
- Batch size and device must be recorded (`device`, `batch_size`).
- For classification: if the model outputs logits, `Ŷ = argmax(logits)` unless config specifies a threshold for binary (`threshold_default = 0.5`).

---

## 6. Fairness methodology

### 6.1 Scientific objective

Fairness evidence measures **group-wise disparities** in model behavior with respect to a declared sensitive attribute `A`, on a task-aligned dataset. v1.0 does **not** assert legal compliance, causal fairness, or counterfactual fairness.

### 6.2 Risk taxonomy (Fairness aspect)

**Scored risks (Layer B — at most one per run):**

| Risk ID | Name | When it may be scored |
| ------- | ---- | --------------------- |
| `F-FAIR-EO` | Equalized odds disparity | Binary classification; EO trigger fires and `G-FAIR-EO-UNSTABLE` is false. **Preferred** over DP when both would fire. |
| `F-FAIR-DP` | Demographic parity disparity | Binary classification; DP trigger fires **and** EO was not selected. |
| `F-FAIR-PERF` | Subgroup performance disparity | **Multiclass:** `subgroup_worst_group_acc_gap` only. **Regression:** `mae_gap_absolute` only, and only when a valid pin + `mae_floor` exist. **Never** scored from binary F1. |

**Not scored (retired or evidence-only):**

| Item | Disposition |
| ---- | ----------- |
| Binary `subgroup_f1_spread` | Layer A evidence only. Must never appear in `osd_proposals`. |
| Multiclass `subgroup_macro_f1_spread` | Layer A evidence only. Do not score. |
| Calibration / ECE group difference | Layer A evidence only when probabilities exist. **No O/S/D.** |
| Thin / non-representative slices | **Not a risk.** Handled only by `G-FAIR-N-GROUP` or by excluding thin groups (§3.3). |

### 6.3 Dataset registry requirements

Each fairness dataset entry **must** declare:

```yaml
logical_key: <string>
hf_path: <pinned repo>
revision: <full git sha>
modality: tabular | text
task_type: binary_classification | multiclass_classification | regression
fairness:
  sensitive_attributes:
    - name: sex
      type: categorical
      values: [Male, Female]
      pooling_policy: none | pool_rare_to_OTHER
  label_field: label
  input_field: text | features
  min_total_n: 200
  min_group_n: 50
  stratify_on: [label, sensitive_attribute]
  mae_floor: <required if task_type is regression>
notes: <provenance>
```

#### 6.3.1 v1.0 pinned datasets (normative minimum set)

| `logical_key` | Modality | Task | Sensitive attr | Purpose |
| ------------- | -------- | ---- | -------------- | ------- |
| `adult_fairness` | tabular | binary_classification | `sex` (default), `race` (config) | Tabular binary baseline |
| `sst2_fairness_placeholder` | — | — | — | **Not a valid v1.0 pin** — SST-2 has no protected attribute; remains `NOT_APPLICABLE` until a pinned NLP fairness corpus is added |

**Critical v1.0 gap:** There is **no approved text fairness dataset** in the initial pin set. Text classification fairness is `NOT_APPLICABLE` until a dataset with declared `A` is pinned. **Do not** use Adult proxy for text models under v1.0.

**Not a v1.0 normative pin:** any Adult-derived regression target (`fnlwgt`, `hours-per-week`, or binarized income reused as continuous Y). Tabular regression Fairness is `NOT_APPLICABLE` until a dataset with a declared real-valued target and `mae_floor` is pinned (post-v1.0, Appendix C).

#### 6.3.2 Required row fields after normalization

**Tabular binary / multiclass:**

```json
{
  "features": { "<feature_name>": <value>, ... },
  "sensitive": "<value>",
  "label": <int>
}
```

**Text binary / multiclass:**

```json
{
  "text": "<string>",
  "sensitive": "<value>",
  "label": <int>
}
```

**Tabular regression (formulas only; no v1.0 pin):**

```json
{
  "features": { ... },
  "sensitive": "<value>",
  "label": <float>
}
```

Rows missing `sensitive` or `label` are dropped and counted in `n_dropped`.

### 6.4 Applicable metrics

All metrics in this subsection are **Layer A**. Only the primary scalar of the **selected** scored risk is used for O (§6.9–§6.10).

#### 6.4.1 Binary classification

| Metric key | Formula | Range | Scored? |
| ---------- | ------- | ----- | ------- |
| `demographic_parity_difference` | `max_g π_g − min_g π_g` | [0, 1] | Primary scalar **only if** `F-FAIR-DP` is selected |
| `equalized_odds_difference` | `max( max_g TPR_g − min_g TPR_g, max_g FPR_g − min_g FPR_g )` | [0, 1] | Primary scalar **only if** `F-FAIR-EO` is selected |
| `equal_opportunity_difference` | `max_g TPR_g − min_g TPR_g` | [0, 1] | Evidence only |
| `subgroup_f1_spread` | `max_g F1_g − min_g F1_g` | [0, 1] | Evidence only — **never scored** |
| `per_group` | `{g: {n, π, TPR, FPR, F1}}` | — | Evidence only |

Positive class is **1** by convention; reports must include `positive_class_label` metadata.

#### 6.4.2 Multiclass classification

| Metric key | Formula | Scored? |
| ---------- | ------- | ------- |
| `subgroup_worst_group_acc_gap` | `max_g acc_g − min_g acc_g` | Primary scalar for `F-FAIR-PERF` |
| `subgroup_macro_f1_spread` | macro-F1 per group over classes in the global eval set; max − min | Evidence only |
| `demographic_parity_difference` | Binary-only | **NOT_APPLICABLE** |

#### 6.4.3 Regression (formulas; path `NOT_APPLICABLE` until pin)

| Metric key | Formula | Scored? |
| ---------- | ------- | ------- |
| `subgroup_mae` | `MAE_g = mean(|Y − Ŷ|)` per group | Evidence |
| `mae_gap_absolute` | `max_g MAE_g − min_g MAE_g` | Primary scalar for `F-FAIR-PERF` **only if** `min_g MAE_g ≥ mae_floor` |
| `mae_ratio_max_min` | optional diagnostic | **Must not trigger scoring** |
| `subgroup_rmse_spread` | `max_g RMSE_g − min_g RMSE_g` | Evidence only |

`mae_floor` default, when a pin exists: **1% of the IQR of `|Y|`** on the evaluated sample (not `1e-6`).

#### 6.4.4 Calibration (optional binary, evidence only)

When `predict_proba` is available, compute `ece_group_diff` (10 equal-width bins on [0, 1]) and `per_group_ece`. Store in `metrics`. **Do not trigger a scored risk. Do not emit O/S/D from ECE.** Per-group ECE at v1.0 sample sizes is too noisy to support FRIES mapping.

### 6.5 Statistical reliability and uncertainty

#### 6.5.1 Estimators

| Quantity | Method | Parameters |
| -------- | ------ | ---------- |
| `π_g`, `acc`, `TPR`, `FPR` | Wilson score interval | 95% (`z=1.96`) |
| `F1_g` | Bootstrap percentile CI | `B=1000`, seed=`seed+1`, stratified by `A` |
| `demographic_parity_difference`, `equalized_odds_difference`, spreads, `mae_gap_absolute` | Bootstrap percentile CI on the metric | `B=1000`, resample rows with replacement |
| `MAE_g` | Bootstrap percentile CI | `B=1000` |

#### 6.5.2 Reliability gates

Emit `reliability.failed_gates` when any gate fails:

| Gate ID | Condition | Consequence |
| ------- | --------- | ----------- |
| `G-FAIR-N-TOTAL` | `n_evaluated < min_total_n` (200) | `INSUFFICIENT_EVIDENCE`; `aspect_scoring: not_scored`; no O/S/D |
| `G-FAIR-N-GROUP` | fewer than 2 groups with `n_g ≥ min_group_n` (50) | `INSUFFICIENT_EVIDENCE`; `aspect_scoring: not_scored`; no O/S/D; **no extra risk triple** |
| `G-FAIR-CI-WIDE` | For the **candidate primary** disparity metric, `CI_upper − CI_lower > 0.15` | Status **`EVALUATED`**; flag `wide_ci`; `aspect_scoring: mapping_blocked`; **empty `osd_proposals`** (no numeric nudge) |
| `G-FAIR-EO-UNSTABLE` | Any compared group with `< 10` positives or `< 10` negatives | Omit EO from selection; flag `eo_unstable`; may still select DP if DP triggers |
| `G-FAIR-LABEL-IMBALANCE` | Global positive rate `< 0.02` or `> 0.98` | Flag `extreme_base_rate`; DP interpretation limited (limitation text required if DP is selected) |

**Rationale:** MVP `n=256` with `min_group_n=30` produces CIs often too wide for audit claims.

#### 6.5.3 Uncertainty output shape

```json
"uncertainty": {
  "demographic_parity_difference": {"point": 0.08, "ci_lower": 0.03, "ci_upper": 0.13, "method": "bootstrap_percentile", "B": 1000},
  "equalized_odds_difference": { }
}
```

### 6.6 Minimum evidence

| Requirement | Value | Notes |
| ----------- | ----- | ----- |
| `min_total_n` | **200** evaluated rows | After label/A filtering |
| `min_group_n` | **50** per **compared** group | Thin groups excluded first (§3.3) |
| Groups compared | ≥ **2** | Both meeting `min_group_n` |
| `seed` | Fixed per evaluation | Record in artifact |
| Model predictions | **100%** from evaluated model | Else `FAILED` (PROXY excepted, §6.8) |

### 6.7 Abstention and status rules

| Status | When | `osd_proposals` |
| ------ | ---- | ---------------- |
| `EVALUATED` | Mandatory gates `G-FAIR-N-TOTAL` and `G-FAIR-N-GROUP` passed; metrics computed | Empty unless `aspect_scoring: scored_risk` |
| `INSUFFICIENT_EVIDENCE` | `G-FAIR-N-TOTAL` or `G-FAIR-N-GROUP`; or zero rows after filter | Empty |
| `NOT_APPLICABLE` | MAC class not fairness-applicable; no pinned dataset for task; text clf without fairness corpus; tabular regression without pin | Empty |
| `FAILED` | Model load, inference exception, dataset load failure | Empty |
| `PROXY` | Deprecated proxy path (§6.8) | **Empty** (metrics allowed) |
| `SKIPPED` | Config `skip_fairness: true` | Empty |

If status ∈ `{INSUFFICIENT_EVIDENCE, NOT_APPLICABLE, FAILED, SKIPPED, PROXY}`, `aspect_scoring` is `not_scored`.

`G-FAIR-CI-WIDE` does **not** change status to `INSUFFICIENT_EVIDENCE`; it sets `mapping_blocked`.

### 6.8 Deprecated PROXY path (legacy compatibility only)

For reproduction of Phase 25 experiments only:

- Config: `fairness.mode: proxy_lr` + `dataset: adult_fairness`
- Status: **`PROXY`** (never `EVALUATED`)
- Limitation string required: `"Predictions from sklearn LogisticRegression on tabular features — not the imported model"`
- Layer A metrics may be stored
- `osd_proposals` **must be empty**
- **Must not** contribute to Autonomous `final_scores` / FRIES
- **Must not** participate in leaderboard comparisons against MODEL_FAITHFUL runs

**v1.0 normative audits forbid PROXY** unless the report section is titled “Legacy proxy reproduction.”

### 6.9 Evidence → scored-risk rules

Let `ε = 0.02` (uncalibrated practical floor for metrics in [0, 1]).

A binary disparity **candidate** fires only if:

```text
point > ε AND ci_lower > ε
```

Do **not** use `ci_lower > 0`.

| Candidate | Task | Condition |
| --------- | ---- | --------- |
| EO candidate | binary_classification | `equalized_odds_difference` satisfies the trigger **and** not `eo_unstable` |
| DP candidate | binary_classification | `demographic_parity_difference` satisfies the trigger |
| PERF (multiclass) | multiclass_classification | `subgroup_worst_group_acc_gap` satisfies the trigger (`ε = 0.02`) |
| PERF (regression) | regression (pinned only) | `min_g MAE_g ≥ mae_floor` **and** `mae_gap_absolute > mae_floor` **and** `ci_lower > mae_floor` |

**Selection (exactly zero or one scored risk):**

1. Binary: if EO candidate fires → score **`F-FAIR-EO`**. Else if DP candidate fires → score **`F-FAIR-DP`**. Else no scored risk.
2. Multiclass: if PERF candidate fires → score **`F-FAIR-PERF`**. Else no scored risk.
3. Binary F1, macro-F1, ECE, MAE ratio: **never** selected.

If gates pass and no scored risk is selected: `risks_triggered: []`, `scored_risk_id: null`, `aspect_scoring: no_material_risk`, `osd_proposals: []`. Interpretation: “no scored disparity above the practical floor at 95% CI,” **not** “could not evaluate.”

If `wide_ci` on the candidate that would have been selected (or on the only candidate family in play): `aspect_scoring: mapping_blocked` even if the point estimate exceeds `ε`. Do not fall through to the other binary metric to “rescue” a triple when the preferred metric is wide-CI; if EO is preferred but wide-CI, **block** (do not silently score DP instead). If EO is unstable (not wide-CI) and DP is valid and not wide-CI, scoring DP is allowed.

### 6.10 Risk → O mapping (`tl-fairness-osd-v1.0`)

Mapping of **O** is **PROPOSED / REQUIRES VALIDATION**. Clamp O to **[1, 9]**. Emit **at most one** proposal.

```text
scale_linear(x, x_low, x_high) = clamp(round(10 * (1 - (x - x_low)/(x_high - x_low))), 1, 9)
# x_low → 9 (best), x_high → 1 (worst)
```

| rule_id | Scored risk | O | S | D | Primary scalar |
| ------- | ----------- | - | - | - | -------------- |
| `FR-EO-01` | `F-FAIR-EO` | `scale_linear(eo, 0, 0.25)` | null or `5` / `unvalidated_default` | null or `5` / `unvalidated_default` | `equalized_odds_difference` |
| `FR-DP-01` | `F-FAIR-DP` | `scale_linear(dp, 0, 0.25)` | same S policy | same D policy | `demographic_parity_difference` |
| `FR-PERF-01` | `F-FAIR-PERF` (multiclass) | `scale_linear(gap, 0, 0.30)` | same S policy | same D policy | `subgroup_worst_group_acc_gap` |
| `FR-PERF-02` | `F-FAIR-PERF` (regression, when pinned) | `scale_linear(mae_gap, 0, mae_scale_high)` | same S policy | same D policy | `mae_gap_absolute` |

`mae_scale_high` (when a pin exists): **IQR of `Y`** on the evaluated sample (uncalibrated). If IQR is 0, mapping is `mapping_blocked`.

There is **no** `conservative_penalty`, **no** Safety high-impact adjustment, **no** slice penalty on O.

**Autonomous vs Assisted:** Assisted leaves S and D null until a human supplies them (cannot finalize that aspect’s `Pi` until S and D are set, or the human explicitly adopts `unvalidated_default`). Autonomous may emit S=5, D=5 with those trace fields so a complete triple exists for Layer C; the methodology label remains PROPOSED.

#### 6.10.1 Mapping trace (required when `scored_risk`)

```json
{
  "risk_id": "F-FAIR-EO",
  "rule_id": "FR-EO-01",
  "methodology_version": "tl-fairness-osd-v1.0",
  "O": 6,
  "S": 5,
  "D": 5,
  "S_source": "unvalidated_default",
  "D_source": "unvalidated_default",
  "inputs": {"equalized_odds_difference": 0.11, "wide_ci": false},
  "rationale": "EO point 0.11 and ci_lower > ε=0.02; O from EO only; S/D unvalidated defaults"
}
```

### 6.11 Fairness confidence (evidence strength)

See [§8](#8-confidence-model-fairness--robustness). Fairness-specific factors:

- `data_quality`: `min(1.0, n_evaluated / 500) * min(1.0, min_group_n_observed / 100)` where `min_group_n_observed` is the smallest **compared** group after thin-group exclusion
- `probe_reliability`: `1.0` MODEL_FAITHFUL; `0.4` PROXY; `0.0` FAILED
- `evidence_completeness`: `1.0` only if the **primary scored metric’s CI** exists **and** mapping was not blocked; else **≤ 0.6**. If `no_material_risk`, completeness is `1.0` only if CIs exist for **both** DP and EO in binary (or the sole PERF primary in multiclass/regression) **and** mapping was not blocked; else ≤ 0.6

---

## 7. Robustness methodology

### 7.1 Scientific objective

Robustness evidence measures **stability of model predictions** under a **declared** input perturbation on a **task-matched** evaluation set. v1.0 does not claim adversarial robustness against adaptive attackers. Char-swap is a **minimum bar**, not semantic robustness.

### 7.2 Risk taxonomy (Robustness aspect)

**Scored risk (Layer B — at most one):**

| Risk ID | Name | Construct |
| ------- | ---- | --------- |
| `R-ROB-PERT` | Perturbation fragility | Material accuracy (or MAE) **drop** under the declared perturbation |

**Not scored:**

| Item | Disposition |
| ---- | ----------- |
| Absolute clean accuracy / clean MAE | Evidence + optional `uninformative_robustness` **block**. Not a Robustness FRIES risk. |
| Relative degradation as a second risk | Evidence only. Do not score a second `Pi`. |

### 7.3 Dataset registry requirements

```yaml
logical_key: <string>
hf_path: <pinned>
revision: <sha>
modality: text | tabular
task_type: binary_classification | multiclass_classification | regression
robustness:
  evaluation_domain: sentiment | news | tabular_adult | ...
  compatible_pipeline_tags: [text-classification, sentiment-analysis]
  label_field: label
  input_field: text | features
  min_total_n: 200
  min_evaluated_n: 100
  label_compatibility_min_fraction: 0.95
  mae_floor: <required if regression>
notes: <must document domain match to intended model use>
```

#### 7.3.1 v1.0 pinned robustness datasets

| `logical_key` | Modality | Task | Compatible models | Domain note |
| ------------- | -------- | ---- | ----------------- | ----------- |
| `ag_news_robustness` | text | multiclass_classification | News topic classifiers | **Mismatch** for sentiment SST-2 models — use only when `evaluation_domain: news` in config **or** the model card states news |
| `sst2_robustness` | text | binary_classification | Sentiment models | **Must be added** to the registry (pin `stanfordnlp/sst2`) for SST-2 family |
| `adult_tabular_robustness` | tabular | binary_classification | Tabular clf on Adult features | Feature noise; classification only |

MVP default `ag_news_robustness` for all text classifiers is **non-compliant** unless MAC/domain alignment confirms news.

Tabular **regression** robustness: **no v1.0 normative pin** (`NOT_APPLICABLE` until a pin with target + `mae_floor` exists). Metric formulas in §7.5.2 are for that future pin.

**Domain alignment rule (`G-ROB-DOMAIN`):**

- If model card `intended_use` / dataset pins conflict with the robustness dataset domain, status = `INSUFFICIENT_EVIDENCE` with reason `domain_mismatch`, **unless** `allow_domain_mismatch: true`.
- If `allow_domain_mismatch: true`: metrics may be computed; `osd_proposals` stay **empty** unless a human **accepts** the mismatch in Assisted mode; confidence **strength** must not exceed `medium` (§8.2).

### 7.4 Perturbation families

| Modality | Task | Perturbation `attack_id` | Parameters |
| -------- | ---- | ------------------------ | ---------- |
| text | classification | `char_swap` | `max_changes = round(budget * 100)` clamped [1, 8]; `budget_default = 0.03` |
| tabular | classification | `gaussian_feature_noise` | `sigma = 0.05` on z-scored numeric features; categorical unchanged |
| tabular | regression | `gaussian_feature_noise` | Same, **only when a pin exists** |
| text | regression | — | `NOT_APPLICABLE` v1.0 |

Char-swap does **not** measure semantic or distributional shift. Perturbation must be **deterministic** given `seed` (MVP `char_swap_attack` RNG semantics). Char-swap **must not increase D**.

### 7.5 Applicable metrics

Layer A. The scored primary scalar is `accuracy_drop` (classification) or `mae_increase` (regression).

#### 7.5.1 Classification

| Metric key | Formula | Scored? |
| ---------- | ------- | ------- |
| `clean_accuracy` | `correct_clean / n_evaluated` | Evidence; used only for `uninformative_robustness` block |
| `robust_accuracy` | `correct_perturbed / n_evaluated` | Evidence |
| `accuracy_drop` | `clean_accuracy − robust_accuracy` | **Primary scalar** for `R-ROB-PERT` |
| `relative_degradation` | `robust_accuracy / max(clean_accuracy, 0.05)` | Evidence only |
| `attack_success_rate` | `count(clean correct AND perturbed wrong) / n_evaluated` | Evidence only |
| `flip_rate` | same as ASR for char_swap | Evidence only |

Do not use unbounded `robust/clean` without the 0.05 floor, even as evidence.

#### 7.5.2 Regression (formulas; `NOT_APPLICABLE` until pin)

| Metric key | Formula | Scored? |
| ---------- | ------- | ------- |
| `clean_mae`, `robust_mae` | mean absolute error | Evidence |
| `mae_increase` | `robust_mae − clean_mae` | **Primary scalar** for `R-ROB-PERT` when pinned |
| `relative_mae_increase` | `mae_increase / max(clean_mae, mae_floor)` | Evidence only |

### 7.6 Statistical reliability and uncertainty

| Quantity | Method |
| -------- | ------ |
| `clean_accuracy`, `robust_accuracy` | Wilson 95% CI |
| `accuracy_drop` | Paired bootstrap CI (`B=1000`): resample indices, recompute both accuracies |
| `clean_mae`, `robust_mae`, `mae_increase` | Bootstrap CI |

#### Reliability gates

| Gate ID | Condition | Consequence |
| ------- | --------- | ----------- |
| `G-ROB-N-EVAL` | `n_evaluated < 100` | `INSUFFICIENT_EVIDENCE`; no O/S/D |
| `G-ROB-LABEL-COMPAT` | fraction of samples with label in `[0, num_labels)` < 0.95 | `INSUFFICIENT_EVIDENCE`; no O/S/D |
| `G-ROB-CLEAN-FLOOR` | `clean_accuracy < 0.20` (classification) | Flag `uninformative_robustness`; compute metrics; **`aspect_scoring: mapping_blocked`**; **do not** map `R-ROB-PERT` |
| `G-ROB-CI-WIDE` | `accuracy_drop` CI width > 0.20 | Flag `wide_ci`; **`mapping_blocked`**; empty `osd_proposals` |
| `G-ROB-DOMAIN` | domain mismatch and `allow_domain_mismatch` is false | `INSUFFICIENT_EVIDENCE` |

`clean_accuracy < 0.20` is **only** this block. It is not a scored robustness risk and is not an O/S/D input.

### 7.7 Minimum evidence

| Requirement | Value |
| ----------- | ----- |
| `n_requested` | ≥ 200 |
| `n_evaluated` | ≥ 100 after label-head filter |
| Label compatibility | ≥ 95% |
| Perturbation applied | 100% of evaluated rows |
| Model | Imported weights at pinned revision |

### 7.8 Abstention and status rules

| Status | When |
| ------ | ---- |
| `EVALUATED` | `G-ROB-N-EVAL`, `G-ROB-LABEL-COMPAT`, and hard `G-ROB-DOMAIN` pass; metrics computed |
| `INSUFFICIENT_EVIDENCE` | `G-ROB-N-EVAL`, `G-ROB-LABEL-COMPAT`, or hard `G-ROB-DOMAIN` |
| `NOT_APPLICABLE` | MAC not in robustness scope; image/audio/LM; regression without pin |
| `FAILED` | Model load failure, zero evaluated samples |
| `SKIPPED` | Config skip |

`uninformative_robustness` and `wide_ci` keep `EVALUATED` with `mapping_blocked`. Domain mismatch with `allow_domain_mismatch: true` keeps computed metrics but `osd_proposals` empty until Assisted human accept (`mapping_blocked` until then).

### 7.9 Evidence → scored-risk rules

Let `ε_drop = 0.05` (uncalibrated).

**`R-ROB-PERT` fires** (classification) only if mapping is not blocked **and**:

```text
accuracy_drop > ε_drop AND ci_lower(drop) > ε_drop
```

Regression (when pinned): `mae_increase > mae_floor` AND `ci_lower(mae_increase) > mae_floor`.

Do not use a second trigger on `relative_degradation`.

If gates pass, mapping is not blocked, and the trigger does not fire: `aspect_scoring: no_material_risk`, `osd_proposals: []`.

### 7.10 Risk → O mapping (`tl-robustness-osd-v1.0`)

**O** from the drop only (not from `robust_accuracy`, not from relative degradation as a second risk).

| rule_id | Risk | O | S | D |
| ------- | ---- | - | - | - |
| `RR-PERT-01` | `R-ROB-PERT` (classification) | `scale_linear(accuracy_drop, 0, 0.40)` | null or `5` / `unvalidated_default` | null or `5` / `unvalidated_default` |
| `RR-PERT-02` | `R-ROB-PERT` (regression, when pinned) | `scale_linear(mae_increase, 0, mae_scale_high)` | same S policy | same D policy |

Char-swap does not change D. No `conservative_penalty`. `wide_ci` and `uninformative_robustness` **block** mapping rather than nudging O/S/D.

If Autonomous needs a complete triple: S=5, D=5 with `S_source` / `D_source` = `unvalidated_default`.

Aspect aggregation: at most one `Pi`. `no_material_risk` must not set `Ti = 0` (§1.3).

### 7.11 Robustness confidence

- `data_quality`: `min(1.0, n_evaluated/300)`
- `probe_reliability`: `1.0` if domain aligned and model loaded; `0.5` if `allow_domain_mismatch`; `0.0` FAILED
- `evidence_completeness`: `1.0` only if the paired CI on `accuracy_drop` (or `mae_increase`) exists **and** mapping was not blocked; else ≤ 0.6. For `no_material_risk`, require that CI to exist and mapping not blocked.

---

## 8. Confidence model (Fairness & Robustness)

Confidence is **evidence strength**, not correctness, and is **not** a calibrated probability (`proposed_calibration: true`).

### 8.1 Combined formula

```text
combined = geometric_mean(data_quality, probe_reliability, evidence_completeness)
```

Floor each factor at `0.1` before geometric mean. Clamp result to `[0, 1]`.

### 8.2 Strength labels (informational)

| combined | Label |
| -------- | ----- |
| ≥ 0.75 | `strength: high` |
| 0.50 – 0.74 | `strength: medium` |
| < 0.50 | `strength: low` — must appear in report limitations |

**Caps and floors:**

- Cap `strength` at **`medium`** (even if `combined ≥ 0.75`) when any of: `n_evaluated` equals the v1.0 minimum (fairness 200 or robustness 100), `min_group_n_observed` equals 50 (fairness), `wide_ci`, `uninformative_robustness`, PROXY, or `allow_domain_mismatch`.
- `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE` / `FAILED`: force `combined < 0.50`, `strength: low`, **no O/S/D**.
- Do not treat “CIs exist because they are mandatory” as completeness 1.0 when mapping is blocked.

### 8.3 Required output

```json
"confidence": {
  "combined": 0.62,
  "factors": {
    "data_quality": 0.85,
    "probe_reliability": 1.0,
    "evidence_completeness": 0.80
  },
  "strength": "medium",
  "method": "geometric_mean_v1",
  "proposed_calibration": true
}
```

---

## 9. Worked examples

### 9.1 Fairness — binary, practical floor not met (`no_material_risk`)

**Setup:** Hypothetical text fairness corpus with `A`; MODEL_FAITHFUL; gates pass; `n_evaluated = 400`, `min_group_n_observed = 120`.

| Metric | Point | 95% CI |
| ------ | ----- | ------ |
| `demographic_parity_difference` | 0.06 | [0.01, 0.11] |
| `equalized_odds_difference` | 0.04 | [0.00, 0.09] |
| `subgroup_f1_spread` | 0.07 | [0.02, 0.12] |

`ε = 0.02`. EO: `ci_lower = 0.00` is not `> ε` → EO does not fire. DP: `ci_lower = 0.01` is not `> ε` → DP does not fire. F1 is not scored.

**Status:** `EVALUATED`  
**`aspect_scoring`:** `no_material_risk`  
**`osd_proposals`:** `[]`  
**FRIES:** do **not** set Fairness `Ti = 0`; do **not** mark the aspect as withheld/incomplete.

This is the opposite of a `ci_lower > 0` trigger: DP’s CI excludes 0 but still includes values below `ε`.

---

### 9.2 Fairness — tabular binary (Adult, MODEL_FAITHFUL), one scored risk

**Setup:** Tabular binary classifier on `adult_fairness`, `sensitive_attribute=sex`, `n_evaluated = 500`. Thin groups none.

| Group | n | TPR | FPR | F1 |
| ----- | - | --- | --- | -- |
| Male | 280 | 0.62 | 0.18 | 0.71 |
| Female | 220 | 0.55 | 0.24 | 0.65 |

| Metric | Point | CI |
| ------ | ----- | -- |
| DP | 0.09 | [0.03, 0.15] |
| EO | 0.11 | [0.04, 0.18] |
| F1 spread | 0.06 | [0.01, 0.11] |

EO candidate fires (`0.11 > 0.02` and `0.04 > 0.02`). DP would also fire; **EO is preferred**. F1 not scored.

**`scored_risk_id`:** `F-FAIR-EO`  
**O:** `scale_linear(0.11, 0, 0.25) = 6`  
**S, D (Autonomous):** `5`, `5` with `unvalidated_default`  
**Not emitted:** DP triple, F1 triple.

**Status:** `EVALUATED`, `aspect_scoring: scored_risk`

---

### 9.3 Fairness — legacy PROXY (no FRIES)

**Setup:** NLP model + `fairness.mode: proxy_lr` on Adult.

**Status:** `PROXY`  
**Metrics:** may be stored  
**`osd_proposals`:** `[]`  
**FRIES:** no contribution from Fairness. Report title must state proxy reproduction.

---

### 9.4 Fairness — insufficient slices

**Setup:** `n_evaluated = 220`, `min_group_n_observed = 35` (< 50); only one group would remain if 35 is excluded.

**Gate:** `G-FAIR-N-GROUP`  
**Status:** `INSUFFICIENT_EVIDENCE`  
**`osd_proposals`:** `[]`  
**Not emitted:** any representativeness triple or O penalty on other risks.

If instead two groups had n ≥ 50 and a third had n = 35: exclude the third from metrics; status may be `EVALUATED`; still no representativeness risk.

---

### 9.5 Robustness — SST-2 on pinned SST-2 subset, one scored risk

**Setup:** DistilBERT SST-2; `sst2_robustness`; `n_evaluated = 200`; char_swap `max_changes=3`; domain aligned; `clean_accuracy = 0.88` (not uninformative).

| Metric | Value | 95% CI |
| ------ | ----- | ------ |
| `clean_accuracy` | 0.88 | [0.83, 0.92] |
| `robust_accuracy` | 0.76 | [0.70, 0.81] |
| `accuracy_drop` | 0.12 | [0.07, 0.17] |

`ε_drop = 0.05`. `0.12 > 0.05` and `ci_lower = 0.07 > 0.05` → `R-ROB-PERT` fires.

**O:** `scale_linear(0.12, 0, 0.40) = 7`  
**S, D:** `5` / `unvalidated_default` (char-swap does not raise D)  
**Not emitted:** a second gap risk; O is **not** `scale_linear(robust_accuracy)`.

**Status:** `EVALUATED`, `aspect_scoring: scored_risk`

If instead drop CI were `[0.04, 0.14]` (`ci_lower = 0.04 < ε_drop`): **no** scored risk (`no_material_risk`), even though the interval excludes 0.

---

### 9.6 Robustness — domain mismatch

**Without override:** `G-ROB-DOMAIN` → `INSUFFICIENT_EVIDENCE`, empty `osd_proposals`.

**With `allow_domain_mismatch: true`:** metrics may be stored; `osd_proposals` empty; `aspect_scoring: mapping_blocked`; `strength` ≤ `medium`. Assisted human accept of the mismatch is required before any O proposal.

---

### 9.7 Robustness — ViT image model

**MAC:** `IMAGE_CLF`  
**Status:** `NOT_APPLICABLE`  
**Reason:** Image robustness is not in `tl-methodology-v1.0` scope.

---

### 9.8 Regression — no v1.0 pin

**Setup:** Any model treated as tabular regression on Adult `hours-per-week` / `fnlwgt`.

**Status:** `NOT_APPLICABLE` for Fairness and Robustness (no normative regression pin, no `mae_floor`).  
**Do not** score MAE-ratio or MAE-gap O/S/D on this path.

---

### 9.9 Robustness — uninformative clean accuracy (mapping blocked)

**Setup:** Classification, `clean_accuracy = 0.12`, `n_evaluated = 150`, domain aligned.

**Flag:** `uninformative_robustness`  
**Status:** `EVALUATED`  
**`aspect_scoring`:** `mapping_blocked`  
**`osd_proposals`:** `[]`  
**Not emitted:** a “clean performance” robustness triple.

---

## 10. Known limitations and non-claims

### 10.1 Fairness limitations

1. **Single sensitive attribute** — no intersectionality in v1.0.
2. **Observational disparities** — not causal; confounders not controlled.
3. **Binary DP/EO** — not generalized to multiclass; multiclass uses worst-group accuracy gap only.
4. **No text fairness dataset** in initial pins — most NLP models will be `NOT_APPLICABLE` until a corpus is pinned.
5. **Equalized odds** omitted when per-group positives/negatives are thin (`eo_unstable`).
6. **`ε` and `scale_linear` ranges** are **uncalibrated heuristics**, not empirically tied to harm. They only gate or scale **O**.
7. **S and D** are unvalidated defaults or human-entered. v1.0 does **not** claim scientifically validated O/S/D triples.
8. **F1 spread** is reported but not scored (base-rate confounding).
9. **ECE** is reported when available but not scored (sample-size noise).

### 10.2 Robustness limitations

1. **Char-swap** does not measure semantic or distributional shift.
2. **Small sample sizes** (100–300) — CIs may be wide; `wide_ci` blocks mapping.
3. **CPU inference** may differ from GPU production — record device.
4. **No adaptive attacks** — not security robustness.
5. **Domain alignment** can be subjective — hard gate unless Assisted human accept.
6. **Clean accuracy** is not a robustness score; very low clean accuracy blocks mapping rather than inventing a second risk.

### 10.3 Non-claims

TrustLens Methodology v1.0 **does not** claim:

- Legal fairness compliance
- Robustness against adversarial actors
- Generalization to production traffic
- Ranking models across unrelated tasks
- Replacement for domain expert review
- **Scientifically validated S or D**, or calibrated conversion of disparity/drop into FRIES O

---

## 11. Acceptance criteria (implementation gate)

An implementation is **v1.0-compliant** only if all criteria pass.

### 11.1 Global

| ID | Criterion | Verification |
| -- | --------- | ------------ |
| G-01 | Evidence artifacts include `methodology_version: tl-methodology-v1.0` | Schema test |
| G-02 | MODEL_FAITHFUL path uses InferenceBackend on `model_ref` | Mock backend asserts `load(model_ref)` |
| G-03 | No numeric O/S/D when status ∈ `{INSUFFICIENT_EVIDENCE, NOT_APPLICABLE, FAILED, SKIPPED, PROXY}` | Agent + pipeline tests |
| G-04 | Every O proposal includes `rule_id`, `risk_id`, `methodology_version` | Trace schema test |
| G-05 | PROXY: Layer A metrics allowed; **`osd_proposals` empty**; no FRIES contribution | Fairness integration test |
| G-06 | Bootstrap/Wilson CIs present for primary metrics | Metric output test |
| G-07 | `reliability.failed_gates` populated when gates fail | Gate unit tests |
| G-08 | `no_material_risk` is `EVALUATED`, evidence-complete, **not** withhold/incomplete; `Ti` is **not** 0 | Pipeline + scorer wiring test |
| G-09 | S and D traces cite `unvalidated_default` or are null — **never** copied from O | Mapping unit test |
| G-10 | At most one `osd_proposals` entry per aspect | Mapping unit test |

### 11.2 Fairness

| ID | Criterion | Verification |
| -- | --------- | ------------ |
| F-01 | `min_total_n=200`, `min_group_n=50` enforced | Thin slices → `INSUFFICIENT_EVIDENCE` |
| F-02 | NLP model without fairness dataset → `NOT_APPLICABLE` (not Adult proxy) | MAC + probe test |
| F-03 | Applicable **metrics** (DP, EO, F1, per-group) still computed; **at most one** scored fairness risk | Metric bundle + selection test |
| F-04 | Triggers require `point > ε` **and** `ci_lower > ε` | Rule engine with synthetic CIs (including CI excluding 0 but `ci_lower < ε`) |
| F-05 | `F-FAIR-EO` not selected when `eo_unstable`; DP may still be selected | Fixture with <10 positives in a group |
| F-06 | `proxy_lr` cannot emit `EVALUATED` or O/S/D | Config test |
| F-07 | Multiclass scores only `subgroup_worst_group_acc_gap` (not DP, not macro-F1) | Multiclass fixture |
| F-08 | Regression without a valid pin → `NOT_APPLICABLE`; MAE-ratio never triggers scoring | Config / MAC test |
| F-09 | Binary F1 spread never appears in `osd_proposals` | Mapping test |
| F-10 | A CI that excludes 0 but has `ci_lower ≤ ε` does **not** trigger a scored risk | Synthetic CI fixture (example 9.1) |
| F-11 | `G-FAIR-N-GROUP` never emits a representativeness triple or an O penalty on other risks | Probe + mapping test |
| F-12 | If EO and DP both fire, only EO is scored | Selection test |
| F-13 | `wide_ci` → `mapping_blocked`, empty proposals (no O nudge) | Mapping test |
| F-14 | ECE never appears in `osd_proposals` | Mapping test |

### 11.3 Robustness

| ID | Criterion | Verification |
| -- | --------- | ------------ |
| R-01 | `n_evaluated >= 100` required | Probe test |
| R-02 | Label compatibility ≥ 95% | Mismatched head test |
| R-03 | `relative_degradation` uses `max(clean, 0.05)` in **evidence**; not a second scored risk | Unit test |
| R-04 | Domain mismatch → `INSUFFICIENT_EVIDENCE` without `allow_domain_mismatch` | SST-2 on AG News test |
| R-05 | At most **one** robustness O proposal (`R-ROB-PERT`); no clean-performance or relative-gap triples | Mapping test |
| R-06 | Image/LM models → `NOT_APPLICABLE` | MAC test |
| R-07 | Paired bootstrap CI on `accuracy_drop` | Statistical test |
| R-08 | `sst2_robustness` pin used for SST-2 models (once added to registry) | Config + integration |
| R-09 | `R-ROB-PERT` mapping blocked when `uninformative_robustness` | Mapping test |
| R-10 | Char-swap does not set D above the unvalidated default (5) or un-null it to a higher value | Mapping test |
| R-11 | Trigger is `accuracy_drop > ε_drop` and `ci_lower > ε_drop` | Rule engine test |
| R-12 | `allow_domain_mismatch` without human accept → empty `osd_proposals`, strength ≤ medium | Probe + confidence test |
| R-13 | O is `scale_linear(accuracy_drop, …)`, not `scale_linear(robust_accuracy, …)` | Mapping test |

### 11.4 Regression / classification coverage

| ID | Criterion | Verification |
| -- | --------- | ------------ |
| C-01 | `binary_classification` end-to-end on tabular (Adult) + text robustness where pinned | Lifecycle test |
| C-02 | `multiclass_classification` metrics path; PERF from worst-group acc only | Unit test |
| C-03 | Tabular/text **regression** without pin → `NOT_APPLICABLE` (formulas unused) | MAC test |
| C-04 | `NOT_APPLICABLE` / incomplete evidence do not write a numeric aspect `Ti` of 0; `no_material_risk` does not withhold the evaluation as incomplete evidence | Pipeline test |

### 11.5 Documentation

| ID | Criterion | Verification |
| -- | --------- | ------------ |
| D-01 | Report limitations list methodology version, PROXY, domain mismatch, `wide_ci`, unvalidated S/D | Report builder snapshot |
| D-02 | README references this document as normative for F/R | Manual review |

---

## 12. Appendices

### Appendix A — Config keys (probe_config extension)

```yaml
schema_version: probe_config_v2
fairness:
  enabled: true
  mode: model_faithful | proxy_lr   # default: model_faithful
  dataset: adult_fairness
  sensitive_attribute: sex
  seed: 42
  n_samples: 500
robustness:
  enabled: true
  dataset: sst2_robustness
  attack_id: char_swap
  attack_budget: 0.03
  allow_domain_mismatch: false
  seed: 42
  n_samples: 200
```

### Appendix B — MVP → v1.0 metric mapping

| MVP metric | v1.0 disposition |
| ---------- | ---------------- |
| `demographic_parity_difference` | Layer A; scored **only if** selected over EO |
| `equalized_odds_difference` | Layer A; **preferred** scored scalar when it triggers |
| `subgroup_f1_spread` | Layer A only; **never scored** |
| `degradation_ratio` | Replaced as evidence by `relative_degradation` with ε floor; **not scored** |
| `accuracy_drop` | Primary scored scalar for robustness |
| `integrity_score_0_10` | Not part of F/R methodology |
| `coverage_ratio` | Not part of F/R methodology |

### Appendix C — Registry additions

| Priority | `logical_key` | Purpose | v1.0 status |
| -------- | ------------- | ------- | ----------- |
| P0 | `sst2_robustness` | SST-2 sentiment robustness | **Required** for SST-2 compliance (R-08) |
| P1 | text fairness corpus with declared `A` | NLP fairness | **Not in v1.0 pins**; until then NLP fairness is `NOT_APPLICABLE` |
| post-v1.0 | tabular regression pin with real target + `mae_floor` | Regression F/R | **Not a v1.0 normative pin** |

Pins must include full HF revision SHAs per `configs/datasets_v1.yaml` convention.

### Appendix D — References (internal)

| Document | Role |
| -------- | ---- |
| `docs/TRUSTLENS_METHODOLOGY_V1_0_AMENDMENTS.md` | Pre-implementation amendments A1–A10 (folded herein) |
| `README.md` | Product vision and FRIES layering |
| `backend/tests/SCORING.md` | Frozen FRIES **risk** math oracle (`cbrt`, veto, weights) |
| `docs/results_chapter.md` | Empirical critique of MVP |
| `docs/experiments_runbook.md` | Reproduction protocol |
| `backend/app/probes/fairness_metrics.py` | Current metric implementations (to be extended) |
| `backend/app/probes/robustness_nlp.py` | Current perturbation runner (to be wrapped) |

### Appendix E — Retired identifiers (must not be implemented)

`F-FAIR-REP`, `FR-REP-01`, `slice_penalty_O`, scored `F-FAIR-CAL`, binary `F-FAIR-PERF` from F1, `R-ROB-CLEAN`, `R-ROB-GAP`, `RR-CLEAN-01`, `RR-GAP-01`, `conservative_penalty`, trigger `ci_lower > 0`, MAE-ratio scoring trigger, `adult_fairness_regression` as a v1.0 pin.

---

*End of TrustLens Methodology v1.0 — Fairness & Robustness (amendments A1–A10 folded). Integrity, Explainability, and Safety specifications are separate documents. Risk-level FRIES math remains `fries-original-v1`; empty-risk `Ti = 0` must not be used for `no_material_risk`.*
