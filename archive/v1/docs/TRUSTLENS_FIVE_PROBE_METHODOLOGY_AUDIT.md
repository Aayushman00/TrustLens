# TrustLens Five-Probe Methodology Audit

**Status:** analysis / recommendation only. Not an implementation plan and not a code change.  
**Does not modify** existing methodology files.  
**Does not implement** Integrity, Explainability, or Safety probes.  
**Audience:** the document from which Integrity, Explainability, and Safety *implementation plans* will be derived.

**Date:** 2026-09-07

---

# 1. Executive Summary

Fairness and Robustness already implement the intended TrustLens shape: **measure → gate → named risk → abstain from O/S/D unless a validated mapping exists**. Integrity, Explainability, and Safety do **not**. They still behave like Phase 10–14 MVP checklists: they almost always default to `EVALUATED`, emit coverage/pass-rate numbers that look like scores, and (on the isolated `legacy_heuristic` path) collapse those numbers into one O/S/D triple per dimension.

This audit answers three questions:

1. What can TrustLens **scientifically claim** for Integrity, Explainability, and Safety on arbitrary Hugging Face models?
2. What of the current implementation is **legitimate evidence**, what is a **misleading score**, and what is an **unsupported risk claim**?
3. How do the three remaining dimensions become **internally consistent** with Fairness/Robustness and with the locked two-mode architecture?

**Headline recommendations (not yet implemented):**

| Dimension | v1.0 should measure | Must not claim |
| --------- | ------------------- | -------------- |
| **Integrity** | Provenance *disclosure* and *identity recording* (pinned revision, Hub file manifest, structured license, card presence). Cryptographic identity **only** when a trusted reference hash exists. | Tampering, true training-data lineage, true reproducibility, malicious intent |
| **Explainability** | **Documentation / transparency** of the model card (required sections present with non-trivial body; simple consistency flags). | Interpretability quality, explanation fidelity, “the model is explainable/unexplainable” |
| **Safety** | **Safety governance disclosure** on the card (required safety sections; high-impact *claims* as review flags). Behavioral refusal/harm tests only as **research-preview**, scoped to a pinned prompt suite. | “The model is safe,” effective mitigation, FRIES2 safety caps |

**O/S/D (locked):** no Integrity / Explainability / Safety dimension currently has an approved, validated O mapping. Deterministic v1.0 therefore records **named risks as Layer A detections** and leaves **O = null, S = null unless human-supplied, D = unavailable**. FRIES remains withheld until required triples exist. This matches Fairness (`F-FAIR-PERF` detected, O not assigned) and Robustness (`R-ROB-PERT` detected, O not assigned).

**`integrity_score_0_10`:** demote completely. It is a weighted checklist pass-rate dressed as a 0–10 score. It must not appear as a score field.

**Contradictions that this document does *not* silently resolve** are listed in §10. The most important is: Methodology v1.0 Fairness/Robustness amendment A6 (empty-risk aspects can still be FRIES-complete) versus Phase 1 / two-mode policy (FRIES withheld when O/S/D are incomplete). Code today follows the latter. Future O-mapping activation must choose one rule explicitly.

---

# 2. Authoritative Sources

Sources are ranked. Lower ranks do not override higher ranks.

| Rank | Source | Role |
| ---- | ------ | ---- |
| **1 — Locked architecture** | Two-mode architecture decision (deterministic vs LLM-assisted); Phase 1 Deterministic OSD; this audit’s cross-cutting rules | Binding for O/S/D, evidence vs interpretation, versioning |
| **2 — Settled F/R methodology** | [`docs/TRUSTLENS_METHODOLOGY_V1_0_FAIRNESS_ROBUSTNESS.md`](TRUSTLENS_METHODOLOGY_V1_0_FAIRNESS_ROBUSTNESS.md) **as amended by** [`docs/TRUSTLENS_METHODOLOGY_V1_0_AMENDMENTS.md`](TRUSTLENS_METHODOLOGY_V1_0_AMENDMENTS.md) **and as implemented** in Fairness pairing + Robustness Phase 2 | Binding pattern for Layer A, gates, named risks, status taxonomy, “no_material_risk ≠ abstention” |
| **3 — Frozen FRIES math** | `backend/app/scoring/fries.py`, `shared/scoring/fixtures/fries_test_vectors.json` | Binding aggregation math. **Out of scope to change.** |
| **4 — Current I/E/S code** | `integrity.py`, `explainability.py`, `explainability_card.py`, `safety.py`, `safety_card.py`, `card_markdown.py`, tests | Facts about what the product *does today* |
| **5 — Historical / proposed** | [`docs/TRUSTLENS_IMPLEMENTATION_BLUEPRINT.md`](TRUSTLENS_IMPLEMENTATION_BLUEPRINT.md), README “target architecture,” `docs/results_chapter.md`, `docs/RESULTS_SUMMARY.md`, HeuristicOSDAgent docstrings | **Not authoritative.** Useful as a catalog of problems and rejected ideas. |

**There is no settled Integrity / Explainability / Safety methodology document today.** Methodology v1.0 explicitly says it does not cover those three dimensions. This audit is the proposed methodological authority from which those specs will be written. It is **not** itself folded into the Fairness/Robustness spec.

**Code vs README drift (do not treat README as current):** README still says statuses are not first-class and that there is no shared inference backend. Both are stale relative to Fairness pairing and Robustness Phase 2.

---

# 3. Locked Cross-Cutting Architecture

These rules are **already accepted**. This audit does not reopen them.

1. **Evidence first:** objective measurement → evidence → uncertainty / validity → named risk → O/S/D only where justified → FRIES later.
2. **Missing evidence is not poor evidence.** Do not map empty cards or skipped probes to low O/S/D bands such as `(2,2,3)`.
3. **Technical failure ≠ insufficient evidence.** Load/inference/store crashes are `FAILED`.
4. **Proxy ≠ direct / model-faithful evaluation.** Label it; never let proxy numbers enter FRIES.
5. **Raw metrics ≠ FRIES score.** Coverage ratio, pass rate, hash, and refusal rate are Layer A.
6. **Arbitrary thresholds must not be presented as scientifically validated.** If used as gates, label them uncalibrated (same pattern as Fairness `ε = 0.02`, Robustness `ε_drop = 0.05`).
7. **Hash mismatch ≠ proof of tampering.** Bytes differ vs a stated reference. Intent is not measured.
8. **Documentation coverage ≠ proof of actual explainability.**
9. **Keyword presence ≠ proof of safety mitigation.**
10. **One measurement must not support a broader risk claim than it measures.**
11. **O/S/D:** O deterministic where a **validated** formula exists (none currently approved for I/E/S). S human-controlled unless/until the experimental LLM-assisted S path is implemented and validated. D unavailable in v1.0. No AI-generated D. No fake numeric defaults (`S=5`, `D=8`, empty-card `(2,2,3)`).
12. **Deterministic Mode** must complete without LLM assistance.
13. **LLM-assisted Mode** is interpretation only on an immutable evidence snapshot (no measurement, inference, metrics, gates, D, or auto-finalize).
14. **`methodology_version` and `ai_config_version` are separate.**
15. **Fairness and Robustness implementations are the architectural reference**, not something to rewrite.

**Assessment engines in code today:** `deterministic` (default) and `legacy_heuristic` (explicit compatibility). The accepted two-mode names are `deterministic` and `llm_assisted`. `legacy_heuristic` is **not** Mode B; it is a frozen historical mapping path. This audit does not change that.

---

# 4. Fairness Baseline

**What is measured (implemented):** group disparity on a **declared** pairing (`supported_pairings_v1.yaml`) or Adult **proxy** path.

**Evidence source:** pinned dataset + `InferenceBackend` (model-faithful) or sklearn LR (proxy).

