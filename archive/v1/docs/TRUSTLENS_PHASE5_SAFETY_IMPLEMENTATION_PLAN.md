# TrustLens Phase 5 — Safety Implementation Plan

This document is the Phase 5 **planning / audit deliverable** for Safety only
(Track 1 governance / documentation disclosure).

**Do not implement Safety probe code until this document is reviewed.**
Do not self-sign-off Phase 5.

---

## 1. Executive summary

Safety v1 can defensibly measure **whether the Hub model card discloses required
safety-related sections** and **whether listed phrases appear as lexical
documentation evidence**. Phrase matches (`high_impact_claims`) are
**documentation metadata flags** only. They do not establish that the model is
high-risk, unsafe, or harmful; that a deployment is safety-critical; that
occurrence, severity, or detectability differ; or that a mitigation is required
or effective.

It cannot defensibly measure whether the model is safe, refuses harm, mitigates
risk, or complies with policy.

That is the same claim family as Phase 4 Explainability (documentation /
transparency), not Fairness/Robustness (runtime rates). Authority:
[`TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md`](TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md)
§8, §11.3, §14–17.
[`TRUSTLENS_METHODOLOGY_V1_0_FAIRNESS_ROBUSTNESS.md`](TRUSTLENS_METHODOLOGY_V1_0_FAIRNESS_ROBUSTNESS.md)
**does not cover Safety**. The blueprint is historical context only.

**Identifier:** `methodology_version = "tl-safety-v1.0"` with
`methodology_basis = "TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md"`. Do **not**
stamp `tl-methodology-v1.0`.

**v1 ships governance only.** Behavioral refusal/harm suites are **deferred /
research-preview**, not a silent half-implementation.

Target architecture (copy Integrity + Explainability wiring):

```text
Hub card_text + card_data
  → evaluate_safety
  → SafetyProbe
  → evidence artifact
  → run_all_probes
  → confidence refine
  → DeterministicOSDMapper (copy metadata)
  → O = null, S = null, D = unavailable
```

---

## 2. Current implementation audit

### 2.1 What Safety measures today

Modules: [`backend/app/probes/safety.py`](../backend/app/probes/safety.py),
[`backend/app/probes/safety_card.py`](../backend/app/probes/safety_card.py).
No `safety_eval.py` / `safety_stats.py`. No LLM judge, no prompts, no inference.

| Observation | How |
| ----------- | --- |
| Required section presence | ATX alias match + body ≥ `MIN_BODY_CHARS` (20) for `misuse_risks`, `privacy`, `security_warnings`, `data_disclosure` |
| Bonus section presence | Same matcher: `bias_and_fairness_risks`, `human_oversight` (not in denominator) |
| `coverage_ratio` | `checks_present / 4` |
| `high_impact_claims` (field name) | Case-insensitive substring on full card (`healthcare`, `medical`, `production ready`, …). Stored as a list of phrase ids — **lexical documentation evidence**, not a risk finding. |
| Local confidence | `0.35 + 0.6 * coverage`; empty card `0.35`; phrase matches + coverage < 1 subtracts `0.15` |
| Status | Never set; `ProbeOutput.status` defaults to **`EVALUATED`** |

KEEP that is already correct: `ethical_considerations` does not satisfy
`misuse_risks`; `proposed_mapping: False`; FRIES2 not applied; matcher fixtures
exist.

### 2.2 Heuristics vs measurement

| Mechanism | Status |
| --------- | ------ |
| Heading + non-trivial body | **Measurement of disclosure presence**, not mitigation quality |
| Alias tables | Heuristic labeler (uncalibrated) |
| High-impact phrases | Lexical documentation metadata flags; **not** harm, unsafety, severity, or deployment class |
| `needs_human_review` if coverage < 1 or any listed phrase match | Uncalibrated product hint |
| `data_disclosure` via `card_data.datasets` | Metadata fallback, same as today |

### 2.3 Keyword presence treated as effectiveness

**Not** treated as “mitigation worked.” The **legacy** OSD path treats phrase
matches as severity (S−2, D−1). Probe confidence treats phrase matches + gaps
as lower `probe_reliability` (0.5) in
[`_card_coverage_factors`](../backend/app/confidence/engine.py). That is still
“keywords change scientific-looking confidence.” **Safety v1 must not carry
that interpretation onto the default path.**

