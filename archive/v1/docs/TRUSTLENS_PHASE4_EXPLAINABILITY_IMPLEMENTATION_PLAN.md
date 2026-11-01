# TrustLens Phase 4 — Explainability Implementation Plan

This document is the approved implementation plan for **Phase 4 Explainability only**
(Track 1 documentation / transparency).

---

## 1. Objective

Replace the Phase 13 card-coverage probe with a Layer-A evidence probe that answers:

*What objective evidence exists that required model-card documentation was present and satisfied the tested structural contract?*

It does **not** answer whether the model has good explainability, faithful attributions, or human-useful explanations.

---

## 2. Methodology

| Field | Value |
| ----- | ----- |
| `methodology_version` | `tl-explainability-v1.0` |
| `methodology_basis` | `TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md` |
| Track | Documentation / transparency only (Track 2 runtime explanations deferred) |

**Authority:** [`docs/TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md`](TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md) §7, §11.2.

**Out of scope to change:** Fairness, Robustness, Integrity, Safety, [`fries.py`](../backend/app/scoring/fries.py), [`HeuristicOSDAgent`](../backend/app/osd/agent.py).

---

## 3. What Explainability Measures

- ATX heading matcher + alias tables over Hub `card_text`
- Optional `card_data` field fallbacks (architecture: `model_name`, `base_model` only — not `pipeline_tag`)
- Five required sections with non-trivial body (`MIN_BODY_CHARS = 20`)
- `coverage_ratio = sections_present / 5` as a **count**, not quality
- Keyword-level contradiction flags (open-use vs license; production claim without limitations)

**Not measured:** SHAP/LIME, attention APIs, explanation fidelity, human comprehension, causal correctness.

---

## 4. Named Risks (Evidence Layer Only)

| ID | Trigger |
| -- | ------- |
| `E-DOC-INCOMPLETE` | Non-empty card; ≥1 required section absent or trivial |
| `E-DOC-CONTRADICTION` | Keyword conflict flags in `detect_contradictions` |

- `scored_risk_id` is **always `null`**
- No FRIES occurrence, severity, occurrence, or detectability
- Risks appear in `risks_triggered` only

---

## 5. `aspect_scoring` Semantics

Explainability v1 uses **`risk_detected`**, not `scored_risk`:

| Value | Meaning |
| ----- | ------- |
| `not_scored` | `INSUFFICIENT_EVIDENCE` or `FAILED` |
| `risk_detected` | `EVALUATED` and ≥1 `E-DOC-*` in `risks_triggered` |
| `no_material_risk` | `EVALUATED` and no documentation risk |

`aspect_scoring = risk_detected` means **evidence-layer detection only** — not FRIES scoring and not a populated `scored_risk_id`.

---

## 6. Status and Gates

| Status | When |
| ------ | ---- |
| `EVALUATED` | Non-empty `card_text` |
| `INSUFFICIENT_EVIDENCE` | Empty/missing card (`G-EXP-CARD-EMPTY`) |
| `FAILED` | Unexpected probe failure |

Empty card does **not** trigger `E-DOC-INCOMPLETE`.

---

## 7. Evidence Artifact

Core fields: `methodology_version`, `methodology_basis`, `status`, `aspect_scoring`, `scored_risk_id`, `risks_triggered`, `sections`, `bonus_sections`, `sections_present`, `sections_required`, `coverage_ratio`, `card_chars`, `contradictions`, `checks`, `claims`, `claim_boundary`, `reliability`, `limitations`, `proposed_mapping: false`, `osd_proposals: []`.

**Claim boundary:**

- **Supported:** section presence, coverage count, contradiction flags
- **Not established:** faithfulness, causal correctness, human usefulness, general explainability quality

---

## 8. Confidence Model

Provisional **uncalibrated architecture-consistency weights** (same three-factor engine as other probes). **Not** probabilities and **not** “X% chance the explanation is correct.”

| Status | `probe_reliability` | `data_quality` |
| ------ | ------------------- | -------------- |
| `EVALUATED` | 1.0 | 1.0 |
| `INSUFFICIENT_EVIDENCE` / `FAILED` | 0.45 | 0.35 |

`evidence_completeness`: 0.2 without evidence refs; else 1.0 when `checks` captured — **not** a function of `coverage_ratio`.

---

## 9. Deterministic OSD

[`DeterministicOSDMapper`](../backend/app/osd/deterministic.py) copies Explainability metadata read-only. **O = S = D = null**. No FRIES.

---

## 10. Legacy Compatibility

- `legacy_heuristic` path unchanged; empty-card `(2,2,3)` remains legacy-only
- Historical JSON artifacts not rewritten
- `coverage_ratio` retained in metrics for API/runner compatibility

---

## 11. Files Changed

| File | Role |
| ---- | ---- |
| `backend/app/probes/explainability_stats.py` | Constants |
| `backend/app/probes/explainability_eval.py` | Pure evaluation |
| `backend/app/probes/explainability.py` | Layer-A probe wiring |
| `backend/app/probes/explainability_card.py` | Matcher (`pipeline_tag` demoted) |
| `backend/app/confidence/engine.py` | `_explainability_factors` |
| `backend/app/osd/deterministic.py` | Metadata key copy |
| Tests + README | Assertions and docs |

---

## 12. Explicit Non-Goals

- Runtime explanation artifacts (Track 2)
- `explainability_score_0_10`
- coverage → O/S/D on default path
- FRIES / O mapping for Explainability
- Changes to Fairness, Robustness, Integrity, Safety

---

## 13. Definition of Done

- [ ] `tl-explainability-v1.0` on new runs
- [ ] `scored_risk_id is None` always
- [ ] `aspect_scoring` uses `risk_detected`, never `scored_risk`
- [ ] Empty card → `INSUFFICIENT_EVIDENCE`
- [ ] Coverage is measurement only
- [ ] Confidence not coverage-driven
- [ ] Deterministic O/S/D null
- [ ] Legacy heuristic isolated from new probe
- [ ] Tests pass