**Named scored risk:** `F-FAIR-PERF` (multiclass: `subgroup_worst_group_acc_gap`). Binary DP/EO remain evidence; F1 is not scored.

**Gates:** `G-FAIR-N-TOTAL`, `G-FAIR-N-GROUP`, `G-FAIR-CI-WIDE`, pairing/task checks.

**Uncertainty:** bootstrap CI on gap; Wilson per-group accuracy.

**Status:** `EVALUATED` (including `no_material_risk` and `mapping_blocked`); `INSUFFICIENT_EVIDENCE`; `NOT_APPLICABLE`; `FAILED`; `PROXY` (metrics allowed, no FRIES).

**O/S/D:** probe may set `scored_risk_id`; DeterministicOSDMapper copies metadata; **O/S/D remain null**. `scale_linear` / FR-PERF mapping is **PROPOSED / REQUIRES VALIDATION** and is **not activated**.

**This is the pattern Integrity / Explainability / Safety must copy.**

---

# 5. Robustness Baseline

**What is measured (implemented):** paired clean vs char-swap accuracy on an **explicit** dataset (`probe_config.datasets.robustness` or `supported_robustness_compat_v1.yaml`). No metadata-inferred domain.

**Named scored risk:** only `R-ROB-PERT`. Primary scalar `accuracy_drop`. Trigger: `drop > 0.05` AND bootstrap `ci_lower > 0.05`. `B=1000`.

**Gates:** `G-ROB-N-EVAL`, `G-ROB-LABEL-COMPAT`, `G-ROB-CLEAN-FLOOR`, `G-ROB-CI-WIDE`, `G-ROB-DOMAIN`, complete perturbation coverage.

**Status split:** zero eligible rows → `INSUFFICIENT_EVIDENCE`; model/dataset/inference crash → `FAILED`.

**O/S/D:** `R-ROB-PERT` detection ≠ O assigned. RR-PERT-01 / `scale_linear` **out of scope**.

**This is the second reference implementation.** Card-checklist probes must grow **gates, named risks, and honest status**, not a 0–10 “integrity/explainability/safety score.”

---

# 6. Integrity Methodology Audit

## 6.1 What Integrity means in TrustLens v1

**Definition (proposed, for this document):** Integrity is the **trustworthiness of *identity, provenance, and disclosure*** of the artifact under evaluation — not a general “the model was not tampered with” verdict, and not a cybersecurity attestation.

FRIES historically talks about integrity risks such as *tampering cannot be ruled out*, *output uncertainty*, *change traceability*, and *data/label uncertainty*. Those names are **historical FRIES catalog language** (README / blueprint). They are **not** a settled TrustLens measurement spec. Using them as scored v1.0 risks would violate rule 10 unless TrustLens actually measures those phenomena.

**v1.0 Integrity is therefore two layers:**

| Layer | Question TrustLens may answer |
| ----- | ----------------------------- |
| **Disclosure / recording** | Did the Hub record a pin, a file list, a license, a card, and reproducibility *claims*? |
| **Cryptographic identity (conditional)** | If and only if a **trusted reference hash** exists, do local bytes match it? |

Anything about intent, true lineage, or “cannot rule out tampering” is **not a v1.0 scored claim**.

## 6.2 Current implementation (facts)

Module: [`backend/app/probes/integrity.py`](../backend/app/probes/integrity.py).

- **Metadata only.** Never downloads weights. Never hashes model files.
- Six equally weighted checks: `revision_pinned`, `files_listed`, `license_declared`, `card_present`, `reproducibility_claims`, `checksum_recorded`.
- Emits `integrity_score_0_10 = 10 - fail_count * (10/6)`, `pass_count`, `fail_count`, `proposed_mapping: True`.
- `checksum_recorded` **passes** if the Hub `files` list is non-empty. The “checksum” is `sha256` of the **sorted filename list**, plus the recorded Hub revision string. It is **not** SHA-256 of weights, and **not** a comparison to a trusted reference.
- `reproducibility_claims` passes if ≥2 keyword groups hit in card text / `card_data`.
- `license_declared` requires a **structured** license field; card-only “MIT” language is an anti-gaming **fail**.
- Default `ProbeOutput.status` is **`EVALUATED`** (never set). Empty files + empty card still produce a numeric score.
- Tests (`test_integrity_probe.py`) assert the score goes up/down with checklist items — they encode the misleading score.
- HeuristicOSDAgent (legacy only): `O = S = scale(pass_rate)`, `D = 8`.

Internal MinIO evidence SHA (`verify_artifact`) is **TrustLens artifact integrity**, not model Integrity. Do not conflate the two.

## 6.3 Evidence-type inventory

| Evidence type | Present today? | What it actually shows |
| ------------- | -------------- | ---------------------- |
| Model revision pinning | Yes (string present, SHA-like regex) | A revision identifier was recorded. Not that Hub content is immutable forever. |
| Repository provenance | Partial (`model_ref`) | Hub repo id. Not author authenticity. |
| Artifact/file manifest | Yes (`files` list) | Hub listed filenames at import time. |
| Local downloaded artifact identity | **No** | Import does not download weights. Robustness/Fairness may download at probe time without Integrity hashing. |
| SHA-256 verification vs trusted reference | **No** | Filename-list fingerprint only. |
| Trusted reference provenance | **No** | No registry of expected hashes. |
| Training-data provenance disclosure | Keyword group only | Disclosure language, not lineage. |
| Reproducibility disclosure | Keyword groups | Disclosure, not a reproduction run. |
| Model/config metadata consistency | Weak (`license_card_mismatch` flag) | Phrase vs structured license. |
| Revision-to-revision change traceability | **No** | Single snapshot. |
| Output/label uncertainty | **No** | Would need inference + labels. |
| Unauthorized artifact tampering | **No** | No independent baseline. |
| Annotation/data provenance | **No** | Not in Hub metadata for arbitrary models. |

## 6.4 Per-check / per-risk table

| Risk / check | Evidence required | Metadata-only? | Requires download? | Requires inference? | Deterministically measurable? | Current status | v1 recommendation |
| ------------ | ----------------- | -------------- | ------------------ | ------------------- | ----------------------------- | -------------- | ----------------- |
| Revision unpinned | Missing/non-SHA revision | Yes | No | No | Yes (presence + format) | Implemented as checklist item | **KEEP as disclosure risk** `I-INT-REV-UNPINNED` |
| Empty Hub file list | `files` empty | Yes | No | No | Yes | Fail `files_listed` | **KEEP** `I-INT-MANIFEST-MISSING` |
| License undisclosed | No structured license | Yes | No | No | Yes (field presence) | Implemented (anti-gaming) | **KEEP** `I-INT-LICENSE-UNDISCLOSED` |
| Card absent | `card_text` empty | Yes | No | No | Yes | Checklist item; still `EVALUATED` | **KEEP as evidence**; empty card → status rules in §6.8, not a fake low score |
| Repro disclosure thin | <2 keyword groups | Yes | No | No | Yes as **disclosure**, not science | Keyword pass | **DEMOTE** to disclosure evidence; optional named risk `I-INT-REPRO-UNDISCLOSED` with explicit claim boundary |
| Filename-list fingerprint | Sorted names | Yes | No | No | Yes (identity of *listing*) | Misnamed `checksum_recorded` **pass** | **RENAME**; never call this a checksum of the model |
| Weight SHA vs Hub oid | Local bytes + Hub LFS/sha | No | Yes | No | Yes **if** Hub publishes a hash | Absent | **ADD conditionally**; no reference → **do not claim identity verified** (`INSUFFICIENT` for that claim) |
| Bytes diverge vs trusted reference | Local SHA ≠ reference SHA | No | Yes | No | Yes | Absent | **ADD** `I-INT-BYTES-DIVERGE` — claim = bytes differ |
| Tampering / unauthorized change | Independent attested baseline + chain of custody | No | Yes | No | **Not with current architecture** | Historical FRIES name in README | **DO NOT SCORE** |
| True training lineage | Dataset attestations, licenses, chain | Usually no | Maybe | No | **Not for arbitrary HF models** | Keywords | **DO NOT SCORE** |
| True reproducibility | Rerun training under recorded seeds | No | Yes | Yes | **Not in v1.0** | Keywords | **DO NOT SCORE** |
| Output/label uncertainty | Predictions + labels / entropy protocol | No | Yes | Yes | Conditionally (new probe) | Absent | **DEFER** |
| Change traceability | ≥2 pinned revisions compared | No | Maybe | No | Conditionally | Absent | **DEFER** |
| Config vs loaded `num_labels` | `config.json` vs `LoadedModelInfo` | Partial | Yes (load) | Load, not predict | Yes when a backend loads | Fairness/Robustness load without Integrity | **DEFER or conditional ADD** when inference already runs — still not “tampering” |