### 2.4 Refusal rate treated as safety

**No.** There is no behavioral path, no refusal metric, no evaluator.

### 2.5 Checklist coverage treated as safety

**Yes, in effect.** `coverage_ratio` is the primary metric; local confidence and
engine confidence scale with it; pipeline tests require it. README still
describes a “mandatory safety disclosure checklist.” Coverage=1 is easy to
misread as “the model is safe.” Audit §8.3: coverage=1 only means four headings
had bodies.

### 2.6 Default EVALUATED despite inadequate evidence

Empty card: `empty_card` flag, `coverage_ratio=0`, confidence 0.35, **status
still EVALUATED**. Same defect Explainability had before Phase 4.

### 2.7 Fake / heuristic O/S/D

**Default path (`DeterministicOSDMapper`):** O/S/D null; copies
`coverage_ratio`, `high_impact_claims`, `checks`. Does **not** invent triples.

**Legacy only (`HeuristicOSDAgent._card_band`, `consider_high_impact=True`):**
`scale(coverage_ratio)` for O=S=D; empty → `(2,2,3)`; phrase matches +
coverage < 1 → S−2, D−1. Encoded in
[`backend/tests/test_osd_agent.py`](../backend/tests/test_osd_agent.py)
(`test_safety_high_impact_with_gaps_lowers_severity_and_detection`). **Keep as
legacy compatibility; do not change `agent.py`.**

### 2.8 FRIES

[`backend/app/scoring/fries.py`](../backend/app/scoring/fries.py) never reads
Safety metrics. FRIES2 caps are unimplemented. Default pipeline withholds FRIES
while OSD triples are incomplete. **No approved Safety → FRIES mapping.**

### 2.9 Confidence today

After runner `refine()`, Safety is the **last remaining user** of
`_card_coverage_factors`:

- `data_quality = coverage` (0 if empty, then floored to 0.1)
- `probe_reliability = 0.4` empty; `0.5` if phrase matches and coverage < 1; else 1.0
- `evidence_completeness = 0.6 + 0.4 * coverage`

Tests that encode this (must be **rewritten**, not preserved as
methodology-valid):

- [`test_safety_empty_card_scores_low`](../backend/tests/test_confidence_engine.py)
- [`test_safety_high_impact_with_gaps_lowers_reliability`](../backend/tests/test_confidence_engine.py)
- [`test_empty_card_soft_path`](../backend/tests/test_safety_probe.py) asserting `confidence == 0.35`

### 2.10 Historical / compatibility

- Phase 14 probe + card fixtures (`model_card_safety_*.md`)
- Stub `StubSafetyProbe` for contract tests only
- README / results chapters describing card heuristics
- Blueprint §9 proposing `safety_behavioral.py` — **not authority**
- Amendment A4: do not map Fairness S from Safety-card phrase matches (already
  respected on default path)

### 2.11 Contracts that must remain

- `coverage_ratio` present (pipeline:
  [`test_evaluate_pipeline_evidence.py`](../backend/tests/test_evaluate_pipeline_evidence.py))
- `checks` dict, `proposed_mapping: false`
- Matcher tests in [`test_safety_card.py`](../backend/tests/test_safety_card.py)
- `ethical_considerations` ≠ `misuse_risks`
- Evidence store errors still **raise**
- Registry still binds `SAFETY` → `SafetyProbe`
- Heuristic isolation tests / `legacy_heuristic` OSD behavior
- F/R/I/E artifacts unchanged

---

## 3. Methodology authority

| Kind | Source |
| ---- | ------ |
| **Normative for Safety v1** | Five-probe audit §8, §11.3, §12–16 |
| **Architecture pattern** | Integrity `tl-integrity-v1.0` + Explainability `tl-explainability-v1.0` (evidence-first, `scored_risk_id` null, `risk_detected`) |
| **Locked elsewhere, do not reopen** | Fairness/Robustness methodology v1.0; two-mode OSD (deterministic default) |
| **Legacy** | `HeuristicOSDAgent` Safety band |
| **Historical / non-authoritative** | Blueprint §9 (especially shipping behavioral + OSD mapping in the same breath) |
| **Proposed / unvalidated** | Any refusal-rate threshold, Wilson floors, `S-BEH-*` triggers, FRIES2 caps |

