# TrustLens Methodology v1.0 — Pre-implementation amendments

**Applies to:** `docs/TRUSTLENS_METHODOLOGY_V1_0_FAIRNESS_ROBUSTNESS.md`  
**Scope:** Only changes required before implementation. Everything not listed here stays as written.  
**Code:** Do not implement until this list is folded into the spec.

---

## Findings (why these amendments exist)

### Double-counting (same phenomenon → multiple FRIES risks)

| Rule as written | What it does |
| ---------------- | ------------ |
| Binary fairness scores `F-FAIR-DP`, `F-FAIR-EO`, and `F-FAIR-PERF` independently, then averages `Pi` | DP is a function of TPR/FPR and group base rates; F1 spread is a function of the same error types plus prevalence. One subgroup pattern can lower the Fairness aspect three times. Example 9.2 does this. |
| `F-FAIR-REP` is a scored risk **and** `slice_penalty_O` on other risks **and** `G-FAIR-N-GROUP` → `INSUFFICIENT_EVIDENCE` | Thin slices are counted as status failure, a fake (5,5,4) triple, and an O penalty. Internally contradictory. |
| `R-ROB-PERT` and `R-ROB-GAP` both fire on the same accuracy drop | Example 9.5 scores one char-swap drop twice. Both also map **S** from `accuracy_drop`. |
| `R-ROB-CLEAN` lives in the Robustness aspect; `RR-PERT-01` maps **O** from `robust_accuracy` | Low absolute accuracy is not perturbation fragility. A weak model is punished as “not robust” even when the drop is small. |
| `wide_ci` applies `conservative_penalty` to O (and therefore S, because S=O) **and** lowers D | One uncertainty flag hits all three FRIES components. |
| Safety `high_impact_deployment` lowers Fairness **S** | Unevaluated card heuristic contaminates Fairness O/S/D. |

### False confidence / invalid O/S/D

| Rule as written | What it does |
| ---------------- | ------------ |
| **S = O** from the same disparity or drop | Severity is harm-if-occurs, not magnitude-of-metric. This is the MVP collapse, renamed per risk. |
| **D = 6–8** because a probe computed a number, or because char-swap is “easy to log” | Audit measurement is not operational detection. High D **inflates** `Pi` for a toy attack. |
| `EVALUATED` + no triggered risks → empty `osd_proposals` (same shape as abstain) | “Measured, nothing above floor” is indistinguishable from “could not evaluate.” |
| `PROXY` may still emit O/S/D | Substitute-model numbers can enter FRIES. |
| Confidence `evidence_completeness = 1.0` if CIs exist | CIs are mandatory, so this factor is almost always 1.0. |
| Confidence can be `high` at the minimum-n gate | `n=500`, `min_group_n=50` already yields a high geometric mean. |
| `combined < 0.50` required for `wide_ci`, but mapping still emits O/S/D | Flag does not prevent a precise-looking triple. |

### Metric validity

| Rule as written | What it does |
| ---------------- | ------------ |
| Binary `subgroup_f1_spread` as a fairness risk | Groups with equal TPR/FPR can differ in F1 solely due to base-rate differences. |
| `F-FAIR-CAL` as a scored risk at v1.0 sample sizes | Per-group ECE at n≈200 is too noisy to support O/S/D. |
| Trigger `point > ε AND ci_lower > 0` | CI may exclude 0 while still including effects below the practical floor `ε`. |
| `mae_ratio_max_min` with ε = 1e-6 | Near-zero MAE in one group explodes the ratio. |
| `adult_fairness_regression` with `fnlwgt` / `hours-per-week` as Y | Survey weight / hours are not a specified regression task for Adult income models. |
| Dual PERF triggers (`mae_ratio` **or** `mae_gap`; macro-F1 **or** worst-group acc) | Implementers can score the same PERF risk twice. |

---

## Amendment list (normative)

Apply these in place of the conflicting sentences. Do not add new risks, datasets, or mapping science beyond what is listed.

### A1. One scored fairness risk family per run (binary)

**Replace** “up to three risks” averaging for binary classification.