### A / B / C

**A — can measure now (metadata):** revision string, file-list presence, structured license, card non-emptiness, reproducibility *keyword disclosure*, filename-list fingerprint, Hub `model_ref`.

**B — can measure only conditionally:** SHA-256 of downloaded files vs a **published** Hub hash or an operator-supplied trusted reference; config/head consistency if the model is already loaded for another probe.

**C — cannot scientifically establish with current architecture:** unauthorized tampering, true data lineage, true reproducibility, malicious intent, annotation provenance, output uncertainty, “integrity of the model” as a single 0–10.

## 6.5 `integrity_score_0_10`

**Recommendation: REMOVE as a score field** (demote the underlying counts).

| Option | Verdict |
| ------ | ------- |
| Keep as 0–10 “integrity score” | **Forbidden** (rules 5, 6, 10) |
| Rename to `checklist_pass_rate` | Acceptable **evidence**, if UI never plots it as FRIES/O |
| Remove from `metric_values` entirely | Preferred for v1.0 surface; keep `pass_count` / `fail_count` / per-check dict |

Equal-weight `10 - fail_count * 10/6` is an arbitrary scoring function. It is not Occurrence.

## 6.6 Proposed Integrity risk taxonomy (v1)

Claim boundary is part of the risk. If the claim cannot be evidenced, the risk must not fire.

### `I-INT-REV-UNPINNED`

- **Name:** Unpinned or non-content-addressed revision  
- **Claim:** TrustLens does not have a SHA-like revision identifier for this evaluation.  
- **Evidence:** `model_revision` / Hub revision string.  
- **Detection:** missing, or not matching a documented SHA-like pattern (same regex family as today).  
- **Status:** `EVALUATED` with risk flagged if other identity evidence exists; if *no* identity fields exist at all, `INSUFFICIENT_EVIDENCE`.  
- **Uncertainty:** none (deterministic presence check). Label threshold “SHA-like” as a **heuristic format check**, not cryptographic proof.  
- **Mapping:** **not eligible** (no validated O formula).  
- **Human:** optional review of floating tags (`main` / `latest`).

### `I-INT-MANIFEST-MISSING`

- **Name:** Hub file manifest unavailable  
- **Claim:** TrustLens could not record a Hub file listing.  
- **Evidence:** `files` list.  
- **Detection:** empty/missing.  
- **Status:** `INSUFFICIENT_EVIDENCE` for identity-recording claims that depend on a manifest.  
- **Mapping:** not eligible.

### `I-INT-LICENSE-UNDISCLOSED`

- **Name:** Structured license not declared  
- **Claim:** No structured license field was present (card-only slogans do not count).  
- **Evidence:** `license` / `card_data.license`.  
- **Detection:** current anti-gaming logic (KEEP).  
- **Status:** `EVALUATED` + named risk (disclosure gap is measurable).  
- **Mapping:** not eligible.  
- **Note:** This is **not** “the model is illegally licensed.”

### `I-INT-REPRO-UNDISCLOSED`

- **Name:** Reproducibility disclosure below v1 heuristic floor  
- **Claim:** Card/metadata did not mention ≥2 of {training data, seed, evaluation, hyperparameters} **as text**.  
- **Evidence:** keyword groups (KEEP as evidence, **relabel**).  
- **Detection:** `< 2` groups.  
- **Status:** `EVALUATED` + risk **or** evidence-only flag. **Preferred:** evidence-only flag `thin_reproducibility` rather than a scored risk, because the floor `2` is arbitrary (rule 6). If kept as a named risk, the report must say “uncalibrated disclosure heuristic.”  
- **Mapping:** not eligible.  
- **Must not claim:** the training run is unreproducible.

### `I-INT-HASH-UNVERIFIED` (gate / limitation, not a “tamper” risk)

- **Name:** Cryptographic identity not verified  
- **Claim:** TrustLens did not compare local bytes to a trusted reference.  
- **Evidence:** absence of reference hash **or** weights not downloaded.  
- **Detection:** no trusted reference in a versioned registry / Hub oid.  
- **Status:** **`INSUFFICIENT_EVIDENCE` for the cryptographic-identity claim**; other disclosure checks may still be `EVALUATED`. Do not collapse the whole Integrity aspect to insufficient solely because weights were not hashed — unless the evaluation *claimed* to verify bytes.  
- **Mapping:** not eligible.  
- **This is the correct interpretation of “no trusted reference → INSUFFICIENT_EVIDENCE.”** It applies to the *hash-verification claim*, not to every Integrity check.

### `I-INT-BYTES-DIVERGE`

- **Name:** Local artifact bytes differ from trusted reference  
- **Claim:** SHA-256 (or Hub LFS oid) of downloaded file(s) ≠ the pinned trusted reference.  
- **Evidence:** local hash, reference hash, reference provenance (`source`, `retrieved_at`, `methodology_version`).  
- **Detection:** inequality.  
- **Status:** `EVALUATED`.  
- **Uncertainty:** none if both hashes computed; document algorithm.  
- **Mapping:** not eligible until a validated O formula exists (none in v1.0).  
- **Must not claim:** unauthorized tampering, supply-chain attack, or Hub compromise.

### Risks **not** in v1 scored catalog

| Historical / tempting ID | Why excluded |
| ------------------------ | ------------ |
| `I-INT-TAMPER` / “tampering cannot be ruled out” | No independent baseline; proving a negative is not a measurement |
| Output uncertainty | No protocol; would be a different probe |
| Label/annotation uncertainty | No annotator data |
| Change traceability | Needs multi-revision design |

## 6.7 Evidence artifact (proposed)

```text
probe: integrity
methodology_version: <string>
model_ref, model_revision
identity:
  revision, sha_like: bool
  hub_files: [...]
  files_listing_fingerprint: sha256   # listing identity, not weights
  weight_hash: { algo, value } | null
  trusted_reference: { algo, value, source, retrieved_at } | null
  hash_comparison: match | diverge | not_performed
disclosure:
  license_structured, card_present, card_chars
  repro_groups_found: [...]
checks: { id: { pass, detail } }
risks_triggered: [...]
aspect_scoring: scored_risk | no_material_risk | not_scored | mapping_blocked
reliability.failed_gates: [...]
proposed_mapping: false
integrity_score_0_10: ABSENT
```

## 6.8 Status, invalid, failure, N/A

| Case | Status |
| ---- | ------ |
| Metadata retrieved; checks ran | `EVALUATED` (even if some disclosure risks fire) |
| Empty card **and** empty files **and** no revision | `INSUFFICIENT_EVIDENCE` (cannot record identity) |
| Hash verification requested but no trusted reference | Hash claim `INSUFFICIENT_EVIDENCE`; see §6.6 |
| Hub metadata fetch / evidence store failure | `FAILED` |
| Integrity not meaningful (none in v1 for HF models) | Do not use `NOT_APPLICABLE` as a dump for “we skipped hashing” |
| Non-HF artifact types | Future `NOT_APPLICABLE` if import is not a Hub model |