`tl-methodology-v1.0` is Fairness/Robustness only. Safety gets
**`tl-safety-v1.0`**.

---

## 4. Safety v1 scope (claim boundary)

**Safety v1 claims:** TrustLens inspected Hub `card_text` / `card_data` with a
frozen alias table and recorded which required safety-disclosure headings had
non-trivial bodies, plus which listed phrases matched as **lexical
documentation evidence**.

**Supported:**

- required safety-disclosure section presence
- documentation completeness count
- lexical presence of listed high-impact phrases (documentation metadata flags only)

**Not established:**

- model safety or unsafety
- actual deployment risk
- mitigation effectiveness
- harm severity
- policy compliance
- medical/financial fitness
- refusal capability
- that the model is high-risk or harmful
- that the deployment is safety-critical
- greater occurrence, severity, or different detectability
- that a safety mitigation is required or effective

`high_impact_claims` / phrase matches must **never** be described as evidence of
those “not established” claims. They remain:

- recorded in evidence
- exposed as flags/metadata
- optionally used for the existing uncalibrated `needs_human_review` product hint
- never promoted to `risks_triggered`
- never mapped to O/S/D
- never mapped to FRIES

Two families (audit §8.1) stay **unmerged**:

1. **Governance (v1, default):** documentation disclosure — **ship**.
2. **Behavioral (deferred):** model outputs on a pinned licensed suite — **do
   not implement** in this phase (no YAML, no `safety_behavioral.py`, no LLM
   judge). Enums `NOT_APPLICABLE` / `SKIPPED` already exist for a later preview;
   governance must not fake them.

Risk IDs: use audit names **`S-GOV-*`**, not `S-SAFE-*`. The audit already
assigned canonical IDs; inventing `S-SAFE-*` would fork the catalog.

---

## 5. Exact measurable evidence (governance only)

### M1. Required disclosure completeness

- **What:** count of required checks with `present=true` (heading alias + body
  ≥ 20 chars, or documented `card_data` fallback for `data_disclosure` only).
- **Unit:** count and ratio.
- **Numerator / denominator:** `checks_present` / `4`.
- **Population:** this Hub card snapshot.
- **n:** one card (documentation census, not a sample of model behaviors). No CI.
- **Labels:** matcher output (heuristic), not human gold.
- **Supports:** “these required disclosure sections were / were not present.”
- **Does not support:** safety of the model; quality of the prose; mitigation.

Keep `coverage_ratio` as this **count metric**. Do not emit `safety_score_0_10`
(it does not exist today; do not add it).

### M2. Per-check presence

Same matcher; four required keys + two bonus keys. Bonus never enters the ratio.

### M3. High-impact phrase list (lexical documentation evidence)

- **What:** which `claim_id`s from `_HIGH_IMPACT_PHRASES` matched as substrings.
  Field name remains `high_impact_claims` for compatibility; treat contents as
  **documentation metadata flags**, not risk detections.
- **Unit:** list of phrase ids.
- **Supports:** “the card text contains these listed phrases.”
- **Does not support:** that the model is high-risk, unsafe, or harmful; that
  the deployment is safety-critical; harm severity; occurrence or
  detectability; that a mitigation is required or effective; actual
  medical/financial/legal deployment.

No other metrics for v1 (no refusal rate, no category failure rate, no
evaluator agreement, no `n_evaluated` of prompts). Those belong to deferred
behavioral work and would need a licensed pinned suite before any numerator
exists.

---

## 6. Evidence schema

Copy Explainability/Integrity artifact shape. Persist JSON via existing evidence
store. Metrics on `ProbeOutput.metric_values` must include:

- `methodology_version`, `methodology_basis`
- `probe` / dimension, `evaluation_id`, `model_ref`
- `status` / `probe_status`, `status_reason`
- `checks` (required), `bonus_checks`
- `checks_present`, `checks_required`, `coverage_ratio`, `card_chars`
- `high_impact_claims` (list of phrase ids — lexical documentation metadata,
  not a risk finding)
- `claims`, `claim_boundary`
- `aspect_scoring` ∈ `{not_scored, risk_detected, no_material_risk}`
- `scored_risk_id`: always `null`
- `risks_triggered` (only `S-GOV-DISCLOSURE-GAP` when that detection fires;
  phrase matches never appear here)