- **Evidence (Layer A):** still compute DP, EO (if stable), F1 spread, per-group tables, CIs. These remain in the artifact.
- **Scored risk (Layer B):** at most **one** disparity risk enters FRIES:
  - Prefer `F-FAIR-EO` when `G-FAIR-EO-UNSTABLE` is false and EO triggers.
  - Else `F-FAIR-DP` if DP triggers.
  - Do **not** score `F-FAIR-PERF` on binary F1.
- Multiclass: score only `F-FAIR-PERF` from **`subgroup_worst_group_acc_gap`** (not macro-F1).
- Regression: score only `F-FAIR-PERF` from **`mae_gap_absolute`**, and only if `min_g MAE_g ≥` a dataset-declared `mae_floor` (default: 1% of `|Y|` IQR, not `1e-6`). Drop `mae_ratio` as a trigger.

### A2. Drop scored `F-FAIR-CAL` and scored `F-FAIR-REP`

- `F-FAIR-CAL`: evidence-only if probabilities exist. No O/S/D.
- `F-FAIR-REP`: **not a risk**. Thin slices are only `G-FAIR-N-GROUP` → `INSUFFICIENT_EVIDENCE` (no O/S/D). Remove `FR-REP-01`, `slice_penalty_O`, and the “slice gate failed but still map other risks” rule.
- If some groups are below `min_group_n` but ≥2 groups remain above it: exclude the thin groups from metrics; do not invent a representativeness triple.

### A3. Robustness: one perturbation risk, not three

- **Evidence:** keep `clean_accuracy` / `clean_mae`, `robust_*`, `accuracy_drop` / `mae_increase`, `relative_*`, ASR, CIs.
- **Scored risk:** only `R-ROB-PERT` (stability under the declared perturbation).
- **Delete** `R-ROB-GAP` (duplicate of the drop) and **delete** `R-ROB-CLEAN` from the Robustness catalog (absolute clean performance is not a robustness risk). Record low clean accuracy as a **limitation / flag** (`uninformative_robustness` if `clean_accuracy < 0.20`), which **blocks** `R-ROB-PERT` mapping rather than adding a second triple.
- Trigger `R-ROB-PERT` only if `accuracy_drop > ε_drop` **and** paired-bootstrap `ci_lower(drop) > ε_drop` (classification), analogously `ci_lower(mae_increase)` for regression. Remove the extra `relative_degradation < 0.90` AND `drop > 0.03` rule.

### A4. Do not map S or D from probe metrics

For every remaining scored risk:

- **O** may be mapped from the **single** primary evidence scalar (EO or DP; worst-group acc gap; MAE gap; accuracy drop / MAE increase) via the existing `scale_linear` helper, still clamped to [1, 9], still PROPOSED.
- **S** is **not** set equal to O. v1.0 agent emits `S = null` (Assisted: human required) or, if Autonomous must propose a complete triple, `S = 5` with trace `"S_source": "unvalidated_default"`. No Safety-card adjustment.
- **D** is **not** 6–8 because the metric exists or the attack is obvious. Same policy as S: `null` or unvalidated default `5`, `"D_source": "unvalidated_default"`. Char-swap must not raise D.

Remove `conservative_penalty` on O/S/D. If `wide_ci` is set, **do not propose O/S/D** (`INSUFFICIENT_EVIDENCE` or keep `EVALUATED` with empty `osd_proposals` and flag `wide_ci` — treat as mapping-blocked, not a small numeric nudge).

### A5. Practical-significance trigger

Replace `point > ε AND ci_lower > 0` with:

```text
point > ε AND ci_lower > ε
```

Keep `ε = 0.02` for rate/gap metrics in [0, 1] as an **explicitly uncalibrated practical floor**, labeled as such. Do not add more ε values. For robustness, use the same rule with the single `ε_drop = 0.05` already defined (and `ci_lower > ε_drop`). Delete `ε_clean` as a mapping input except for the uninformative-robustness **block** in A3.

### A6. “No material risk” is not abstention

When gates pass and no scored risk triggers:

- Status stays `EVALUATED`.
- `osd_proposals: []` is correct (do not invent 9s/10s).
- Set `aspect_scoring: "no_material_risk"` (name fixed).
- This **must not** use the same pipeline path as `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE` withhold. Completeness of the Fairness or Robustness aspect is **evidence-complete**, not “a risk fired.” Overall FRIES policy: include the aspect as **empty-risk mean = do not drag to 0**; reweight overall T over aspects that are evidence-complete (including no-material-risk). Do not treat empty-risk as `Ti = 0`.