## 6.9 Tests (required when implemented)

- Per-check pass/fail without asserting a 0–10 score.  
- Card-only license still fails structured license (KEEP).  
- Filename fingerprint ≠ weight hash (regression).  
- No trusted reference → `hash_comparison: not_performed`, no tamper language.  
- Bytes diverge vs fixture reference → `I-INT-BYTES-DIVERGE`, claim text exact.  
- Evidence-store error → `FAILED` / propagate as today.  
- Deterministic OSD: risks visible, O/S/D null, `osd_proposals` empty.  
- Legacy heuristic isolation unchanged.

---

# 7. Explainability Methodology Audit

## 7.1 What “Explainability” means — and why it is dangerous

At least seven different things are routinely collapsed under one FRIES aspect:

| # | Concept | Measurable on arbitrary HF models in v1? |
| - | ------- | ---------------------------------------- |
| 1 | Documentation transparency (card sections exist and are non-empty) | **Yes** (current matcher, if honestly named) |
| 2 | Architecture transparency (architecture described) | **Partially** (bonus section / `card_data`) |
| 3 | Explanation-method *availability* (API, attentions, SHAP) | **Not reliably** from cards; would need code inspection |
| 4 | Actual explanation generation | **No** in current probes; SHAP/LIME out of README non-goals |
| 5 | Explanation quality / fidelity | **No** without a declared explanation method + fidelity protocol |
| 6 | Explanation stability | **No** |
| 7 | Human-understandability | **No** (requires humans) |

**v1.0 TrustLens Explainability, honestly named:** a **documentation / transparency** evaluation of the model card. It is **not** an interpretability benchmark.

If the product label remains “Explainability,” every report must state: *this aspect currently measures documentation completeness, not explanation quality.* Prefer internal risk IDs under `E-DOC-*` so the catalog cannot be misread as `E-EXP-FAITHFUL`.

## 7.2 Current matcher audit

Modules: [`explainability.py`](../backend/app/probes/explainability.py), [`explainability_card.py`](../backend/app/probes/explainability_card.py), [`card_markdown.py`](../backend/app/probes/card_markdown.py).

| Mechanism | Behavior | Methodological standing |
| --------- | -------- | ----------------------- |
| Exact / alias heading match | ATX `#`–`###`, punctuation stripped, alias tables | **Legitimate documentation evidence** if body ≥ `MIN_BODY_CHARS` (20) |
| Synonym matching | Alias phrases per section | **Heuristic.** Aliases like `bias` → `limitations` over-claim. Not validated. |
| Semantic fallback | **None.** No embeddings. `card_data` field fallback only | Do not describe as “semantic” |
| `card_data` fallback | e.g. `pipeline_tag` can satisfy **architecture** | **Weak.** A pipeline tag is not an architecture description. Over-credits transparency. |
| Coverage ratio | `present / 5` over required sections | **Documentation completeness metric**, not an explainability score |
| Missing concepts | Flags `missing_<section>` | Legitimate **gap list** |
| Architecture | Bonus only; not in denominator | Correct as optional evidence |
| Empty card | `coverage_ratio=0`, `empty_card`, still default `EVALUATED`; confidence 0.35 | **Wrong status** (missing evidence ≠ evaluated poor explainability) |
| Thin card | `needs_human_review` if ratio < 0.6 | Arbitrary 0.6 (rule 6). OK as a **review flag**, not a gate pretending to be science |
| Contradictions | Phrase lists vs license / production claims | **Weak consistency flags**, not NLI. KEEP as flags, not O/S/D. |

Required sections: `intended_use`, `limitations`, `training_data`, `evaluation`, `ethical_considerations`.

**Historical damage (Mode B experiment):** coverage 0 with non-empty prose (no ATX headers) mapped to O=S=D=1 via HeuristicOSDAgent. That is exactly “missing headings = unexplainable model.” **Must not recur on the deterministic path.**

## 7.3 Classification of current outputs

| Output | Verdict |
| ------ | ------- |
| Per-section present + matched heading | **KEEP** as documentation evidence |
| `coverage_ratio` | **DEMOTE** — evidence completeness of the card checklist, never “explainability score” |
| `card_chars` | **KEEP** as context |
| Contradictions | **KEEP** as flags; do not map to O |
| `proposed_mapping: False` | **KEEP** |
| Default `EVALUATED` on empty card | **REMOVE** that behavior |
| Agent `(2,2,3)` empty card | **REMOVE** from any default path (legacy-only if retained) |
| Treating `card_data.pipeline_tag` as architecture documentation | **DEMOTE or tighten** — too weak for `present=true` on architecture |
| SHAP/LIME | **DEFER** (README non-goal) |

## 7.4 v1 tracks

**Track 1 — Documentation / transparency (ship).**  
Evidence: section matcher + contradiction flags. Named risks only about **missing or contradictory documentation**.

**Track 2 — Runtime explanation capability (defer).**  
Would require: declared method, pinned inputs, generated attributions, fidelity/stability protocol. Not available for arbitrary HF models in v1.

Do **not** mix tracks into one coverage number.

## 7.5 Proposed documentation risks

### `E-DOC-INCOMPLETE`

- **Claim:** One or more **required documentation sections** are absent or have a trivial body (< 20 characters).  
- **Evidence:** matcher results.  
- **Metric:** per-section booleans; `coverage_ratio` as **supporting count only**.  
- **Validity:** measures headings/fields, not truth of the prose.  
- **Uncertainty:** none; matcher is deterministic given card text. Alias table version must be in `methodology_version`.  
- **Status:**  
  - Empty card → `INSUFFICIENT_EVIDENCE` (no document to evaluate).  
  - Non-empty card, some sections missing → `EVALUATED` + risk.  
  - All required present → `EVALUATED` + `no_material_risk` **for this documentation risk only**.  
- **Mapping:** not eligible.  
- **Must not claim:** the model has/has-not faithful explanations.

### `E-DOC-CONTRADICTION`

- **Claim:** Card text contains a **keyword-level** conflict (open-use language vs restrictive license; production-ready language without a limitations section).  
- **Evidence:** `detect_contradictions`.  
- **Validity:** high false-positive/negative risk; **heuristic**.  
- **Status:** `EVALUATED` + flag/risk.  
- **Mapping:** not eligible.  
- **Must not claim:** legal noncompliance.

### Not in v1

| Tempting risk | Why not |
| ------------- | ------- |
| `E-EXP-NO-METHOD` | Cannot detect SHAP/attention APIs from cards reliably |
| `E-EXP-UNFAITHFUL` | No fidelity protocol |
| “Model is unexplainable” because card is empty | Empty card = missing documentation, not a property of weights |

## 7.6 Old rules to remove or demote

| Rule | Action |
| ---- | ------ |
| `coverage_ratio` → O=S=D | **REMOVE** from default path |
| Empty card → `(2,2,3)` | **REMOVE** from default path |
| `coverage_ratio < 0.6` as scientific gate | **DEMOTE** to review flag |
| Alias `bias` ⇒ limitations | **TIGHTEN** in a later spec (flag as over-broad; do not silently drop without a spec revision) |
| `pipeline_tag` satisfies architecture | **DEMOTE** (bonus evidence only, not “architecture documented”) |
| Naming this aspect’s metric “explainability score” | **REMOVE** |

## 7.7 Tests (when implemented)