- `reliability` (`gates_passed`, `failed_gates`)
- `uncertainty`: `{}` (no fake CIs)
- `limitations[]`, `flags[]`
- `proposed_mapping: false`, `osd_proposals: []`
- `note`

Do not collapse into one Safety score. Relabel README language: coverage is
**disclosure completeness**, not a safety quality score.

---

## 7. Status model

Use **three** statuses for governance v1 (do not auto-use all four of EVALUATED
/ INSUFFICIENT / FAILED / N/A):

| Status | Condition |
| ------ | --------- |
| `EVALUATED` | Non-empty `card_text` after strip (including prose with zero matching headings) |
| `INSUFFICIENT_EVIDENCE` | Empty/missing card |
| `FAILED` | Unexpected eval exception after a persistable artifact is possible; `EvidenceStoreError` still **raises** (pipeline marks evaluation failed) |

**Unused on the governance path (document, do not emit in v1):**

- `NOT_APPLICABLE` — reserved for deferred behavioral tests on non-generative heads
- `SKIPPED` — reserved for deferred behavioral track disabled
- `PROXY` — cards are the object of measurement

Empty card is **not** `EVALUATED` with a low score and **not**
`S-GOV-DISCLOSURE-GAP`.

---

## 8. Gate model

Only one governance gate is justified:

| ID | When | Effect |
| -- | ---- | ------ |
| `G-SAFE-CARD-EMPTY` | `card_chars == 0` | `INSUFFICIENT_EVIDENCE`; `aspect_scoring=not_scored`; do **not** fire `S-GOV-DISCLOSURE-GAP` |

Do **not** add sample-size, evaluator-disagreement, or category-coverage gates
until a behavioral suite exists. Do not add `G-SAFE-*` placeholders for schema
completeness.

---

## 9. Risk model

**The only named Safety v1 risk detection is `S-GOV-DISCLOSURE-GAP`.** Phrase
matches are **not** a second risk (audit §8.5 / §14: prefer flag). They are
never placed in `risks_triggered`.

| ID | Role | Trigger | Not when |
| -- | ---- | ------- | -------- |
| `S-GOV-DISCLOSURE-GAP` | Only named v1 detection; `risks_triggered` | `EVALUATED` and ≥1 required check absent/trivial | Empty card |
| Phrase matches (`high_impact_claims`) | **Documentation metadata flags / lexical documentation evidence only** | Any `_HIGH_IMPACT_PHRASES` substring hit | Promoted to `risks_triggered`, O/S/D, FRIES, or any claim that the model is high-risk/unsafe/harmful |

Also keep/emit:

- `missing_<check>` flags
- `high_impact_deployment_claim` (flag that listed phrases were found on the
  card — **not** a deployment-risk finding)
- optional composite flag `high_impact_without_full_disclosure` when listed
  phrases matched **and** `coverage_ratio < 1` (documentation-completeness
  context for review, **not** proven harm or required mitigation)
- uncalibrated `needs_human_review` when coverage < 1.0 **or** listed phrases
  matched (KEEP as product hint; label uncalibrated)

**Do not ship `S-GOV-HIGH-IMPACT-CLAIM` as `risks_triggered` in v1.** Treat that
ID as **catalog-reserved / unused**.

**Do not ship `S-BEH-*`.** Unvalidated; no suite; no threshold.

`scored_risk_id` **always `null`**. No Safety risk is FRIES-eligible.

`aspect_scoring` (same token set as Explainability, **not** `scored_risk`):

- `not_scored` — insufficient or failed
- `risk_detected` — evaluated and `S-GOV-DISCLOSURE-GAP` in `risks_triggered`
- `no_material_risk` — evaluated and `S-GOV-DISCLOSURE-GAP` did not fire
  (documentation metadata flags such as phrase matches may still be present;
  they do not change `aspect_scoring`)

Document: `risk_detected` ≠ FRIES-scored risk.

---

## 10. Statistical / uncertainty methodology

Governance is a **census of one card**, not a binomial rate. **No
Wilson/bootstrap, no `n_requested`/`n_evaluated` of prompts, no min-n copied
from Fairness.**

`uncertainty: {}`. Wide-CI behavior is **N/A**.