### A7. PROXY never enters FRIES

`fairness.mode: proxy_lr` may compute Layer A metrics for reproduction only. `osd_proposals` **must be empty**. No Autonomous `final_scores` contribution from PROXY fairness. Trace may store metrics, not O/S/D.

### A8. Confidence must not look calibrated

- Drop `evidence_completeness = 1.0 if CIs present`. Completeness is 1.0 only if the **primary scored metric’s CI** exists **and** mapping was not blocked; else ≤ 0.6.
- Cap `strength` at `medium` whenever `n_evaluated` or `min_group_n_observed` is at the v1.0 minimum, or `wide_ci`, or `uninformative_robustness`, or PROXY.
- `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE` / `FAILED`: do not emit `strength: high` (force `combined < 0.50` as already stated, and **no O/S/D**).
- Keep `proposed_calibration: true`.

### A9. Remove invalid regression pin as normative

Delete `adult_fairness_regression` from the v1.0 **normative** pin set (Appendix C P2 becomes post-v1.0). Tabular **classification** Adult remains. Tabular regression robustness/fairness stay in the metric **formulas** but are `NOT_APPLICABLE` until a dataset with a declared real-valued target and `mae_floor` is pinned.

### A10. Domain mismatch stays a hard gate

No change to `G-ROB-DOMAIN` except: `allow_domain_mismatch: true` still cannot raise confidence above `medium` (A8) and must keep `osd_proposals` empty unless a human accepts the mismatch in Assisted mode.

---

## Acceptance-criteria patches

Update §11 to match the amendments (delete tests that encoded the old bugs):

| Remove / replace | New check |
| ---------------- | --------- |
| R-05 “three separate robustness risks → three triples” | At most **one** robustness O proposal (`R-ROB-PERT`); no `R-ROB-GAP` / `R-ROB-CLEAN` triples |
| F-03 “at least one of DP/EO/PERF computed” | All applicable **metrics** still computed; **at most one** scored fairness risk |
| G-05 PROXY emits O/S/D with `proxy: true` | PROXY: metrics allowed, **`osd_proposals` empty** |
| Example 9.2 three fairness triples | One scored risk (EO if triggered, else DP); F1 not scored |
| Example 9.5 PERT + GAP | Only `R-ROB-PERT`; S/D default or null per A4 |
| Example 9.4 vs §6.9 `F-FAIR-REP` | Thin slices → `INSUFFICIENT_EVIDENCE` only |

Add:

| ID | Criterion |
| -- | --------- |
| F-09 | Binary F1 spread never appears in `osd_proposals` |
| F-10 | `ci_lower > ε` required to trigger |
| F-11 | `G-FAIR-N-GROUP` never emits `FR-REP-01` or `slice_penalty_O` |
| R-09 | `R-ROB-PERT` blocked when `uninformative_robustness` |
| R-10 | Char-swap does not increase D above the unvalidated default |
| G-08 | `no_material_risk` is not scored as withheld/incomplete evidence |
| G-09 | S and D traces cite `unvalidated_default` or are null — never copied from O |

---

## Explicitly not changing

- Model-faithful inference; Adult proxy banned as `EVALUATED`
- NLP fairness `NOT_APPLICABLE` until a pinned corpus with `A` exists
- Image / LM / generative `NOT_APPLICABLE`
- Original FRIES math (`cbrt`, veto 0, optimal 10, weight floor)
- Agent clamp [1, 9]; humans may set 0 or 10
- Wilson + bootstrap CIs; `min_total_n=200`, `min_group_n=50`; robustness `n_evaluated≥100`
- Char-swap retained as a **declared minimum perturbation** with limitations (not semantic robustness)
- `sst2_robustness` still required for SST-2 models
- PROPOSED / REQUIRES VALIDATION labeling
- `ε` values remain uncalibrated heuristics (now fewer, and they only gate O / triggers)

---

*End of amendment list. Fold A1–A10 and the §11 patches into Methodology v1.0 before writing code.*