- Empty card → `INSUFFICIENT_EVIDENCE`, no O/S/D, no `(2,2,3)`.  
- Complete ATX card → `no_material_risk` for `E-DOC-INCOMPLETE`.  
- Prose without headings → missing sections (honest), not O=1.  
- Contradiction fixtures KEEP.  
- `coverage_ratio` not shown as FRIES.  
- Deterministic OSD copies risks; O null.

---

# 8. Safety Methodology Audit

## 8.1 Two families that must not be one metric

| Family | Question | v1 |
| ------ | -------- | -- |
| **Safety governance (documentation)** | Does the card disclose misuse, privacy, security, data sources? Does it claim high-impact uses? | **Ship** as disclosure evidence |
| **Behavioral safety** | Does the **imported model** refuse / complete harmful prompts in a declared category? | **Research-preview / optional**; not default CI; not a generic “safety score” |

Collapsing them into `coverage_ratio` is the same error as collapsing Fairness into “one number from the card.”

## 8.2 Current governance implementation (facts)

Modules: [`safety.py`](../backend/app/probes/safety.py), [`safety_card.py`](../backend/app/probes/safety_card.py).

- Required: `misuse_risks`, `privacy`, `security_warnings`, `data_disclosure` (denominator 4).  
- Bonus: `bias_and_fairness_risks`, `human_oversight`.  
- Matcher: ATX aliases; `ethical_considerations` **does not** satisfy `misuse_risks` (KEEP — good claim-boundary instinct).  
- `high_impact_claims`: substring hits (`healthcare`, `medical`, `production ready`, …).  
- `needs_human_review` if coverage < 1.0 **or** any high-impact claim.  
- `proposed_mapping: False`. FRIES2 caps explicitly not applied (KEEP).  
- Default status `EVALUATED`. Empty card → `empty_card` + ratio 0.  
- HeuristicOSDAgent: scale(coverage); high-impact lowers **S by 2 and D by 1**. Amendment A4 already forbade Safety-card adjustment of Fairness S; the same logic forbids using high-impact keywords to mint Safety S/D on the default path.

## 8.3 What keyword detection can and cannot establish

| Observation | Establishes | Does not establish |
| ----------- | ----------- | ------------------ |
| Heading “Privacy” with ≥20 chars | A privacy **section exists** | GDPR compliance, PII handling in training |
| Word “mitigation” | The token appears | Effective mitigation, residual risk |
| “healthcare” / “clinical” | High-impact **language** on the card | That the model is a medical device, or that it is unsafe in clinic |
| Missing “Security” heading | Disclosure gap | That the model is insecure |
| Coverage = 1.0 | All four headings had bodies | The model is safe |

## 8.4 Behavioral safety — what would be required (and what v1 should not fake)

| Requirement | v1 verdict |
| ----------- | ---------- |
| Pinned prompt set | **Required** if the path ships; versioned YAML; no floating GitHub gists |
| Source/licensing | **Required**; many red-team sets are restricted. No pin → **do not ship** |
| Task/model compatibility | Generative vs encoder-only. BERT-style classifiers **cannot** take open-ended harm prompts. Default: `NOT_APPLICABLE` for non-generative heads |
| Refusal definition | Must be operational (string match, “I can’t”, empty, safety token). Arbitrary. Must be documented as uncalibrated |
| Harmful completion definition | Same; severity labels need a codebook — **human or frozen labels**, not an LLM judge in Deterministic Mode (two-mode lock) |
| Per-category metrics | Refusal rate / harmful-completion rate **per declared category** |
| Minimum n | If shipped, follow a documented floor (Fairness/Robustness style). Do not score n=5 |
| Uncertainty | Wilson or bootstrap on rates |
| Over-refusal | Separate metric; do not call high refusal “safe” |
| Reproducibility | Seed, prompt order, decoding params pinned |
| Inference backend | Existing `InferenceBackend` only — no second transformers path |
| Generic vs model-specific prompts | Generic suites **over-claim** on arbitrary HF models. Scope the risk ID to the suite name + category |

**Can behavioral testing be valid for arbitrary Hugging Face models?**  
**No.** It can be valid for **a declared model class** (e.g. instruction-tuned causal LMs) against **a declared prompt suite**. Encoder-only text classifiers, vision models, and token-classifiers are `NOT_APPLICABLE` for that suite.

**v1 recommendation:** do **not** make behavioral safety a default probe requirement. Governance path ships first. Behavioral path is **research-preview**, `SKIPPED` unless explicitly enabled and compatible.

## 8.5 Proposed Safety risk taxonomy

### Governance (v1)

#### `S-GOV-DISCLOSURE-GAP`

- **Claim:** One or more **required safety-disclosure sections** are missing or trivial.  
- **Evidence:** `SAFETY_REQUIRED` matcher.  
- **Status:** empty card → `INSUFFICIENT_EVIDENCE`; else `EVALUATED` + risk or `no_material_risk` for this risk.  
- **Mapping:** not eligible.  
- **Must not claim:** the model is unsafe / safe.

#### `S-GOV-HIGH-IMPACT-CLAIM`

- **Claim:** Card contains listed high-impact phrases.  
- **Evidence:** `detect_high_impact_claims` (heuristic).  
- **Status:** `EVALUATED` + **flag** (prefer flag over scored risk). Use as `needs_human_review`, not as O/S/D.  
- **If combined with incomplete disclosures:** still a **governance inconsistency**, not “high harm proven.” Optional composite flag `high_impact_without_full_disclosure`.  
- **Mapping:** not eligible.  
- **Must not** lower Fairness S (A4). Must not invent D.

### Behavioral (research-preview only)

#### `S-BEH-HARM-COMPLETION-<SUITE>-<CATEGORY>`

- **Claim:** On pinned suite `<SUITE>`, category `<CATEGORY>`, harmful-completion rate exceeds a **declared uncalibrated** floor with CI lower bound above that floor (same trigger shape as F/R).  
- **Evidence:** model outputs on pinned prompts via `InferenceBackend`.  
- **Status:** incompatible head → `NOT_APPLICABLE`; suite missing → `SKIPPED`; load fail → `FAILED`; n too small → `INSUFFICIENT_EVIDENCE`.  
- **Mapping:** not eligible until a validated O study exists.  
- **Must not** be named `S-BEH-UNSAFE` or “model is unsafe.”

## 8.6 Status matrix (Safety)

| Situation | Status |
| --------- | ------ |
| Card present; checklist ran | `EVALUATED` |
| Empty card (governance) | `INSUFFICIENT_EVIDENCE` |
| Behavioral enabled, model not generative | `NOT_APPLICABLE` |
| Behavioral not enabled | `SKIPPED` (behavioral track only; governance still runs) |
| Prompt/dataset load failure; inference crash | `FAILED` |
| Behavioral n below floor | `INSUFFICIENT_EVIDENCE` |

## 8.7 Tests (when implemented)

- Governance: complete vs missing privacy (KEEP existing fixtures).  
- Empty card → insufficient, not O=2.  
- High-impact flag without S/D mutation on deterministic path.  
- Behavioral tests only with `FakeInferenceBackend` in default CI; live suite behind `TRUSTLENS_LIVE_TESTS`.  
- Risk IDs include suite + category.  
- FRIES2 still absent.

---

# 9. Five-Dimension Consistency Matrix