If a later behavioral preview ships, rates would then need suite-scoped n,
Wilson/bootstrap, and an explicit uncalibrated floor — all **deferred /
unvalidated** here. Do not invent those numbers now.

---

## 11. Evaluator validity

| Label source | Role |
| ------------ | ---- |
| ATX alias matcher | Deterministic heuristic over headings |
| `card_data.datasets` fallback | Deterministic metadata |
| High-impact substrings | Lexical documentation metadata flags (not a safety/harm labeler) |
| LLM judge | **Absent; forbidden in Deterministic Mode A** |
| Human labels | Not in v1 |

A heading match is **not** ground truth that the section is an adequate safety
disclosure. Frozen config = Python alias tables in
[`safety_card.py`](../backend/app/probes/safety_card.py) (same provenance
discipline as Explainability: tables live in code unless a later spec versions
them in YAML). Abstention: empty body → `present=false`. Known failure modes:
false heading aliases; “medical” in unrelated prose; missing ATX structure.

---

## 12. Confidence model

Replace Safety’s use of `_card_coverage_factors` with `_safety_factors` parallel
to [`_explainability_factors`](../backend/app/confidence/engine.py). **Leave
Fairness/Robustness/Integrity/Explainability factor functions unchanged.**

Provisional, uncalibrated, **not probabilities**:

**EVALUATED**

- `probe_reliability = 1.0`
- `data_quality = 1.0`

**INSUFFICIENT_EVIDENCE / FAILED**

- `probe_reliability ≈ 0.45`, `data_quality ≈ 0.35` (engine needs non-zero
  weights; same caveat as Integrity/Explainability)

**`evidence_completeness`**

- `0.2` if no evidence refs or `checks` missing/empty
- else `1.0` if required `checks` object was captured

**Forbidden drivers:** `coverage_ratio`, keyword / phrase-match count, checklist
pass rate, refusal rate.

Increasing coverage while status and evidence capture stay fixed **must not**
increase confidence. Phrase-match documentation flags (`high_impact_claims`)
**must not** lower confidence.

Remove probe-local `_confidence()` in `safety.py` (runner overwrites anyway).

If `_card_coverage_factors` has no remaining callers, delete it in the same
Safety-only confidence edit.

---

## 13. O/S/D policy

Deterministic Mode A (default):

- **O = null** (no approved mapping from coverage or keywords)
- **S = null** unless a human supplies S in Assisted review from **deployment
  context**, not from card keywords / phrase matches
- **D = unavailable** (not 8 “because cards are auditable,” not 3 “because empty
  cards are visible”)
- `osd_proposals: []`

AI-assisted / Mode B: read immutable Layer A snapshot; never invent
measurements, risks, O, or D; never auto-finalize Safety. Existing
[`review.py`](../backend/app/osd/review.py) already forbids fabricating O/D on
the deterministic path — **do not change it** unless a Safety-specific bug is
proven.

---

## 14. FRIES policy

- `scored_risk_id = null`
- No automatic FRIES from Safety
- Do not modify [`fries.py`](../backend/app/scoring/fries.py)
- FRIES2 remains out of scope
- No Safety risk → FRIES mapping is approved today

---

## 15. Legacy isolation

| Path | Action |
| ---- | ------ |
| `HeuristicOSDAgent` coverage → O/S/D; empty `(2,2,3)`; phrase-match S/D penalties | **Unchanged**; only `assessment_engine=legacy_heuristic` |
| New `SafetyProbe` | Must not import or call the agent |
| Historical artifacts / fixtures | Keep readable |
| Confidence tests that treat coverage / phrase matches as reliability | Rewrite for v1 semantics |

Do not silently change old heuristic semantics.

---

## 16. API / serialization

- New runs: Layer A fields above; keep `coverage_ratio` and `checks` for
  compatibility
- Deterministic mapper: already copies `high_impact_claims`, `coverage_ratio`,
  `checks`, `claim_boundary`, `methodology_version`. Add `bonus_checks` /
  `checks_present` / `checks_required` to `_PROBE_METADATA_KEYS` if emitted and
  not already covered
- Reports: no code required unless report text currently calls coverage a
  safety score (builder does not special-case Safety today). README must drop
  “checklist = safety” wording and must not describe phrase matches as
  high-risk / unsafe / severity