| Dimension | What is measured | Evidence source | Model inference? | Dataset/config | Uncertainty | Validity gates | Risk IDs | O | S | D | FRIES eligibility |
| --------- | ---------------- | --------------- | ---------------- | -------------- | ----------- | -------------- | -------- | - | - | - | ----------------- |
| **Fairness** | Subgroup accuracy gap (multiclass); DP/EO evidence (binary) | Pinned dataset + pairing or Adult proxy | Yes if pairing; **proxy LR otherwise** | `supported_pairings_v1.yaml` / `adult_fairness` | Bootstrap + Wilson | n, groups, CI width, pairing | `F-FAIR-PERF` | null until mapping validated | null unless human | unavailable | Withheld while triples incomplete; PROXY never |
| **Robustness** | `accuracy_drop` under char-swap | Pinned NLP subset | Yes (`LocalHFBackend`) | explicit dataset or `supported_robustness_compat_v1.yaml` | Paired bootstrap B=1000; Wilson acc | n, label compat, coverage, domain, clean floor, CI width | `R-ROB-PERT` | null until RR-PERT-01 validated | null unless human | unavailable | Same withhold |
| **Integrity (today)** | 6 metadata checks + fake 0–10 | Hub metadata | No | None | None | None | *(none — pass_rate)* | legacy: scale(pass); default: null | legacy: =O | legacy: 8 | Default: withheld; legacy: scores |
| **Integrity (v1 target)** | Disclosure + optional hash vs reference | Hub metadata; hashes iff downloaded + reference | No (unless hash-on-load) | optional trusted-hash registry | Hash algo documented; no CI | identity fields; trusted reference for hash claim | `I-INT-*` as §6.6 | null | null unless human | unavailable | Same withhold |
| **Explainability (today)** | Card section coverage | Card markdown | No | Alias tables in code | None | None | *(none — coverage_ratio)* | legacy: scale(coverage) or (2,2,3) | =O | =O or 3 | Default withheld; legacy scores |
| **Explainability (v1 target)** | Documentation completeness | Same matcher, honest naming | No | Versioned alias table | None | empty card → insufficient | `E-DOC-*` | null | null unless human | unavailable | Same withhold |
| **Safety (today)** | Safety section coverage + high-impact keywords | Card markdown | No | Alias + phrase lists | None | None | *(none — coverage)* | legacy: scale(coverage) | lowered if high-impact | lowered if high-impact | Default withheld; legacy scores |
| **Safety (v1 target)** | Governance disclosure; behavioral optional | Card; optional pinned prompts | Behavioral only | `safety_prompts_v1.yaml` if shipped | Wilson/bootstrap if behavioral | empty card; N/A non-generative; n floor | `S-GOV-*`, optional `S-BEH-*` | null | null unless human | unavailable | Same withhold |

### Inconsistencies observed **today**

| Issue | Where |
| ----- | ----- |
| `EVALUATED` means “probe ran” for I/E/S, vs “gates passed / evidence sufficient” for F/R | I/E/S default status |
| Missing card → numeric low band (legacy) vs insufficient (F/R, two-mode) | HeuristicOSDAgent `_EMPTY_CARD_BAND` |
| `integrity_score_0_10` looks like an aspect score; F/R forbid this | Integrity metrics |
| `proposed_mapping: True` on Integrity vs `False` on E/S/F/R | Integrity probe |
| No named risks on I/E/S | vs `F-FAIR-PERF` / `R-ROB-PERT` |
| No uncertainty on I/E/S | vs CIs on F/R |
| Filename fingerprint branded as checksum | Integrity |
| Coverage used as if it were interpretability / safety | E/S + legacy OSD |
| PROXY labeled on Fairness; I/E/S have no equivalent “this is only a card” first-class mode | Product/schema |
| Provenance: F/R have versioned YAML pins; I/E/S alias tables live only in Python | Config discipline |
| Arbitrary floors: Integrity ≥2 repro groups; E coverage 0.6 review; S coverage 1.0 review | Uncalibrated (acceptable if labeled) |

---

# 10. Contradictions and Resolutions

**Rule for this section:** if two normative sources disagree, **stop** and flag. Do not pick a winner unless a *later locked* decision already supersedes an *earlier* document.

### C1. Amendment A4 (`S=5` / `D=5` unvalidated_default on Autonomous) vs two-mode lock (`S` null, `D` unavailable)

- **A4** allowed Autonomous to emit dummy S/D so FRIES could run.  
- **Locked two-mode / Phase 1** forbids fake defaults.  
- **Flag:** A4 is **superseded** for TrustLens v1.0 product policy by the later lock. Do not reintroduce `unvalidated_default` S/D for Integrity/Explainability/Safety.  
- **Not silent:** Fairness/Robustness methodology markdown still contains A4 text in places. Folding A4 vs Phase 1 into one F/R spec is **out of scope of this audit** but remains a documentation debt.

### C2. Amendment A6 (`no_material_risk` is FRIES-complete; reweight; don’t treat empty risk as `Ti=0`) vs Phase 1 (FRIES withheld if any O/S/D missing)

- **A6** wants “measured, nothing above floor” to count as an evidence-complete aspect.  
- **Phase 1 code** withholds FRIES whenever triples are incomplete — which is **always** while O/S/D are null.  
- **Flag: UNRESOLVED at the FRIES-aggregation layer.** Layer A should still distinguish `no_material_risk` from `INSUFFICIENT_EVIDENCE` (A6 is correct *as status semantics*). Whether overall FRIES is withheld is a **product rule** currently implemented as withhold.  
- **This audit must not invent a new FRIES reweighting scheme.** Implementation plans for I/E/S must preserve: (a) A6 status distinction at probe level; (b) current withhold until a later, explicit FRIES-policy decision.

### C3. Historical FRIES Integrity catalog (“tampering cannot be ruled out”) vs measurement capability

- README/blueprint treat those names as the *target* Integrity taxonomy.  
- Current architecture **cannot** establish tampering.  
- **Flag:** historical catalog **must not** be copied into v1 scored risks. This is a methodology narrowing, not a claim that FRIES-the-paper is wrong.

### C4. Blueprint OSD section still describes HeuristicOSDAgent as *the* mapper

- **Superseded** by Phase 1 default `deterministic`. Blueprint is historical.

### C5. Explainability aspect name vs documentation-only measurement

- Product dimension enum is `EXPLAINABILITY`.  
- Measurement is card coverage.  
- **Flag:** keep the FRIES aspect name (enum change would be a schema earthquake) but **risk IDs and UI copy must say documentation/transparency**. Do not resolve by pretending coverage is explainability.

### C6. Safety high-impact keywords vs severity (S)

- Legacy agent lowers S/D. Two-mode: S is human (or future structured LLM-assisted S from **deployment context**, not from card keywords).  
- **Flag:** high-impact phrases are **not** deployment-context schema and **must not** become S.

### C7. Hash verification “INSUFFICIENT if no trusted reference” vs “Integrity probe still EVALUATED on metadata”

- Both can be true if claims are split (see `I-INT-HASH-UNVERIFIED`).  
- **Not a contradiction** if the artifact separates claim scopes. It **is** a contradiction if a single aspect-level status is forced to mean both.

---

# 11. KEEP / ADD / REMOVE / DEMOTE / DEFER

## 11.1 Integrity

**KEEP**

- Metadata-only path that does not pretend to download.  
- Structured-license anti-gaming.  
- Per-check dict with `pass` + `detail`.  
- Recording Hub revision and file list.  
- Evidence JSON in MinIO.  
- Distinguishing card-only license from structured license.

**ADD**

- Explicit `probe_status` / `aspect_scoring` / `risks_triggered` / `failed_gates` (F/R shape).  
- Named risks in §6.6.  
- Trusted-reference schema; `hash_comparison: not_performed | match | diverge`.  
- Split claim: disclosure `EVALUATED` vs cryptographic identity insufficient.  
- Tests that forbid tamper language.

**REMOVE**

- `integrity_score_0_10` as a score.  
- `proposed_mapping: True`.  
- Implicit always-`EVALUATED`.  
- Any default-path mapping of pass_rate → O/S/D.  
- Scored “tampering” risk.

**DEMOTE**

- Reproducibility keyword groups → disclosure evidence, not “reproducible.”  
- `checksum_recorded` → `files_listing_fingerprint`.  
- Confidence bumps from checklist → keep as evidence-strength only, cap when claims unverified.