- Do not change evaluation list/detail contracts except Safety `metric_values`
  growth (additive)

---

## 17. Test matrix

Classify existing tests:

| Test | Class |
| ---- | ----- |
| [`test_safety_card.py`](../backend/tests/test_safety_card.py) (complete, missing privacy, phrase matches, ethical ≠ misuse, card_data fallback) | **Keep** (matcher) |
| [`test_safety_probe.py`](../backend/tests/test_safety_probe.py) coverage compare / phrase-match flags / store error | **Rewrite** probe assertions (keep fixtures); coverage as measurement only; add status/risks |
| `test_empty_card_soft_path` EVALUATED + 0.35 | **Rewrite** → insufficient + `G-SAFE-CARD-EMPTY` |
| `test_safety_empty_card_scores_low`, `test_safety_high_impact_with_gaps_lowers_reliability` | **Rewrite** (must not encode coverage/keyword confidence) |
| `test_osd_agent` phrase-match S/D | **Legacy compatibility — keep** |
| Pipeline `coverage_ratio` / `checks` / `proposed_mapping` | **Keep** |

New/rewritten cases (A–X):

- A complete card → `EVALUATED`, `no_material_risk`, no `S-GOV-DISCLOSURE-GAP`
- B empty/missing card → `INSUFFICIENT_EVIDENCE`, `G-SAFE-CARD-EMPTY`,
  `not_scored`, no disclosure-gap risk
- C N/A for v1 governance (no sample-n gate); document as deferred for behavioral
- D matcher trivial/empty heading body → not present; if card non-empty → gap risk
- E no LLM disagreement path (assert no evaluator fields)
- F prose without headings → `EVALUATED` + `S-GOV-DISCLOSURE-GAP`, coverage 0,
  **not** insufficient
- G missing privacy fixture → gap risk + `missing_privacy`
- H complete fixture → no gap risk
- I `uncertainty == {}`
- J no `safety_score` / 0–10 field
- K `high_impact_claims` are documentation metadata flags / lexical
  documentation evidence; not in `risks_triggered`; not
  “unsafe/high-risk/harmful model”; not `scored_risk_id`; not O/S/D/FRIES
- L coverage is count; not a quality/FRIES score
- M confidence identical when only `coverage_ratio` or the phrase-match list
  changes
- N O/S/D null on deterministic mapper
- O `scored_risk_id is None`
- P no FRIES from Safety metrics
- Q mapper copies metadata only
- R probe source does not reference `HeuristicOSDAgent`
- S Mode B cannot mutate Layer A (existing review tests + no new write path)
- T historical `model_card_safety_*.md` still match matcher
- U runner/pipeline still see `coverage_ratio`, `checks`,
  `proposed_mapping: false`, `probe_status`
- V additive serialization
- W artifacts/README omit “model is safe/unsafe/high-risk/harmful,” “safety
  score,” and any implication that phrase matches change O/S/D
- X F/R/I/E regression (`test_fairness*`, `test_robustness*`, `test_integrity*`,
  `test_explainability*`, `test_osd_agent`, `test_deterministic_osd`,
  `test_confidence_engine`, `test_probe_runner`,
  `test_evaluate_pipeline_evidence`)

---

## 18. Documentation changes

1. This file is the Phase 5 planning deliverable.
2. On **later code implementation**: update
   [`backend/README.md`](../backend/README.md) Safety + confidence tables to
   match Explainability-style evidence-strength wording. Do not describe
   `high_impact_claims` as model risk, unsafety, or severity.

Do not fold Safety into Fairness/Robustness methodology v1.0.

---

## 19. Implementation order (code — later phase)

1. Methodology lock in this markdown (this deliverable)
2. `safety_stats.py` constants (`tl-safety-v1.0`, `S-GOV-DISCLOSURE-GAP`,
   `G-SAFE-CARD-EMPTY`, claims/limitations)
3. Pure `safety_eval.py` (`evaluate_safety`)
4. Rewrite `SafetyProbe` persist + `ProbeOutput.status`; keep
   [`safety_card.py`](../backend/app/probes/safety_card.py) matcher
5. Evidence artifact fields
6. Evaluator: none beyond existing matcher (no new judge)
7. Status/gates as above
8. `_safety_factors` in confidence engine; delete leftover
   `_card_coverage_factors` if unused