**DEFER**

- Weight hashing in production import (needs download + Hub oid policy).  
- Multi-revision change traceability.  
- Output/label uncertainty probe.  
- Config vs loaded-head consistency as Integrity (could live with inference metadata).  
- Validated O formula for `I-INT-BYTES-DIVERGE`.

## 11.2 Explainability

**KEEP**

- ATX split + nontrivial body (`MIN_BODY_CHARS`).  
- Required five-section checklist as **documentation** evidence.  
- Contradiction flags (as flags).  
- `proposed_mapping: False`.  
- Bonus sections tracked separately from denominator.  
- Existing card fixtures/tests as matcher regressions.

**ADD**

- Status: empty card `INSUFFICIENT_EVIDENCE`.  
- `E-DOC-INCOMPLETE` / `E-DOC-CONTRADICTION`.  
- Report copy: “documentation coverage, not interpretability.”  
- Version pin for alias tables (YAML or `methodology_version` note).

**REMOVE**

- Default-path coverage → O/S/D.  
- Empty-card `(2,2,3)`.  
- Calling `coverage_ratio` an explainability score in UI/reports.

**DEMOTE**

- `coverage_ratio` → checklist completeness.  
- `needs_human_review` at 0.6 → uncalibrated review hint.  
- `card_data.pipeline_tag` as architecture “present.”

**DEFER**

- SHAP/LIME / attention explanations.  
- Fidelity and stability.  
- Tightening over-broad aliases (`bias` → limitations) until a spec revision lists the new table.  
- Human-understandability studies.

## 11.3 Safety

**KEEP**

- Split required vs bonus checks.  
- `ethical_considerations` ≠ `misuse_risks`.  
- FRIES2 caps not applied.  
- `proposed_mapping: False`.  
- High-impact **detection as a list of phrase ids** (as claims, not harm).  
- Existing safety card fixtures.

**ADD**

- Status semantics matching F/R.  
- `S-GOV-DISCLOSURE-GAP`.  
- Explicit governance vs behavioral tracks in the artifact.  
- `NOT_APPLICABLE` / `SKIPPED` for behavioral.  
- If behavioral ships: pinned licensed suite, category-scoped risk IDs, `InferenceBackend` only.

**REMOVE**

- Coverage → O/S/D on default path.  
- High-impact → automatic S/D penalties.  
- Any “model is safe/unsafe” summary.

**DEMOTE**

- `coverage_ratio` → governance disclosure completeness.  
- Keyword “mitigation” / section presence → disclosure only.

**DEFER**

- Default-on behavioral suite for all HF models.  
- LLM-as-judge for harm.  
- FRIES2.  
- Validated O from refusal rates.  
- Over-refusal as a scored risk until a benign-prompt pin exists.

---

# 12. Unified Evidence Model

Every FRIES probe artifact (F/R already close; I/E/S must match) should carry:

```text
probe, dimension, methodology_version
model_ref, model_revision
status, status_reason
aspect_scoring: scored_risk | no_material_risk | not_scored | mapping_blocked
scored_risk_id, risks_triggered[]
reliability: { gates_passed, failed_gates[] }
uncertainty: {}          # empty object if N/A, never fake CIs
limitations[]
flags[]
metrics / checks / sections   # dimension-specific Layer A
claim_boundary[]             # short strings: what this does NOT show
proposed_mapping: false
```

**Provenance fields (Integrity extra):** `trusted_reference`, `hash_comparison`, listing fingerprint vs weight hash.

**Do not** put O, S, D, or FRIES on the probe artifact.

LLM-assisted mode (future) receives a **snapshot** of this object; it cannot write it.

---

# 13. Unified Status Model

Align I/E/S with F/R:

| Status | Meaning | I/E/S examples |
| ------ | ------- | ---------------- |
| `EVALUATED` | The intended evidence object existed and checks ran. May include triggered risks, `no_material_risk`, or `mapping_blocked`. | Card present; checklist complete or gappy |
| `INSUFFICIENT_EVIDENCE` | Required inputs for the **claim being made** are missing — not a fake low score | Empty card (E/S/I documentation); hash claim without reference; behavioral n too small |
| `NOT_APPLICABLE` | The test is meaningless for this model/task | Behavioral safety on encoder-only BERT |
| `SKIPPED` | Intentionally not run | Behavioral track disabled |
| `FAILED` | Attempted; technical error | Evidence store down; Hub metadata API crash; inference crash |
| `PROXY` | Substitute measurement | **Not used** for card probes (cards *are* the object). Fairness Adult LR remains the PROXY exemplar |

**Missing evidence is not `EVALUATED` with O=2.**  
**Keyword miss is not `FAILED`.**

---

# 14. Unified Risk Model

| Dimension | v1 scored-risk family (detection only) | Evidence-only / flags |
| --------- | -------------------------------------- | --------------------- |
| Fairness | `F-FAIR-PERF` (as implemented) | DP, EO, F1, per-group tables |
| Robustness | `R-ROB-PERT` | clean/robust acc, ASR, relative degradation |
| Integrity | `I-INT-REV-UNPINNED`, `I-INT-MANIFEST-MISSING`, `I-INT-LICENSE-UNDISCLOSED`, `I-INT-BYTES-DIVERGE` | repro keywords, listing fingerprint, `I-INT-HASH-UNVERIFIED` as claim-scope |
| Explainability | `E-DOC-INCOMPLETE`, optional `E-DOC-CONTRADICTION` | `coverage_ratio`, bonus sections |
| Safety | `S-GOV-DISCLOSURE-GAP`; optional preview `S-BEH-HARM-COMPLETION-<SUITE>-<CAT>` | high-impact phrase list, bonus checks |

**At most a small number of named risks per aspect** (FRIES 1–3). Do not score every missing heading as its own FRIES risk if that recreates double-counting: prefer **one** `E-DOC-INCOMPLETE` with a list of missing keys, one `S-GOV-DISCLOSURE-GAP` with missing keys.

**Detection ≠ O.** Same as `R-ROB-PERT`.

---

# 15. O/S/D Policy

Applies to **all five** dimensions on `assessment_engine=deterministic`:

| Component | Policy |
| --------- | ------ |
| **O** | Null unless an **explicitly approved and validated** mapping exists. None exist today for I/E/S. Do not use pass_rate, coverage, or keyword hits. Do not use `scale_linear` analog until a calibration study exists. |
| **S** | Null unless a human supplies it (Assisted review). Future `llm_assisted` S is research-preview from **structured deployment context**, not from model-card safety keywords. |
| **D** | Unavailable. Not 8 “because metadata is auditable.” Not 3 “because empty cards are easy to see.” Those are **audit detectability**, not operational Detection in the FRIES sense (already rejected for Robustness char-swap). |
| **osd_proposals** | Empty on deterministic path. |
| **legacy_heuristic** | May still emit triples; isolated; not default; not a methodology target. |

---

# 16. Unified Five-Probe Pipeline

```text
MODEL IMPORT (Hub metadata; optional later weight download)
    → MODEL/DATA PROVENANCE (revision, files, license recorded)
    → COMPATIBILITY (task, resources, pairing / robustness compat)
    → PROBE ELIGIBILITY (per dimension)
    → EVIDENCE COLLECTION
    → UNCERTAINTY / VALIDITY GATES
    → NAMED RISK DETECTION
    → O/S/D MAPPING WHERE SCIENTIFICALLY JUSTIFIED (none for I/E/S in v1)
    → HUMAN REVIEW WHERE REQUIRED
    → FRIES INTEGRATION (withheld if triples incomplete)
```

### Fairness branch

Eligibility: pairing XOR explicit Adult proxy.  
Collect: predictions + sensitive + labels.  
Gate: n, groups, CI.  
Risk: `F-FAIR-PERF` or `no_material_risk`.  
Proxy: stop before FRIES.

### Robustness branch

Eligibility: text-classification + explicit dataset/compat.  
Collect: paired clean/attack preds.  
Gate: n, label compat, coverage, domain, clean floor, CI.  
Risk: `R-ROB-PERT` or `no_material_risk` / `mapping_blocked`.

### Integrity branch

Eligibility: almost always (HF import).  
Collect: metadata checks; hash only if download + reference.  
Gate: identity fields for disclosure; trusted reference for crypto claim.  
Risk: `I-INT-*` or `no_material_risk` for disclosure family.  
Say **“we recorded identity”** vs **“we could not verify bytes.”**

### Explainability branch

Eligibility: card evaluation is always applicable to Hub models; empty card is insufficient evidence, not N/A.  
Collect: matcher.  
Gate: empty card.  
Risk: `E-DOC-*` or `no_material_risk`.  
Never SHAP in v1.

### Safety branch

Eligibility: governance always (as documentation). Behavioral: generative + suite enabled.  
Collect: matcher; optional prompt eval.  
Gate: empty card; N/A head; n.  
Risk: `S-GOV-*`; optional scoped `S-BEH-*`.

The pipeline must be able to say, without fake scores:

- **we measured it** (`EVALUATED`)  
- **we could not measure it** (`INSUFFICIENT_EVIDENCE`)  
- **the test was not applicable** (`NOT_APPLICABLE`)  
- **the test failed** (`FAILED`)  
- **we skipped it on purpose** (`SKIPPED`)

---

# 17. Implementation Order

Do **not** start with O mappings or behavioral red-teaming.

1. **Status + artifact schema alignment** for I/E/S (probe_status, aspect_scoring, failed_gates, proposed_mapping false, claim_boundary). Empty card / empty identity → `INSUFFICIENT_EVIDENCE`. Evidence-store errors stay `FAILED`.  
2. **Demote misleading scores** (`integrity_score_0_10` removed from API surface; coverage relabeled). Update tests that assert the 0–10.  
3. **Integrity named risks (disclosure only)** + rename checksum field. No download required.  
4. **Explainability named documentation risks** + report wording. Tighten architecture fallback in the same spec pass if desired.  
5. **Safety governance named risks** + high-impact as flag only.  
6. **Deterministic OSD metadata keys** for new I/E/S fields (copy-only). Confirm heuristic isolation tests still pass.  
7. **Confidence engine** for I/E/S: penalize empty card / mapping_blocked analog; do not treat coverage=1 as “high scientific confidence.”  
8. **Reports/UI** — never show coverage/pass_rate as FRIES.  
9. **Optional:** trusted-hash registry + `I-INT-BYTES-DIVERGE` when a download path already exists.  
10. **Optional research-preview:** behavioral safety suite behind config + `NOT_APPLICABLE` matrix.  
11. **Never in this phase:** `scale_linear` for I/E/S, FRIES2, SHAP, AI-generated D, re-enabling empty-card bands.

Fairness and Robustness code is **not** rewritten as part of I/E/S work.

---

# 18. Definition of Done (methodology → later implementation)

An Integrity/Explainability/Safety implementation plan is done only if:

- [ ] Layer A emits named risks or `no_material_risk`, not a dimension score.  
- [ ] Empty/missing evidence uses `INSUFFICIENT_EVIDENCE`, not a low O/S/D band.  
- [ ] `FAILED` is distinct from insufficient.  
- [ ] `NOT_APPLICABLE` / `SKIPPED` exist where scientifically required (especially Safety behavioral).  
- [ ] Deterministic OSD: O/S null, D unavailable, empty proposals, FRIES withheld.  
- [ ] `legacy_heuristic` still isolated.  
- [ ] `fries.py` and fixtures untouched.  
- [ ] Reports state claim boundaries (no tamper, no “explainable model,” no “safe model”).  
- [ ] No implicit dataset/domain inference (already forbidden; I/E/S must not add a MAC-style classifier).  
- [ ] Tests cover the new statuses and forbid tamper/safety-score language in artifacts.

---

# 19. Explicit Non-Goals

- Changing Fairness or Robustness methodology or reopening RR-PERT-01 / FR-PERF O mapping.  
- Modifying original FRIES math.  
- Implementing LLM-assisted mode.  
- Cryptographic signing of reports as a substitute for Integrity.  
- SHAP/LIME, attention-as-explanation, or human interpretability studies.  
- A universal behavioral safety score for all Hugging Face models.  
- FRIES2 safety caps.  
- Proving absence of tampering.  
- Using CI width or AI confidence as Detection.  
- Treating this audit as folded into `TRUSTLENS_METHODOLOGY_V1_0_FAIRNESS_ROBUSTNESS.md` without an explicit follow-on spec.

---

# 20. FINAL RECOMMENDATION

Implement Integrity, Explainability, and Safety as **Layer A evidence probes with honest status and narrowly named risks**, copying Fairness/Robustness architecture, **without** activating O/S/D. Demote every 0–10 or coverage field that currently impersonates a FRIES aspect score.

Until O mappings are separately validated, deterministic TrustLens v1.0 will continue to **withhold FRIES** while still producing **auditable evidence and named-risk detections** on all five dimensions.

---

## Plain answers

**1. What should Integrity measure in TrustLens v1?**  
Identity **recording** and **disclosure** (pinned revision, Hub manifest, structured license, card presence, reproducibility *language*). Cryptographic identity **only** when local bytes can be compared to a **trusted reference**. Never tampering, true lineage, or a 0–10 integrity score.

**2. What should Explainability measure in TrustLens v1?**  
**Model-card documentation / transparency** (required sections with non-trivial bodies; heuristic consistency flags). Not explanation quality, fidelity, or “the model is unexplainable.”

**3. What should Safety measure in TrustLens v1?**  
**Safety-governance disclosure** on the card, plus high-impact *claims* as review flags. Behavioral tests only as optional, category-scoped, licensed, model-class-limited research-preview — never “the model is safe.”

**4. What old methodology must be removed?**  
`integrity_score_0_10`; checksum-as-weight-hash; pass_rate/coverage → O/S/D on the default path; empty-card `(2,2,3)`; high-impact keywords minting S/D; always-`EVALUATED` checklists; scored tampering; calling documentation coverage an explainability or safety score; FRIES2 (already unimplemented — keep it out).

**5. What must be added?**  
F/R-style status, gates, `aspect_scoring`, named `I-INT-*` / `E-DOC-*` / `S-GOV-*` risks, claim-boundary text, hash `not_performed` vs `diverge`, report/UI relabeling, tests for insufficient vs failed.

**6. What remains N/A or INSUFFICIENT_EVIDENCE?**  
Empty cards (I/E/S documentation claims); hash verification without a trusted reference; behavioral safety on non-generative models (`NOT_APPLICABLE`); behavioral path off (`SKIPPED`); output uncertainty, SHAP, true reproducibility, tamper-proofing (insufficient / out of scope — do not fake `EVALUATED`).

**7. Is the resulting methodology internally coherent?**  
**Yes at Layer A and O/S/D**, if I/E/S follow F/R and the two-mode lock. **Not fully coherent at FRIES aggregation** until C2 (A6 vs withhold) is decided explicitly. That decision is **not** made here.

**8. What exact implementation order should we use?**  
See §17: schema/status → demote scores → Integrity disclosure risks → Explainability doc risks → Safety governance risks → OSD metadata copy → confidence/reports → optional hash verify → optional behavioral preview. No O mapping. No Fairness/Robustness rewrite. No `fries.py` changes.

---

*End of audit. Next artifacts should be separate implementation plans for Integrity, then Explainability, then Safety, each derived from this document.*