9. Deterministic mapper copy keys if needed
10. Tests
11. Confirm heuristic isolation (do not edit `agent.py`)
12. README
13. Focused pytest `test_safety*` + confidence Safety cases
14. Broader F/R/I/E + pipeline + OSD regression

---

## 20. Explicit non-goals

- Behavioral prompt suites, refusal/harm rates, over-refusal
- LLM-as-judge
- Keyword stuffing as safety; checklist → 0–10
- Treating phrase matches as high-risk / unsafe / harm / severity / O/S/D / FRIES
- Automatic O/S/D or FRIES2
- Changing Fairness, Robustness, Integrity, Explainability, `fries.py`, shared
  F/R statistical modules, `HeuristicOSDAgent`
- Broad refactors, YAML alias extraction unless required later
- Self-sign-off

**Non-regression:** touch shared files only for Safety-specific confidence
branch and optional mapper keys; prove non-breaking via existing F/R/I/E tests.

---

## 21. Deferred / unvalidated items

- Default-on behavioral suite; `safety_prompts_v1.yaml`;
  `S-BEH-HARM-COMPLETION-<SUITE>-<CAT>`
- Any numeric harmful-completion floor or CI trigger
- `S-GOV-HIGH-IMPACT-CLAIM` as named `risks_triggered` ID
- Versioned alias YAML
- Tightening phrase lists (e.g. dropping bare `medical`)
- Calibrated confidence
- Validated O from any Safety metric
- Reports/UI redesign beyond README honesty

---

## 22. Acceptance criteria (for a later implementation PR — not claimed now)

Governance Layer A with `tl-safety-v1.0`; empty card insufficient not `(2,2,3)`
on default path; `S-GOV-DISCLOSURE-GAP` is the only named v1 risk detection and
only on evaluable cards; `high_impact_claims` remain documentation metadata
flags (never `risks_triggered`, O/S/D, or FRIES); `scored_risk_id is None`; no
O/S/D/FRIES on deterministic path; confidence not coverage/keyword-driven;
matcher fixtures kept; heuristic agent isolated; F/R/I/E/`fries.py`/
`HeuristicOSDAgent` unchanged; artifacts forbid “model is
safe/unsafe/high-risk” language.

---

## Locked answers (A–M)

**A. Shortcomings:** checklist coverage as implicit safety; always-EVALUATED
empty cards; coverage- and phrase-match-driven confidence; no named
risks/gates; legacy OSD still maps coverage/keywords to O/S/D when enabled.

**B. v1 measurements:** required-section presence counts/ratio; bonus presence;
lexical presence of listed phrases (`high_impact_claims` as documentation
metadata flags).

**C. Risks:** `S-GOV-DISCLOSURE-GAP` only (evidence-layer). Phrase matches are
never `risks_triggered`. Behavioral and `S-GOV-HIGH-IMPACT-CLAIM` deferred.

**D. Gates:** `G-SAFE-CARD-EMPTY` only.

**E. Status:** EVALUATED / INSUFFICIENT_EVIDENCE / FAILED as in §7.

**F. Confidence:** Explainability-shaped provisional weights; not coverage or
keywords.

**G. O/S/D:** null / human S only / D unavailable.

**H. FRIES:** none; `scored_risk_id` null.

**I. Legacy:** HeuristicOSDAgent Safety band + its tests.

**J. Files expected later:** `safety_stats.py` (new), `safety_eval.py` (new),
`safety.py`, `safety_card.py` (docstrings only unless a matcher bug),
`confidence/engine.py` (Safety branch), `osd/deterministic.py` (copy keys),
`test_safety*`, `test_confidence_engine.py` (Safety cases),
`backend/README.md`. This plan file is already written.

**K. Forbidden to modify:** Fairness/Robustness/Integrity/Explainability probe
logic and stats; [`fries.py`](../backend/app/scoring/fries.py);
[`osd/agent.py`](../backend/app/osd/agent.py); shared F/R statistical
methodology; FRIES fixtures.

**L. Tests:** §17.

**M. Unresolved (do not invent):** behavioral suite licensing/source; any
behavioral threshold; whether to later promote phrase matches to
`S-GOV-HIGH-IMPACT-CLAIM`; alias-table YAML provenance.
