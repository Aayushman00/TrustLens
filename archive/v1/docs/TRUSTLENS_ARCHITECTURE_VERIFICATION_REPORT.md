# TrustLens — Independent Architecture Verification / Red-Team Review

**Status:** independent verification. Not an implementation plan. Not a methodology rewrite. Not a sign-off of Phase 6.  
**Date:** 2026-09-07  
**Method:** code first; documents treated as claims to be tested. The implementation blueprint is ignored unless code independently confirms it.  
**Did not:** change code, change `fries.py`, invent O mappings, invent Mode B, invent behavioral Safety, or resolve open methodology questions.

---

# 1. Executive verdict

TrustLens today is **two systems glued together by shared names**.

**Layer A (probes + evidence store + confidence engine + deterministic OSD mapper) is largely coherent.** On the default path it measures evidence, gates it, names detections, abstains from O/S/D, and withholds FRIES. That is scientifically the right shape for an unfinished mapping science.

**The served product (API disclaimers, evaluation UI, reports, leaderboard framing) still describes a Phase 16–22 scoring agent.** Default runs finalize with **no FRIES number**, then tell the user that **O/S/D were generated automatically**, show an **Agent O/S/D suggestion**, hide probe status, and omit claim boundaries. That is not a cosmetic mismatch. It is a **claim-boundary failure**.

The architecture is **not broken at the measurement layer**. It is **not ready to be trusted as a v1 evaluation product**.

| Layer | Verdict |
| ----- | ------- |
| Probe science (F/R/I/E/S as implemented) | **Mostly defensible**, with known uncalibrated floors and one latent binary-fairness hole |
| Default OSD / FRIES | **Correctly abstains / withholds** |
| Confidence engine | **Intent is evidence strength; numbers are engineering weights, not science** |
| Mode A | **Implemented as the default assessment engine** |
| Mode B (`llm_assisted`) | **Does not exist.** Product `AI_ASSISTED` is a human-review workflow, not AI interpretation |
| Legacy heuristic | **Isolated from the UI default; not isolated from the API** |
| API as source of truth | **Persists more than it serves** |
| Frontend honesty | **Fails** for a technically sophisticated user who reads labels, not artifacts |
| Reports | **Honest JSON payload when they exist; dishonest wrapper language; unavailable on the default path** |
| v1 freeze | **No** |

**What is genuinely correct:** default Mode A does not invent numeric O/S/D or FRIES. Probes do not write FRIES. Integrity has no `integrity_score_0_10`. Explainability/Safety confidence is not a function of `coverage_ratio` after engine overwrite. Human review on the deterministic path cannot supply O or D.

**What is only accidentally correct:** FRIES withholding “looks honest” because the mapper always emits nulls, not because A6 vs withhold was decided. Binary fairness pairing would look like methodology v1.0 if someone added an SST-2 pairing tomorrow — it would not be. Flag omission from DB metrics is papered over because the UI never shows flags.

**What is misleading:** “AI-Autonomous”, “Agent O/S/D”, `AUTONOMOUS_DISCLAIMER`, report O/S/D as Operations/Safeguards/Disclosures, README target pipeline presented as current, leaderboard as a trust ranking, blank O/S/D cells, omitted FRIES-withheld state.

**What is scientifically weak:** provisional confidence factors; uncalibrated ε floors (correctly labeled in methodology, invisible in UI); card section/phrase matchers; Integrity `aspect_scoring=scored_risk` with `scored_risk_id=None`.

**What is architecturally dangerous:** authenticated clients can opt into `legacy_heuristic` (and `extra.assessment_engine="heuristic"`) and obtain a complete FRIES from coverage/pass-rate bands, including Integrity/Explainability/Safety. That path is a production escape hatch, not merely historical compatibility.

---

# 2. Architecture reconstructed from code

Discovered structure (names from the repo, not the blueprint):

```text
Frontend (Vite/React)  →  FastAPI /v1  →  Celery worker
                                              │
                                    run_evaluation_pipeline
                                              │
                         run_all_probes F→R→I→E→S
                              │  evidence_store.put_artifact
                              │  confidence.refine overwrites probe.confidence
                              │  probe_results INSERT (no uniqueness)
                                              │
                         resolve_assessment_engine(probe_config)
                              │
              deterministic (default)              legacy_heuristic | heuristic
              DeterministicOSDMapper               HeuristicOSDAgent
              O=S=D=None                           metric→[1,9] bands
                                              │
                         osd_agent_outputs (ai_suggestion, ai_confidence)
                                              │
              AI_ASSISTED ─────────────────────┬── AI_AUTONOMOUS
              AWAITING_REVIEW                  │
              human review (S-only if det.)    │
              finalize                         │
                    │                          │
                    └──── if 5 int O/S/D ──────┤
                         score_from_finalized_osd
                         final_scores
                         else FINALIZED, no row, FRIES withheld
```

**Two orthogonal axes (currently conflated in the UI):**

| Axis | Values in code | What it actually is |
| ---- | -------------- | ------------------- |
| Assessment engine | `deterministic` (default), `legacy_heuristic` | Who proposes O/S/D |
| Evaluation mode | `AI_AUTONOMOUS`, `AI_ASSISTED` | Whether a human must review before finalize |

**Not present:** `llm_assisted`, Mode B snapshot interpreter, AI-written O or D, behavioral Safety suite, composite “TrustLens score” other than original FRIES.

**Authoritative vs non-authoritative**

| Source | Rank for this review |
| ------ | -------------------- |
| Probe eval/stats + runner + mapper + `fries.py` | Authoritative for what is measured and scored |
| Persisted `probe_results` / artifacts | Authoritative for Layer A |
| `GET /v1/evaluations/{id}` + frontend | Authoritative for what users are told |
| Methodology v1.0 + amendments | Binding for F/R Layer A; **A6 conflicts with withhold** |
| Five-probe methodology audit | Binding *intent* for I/E/S; written before I/E/S landed; do not treat §1 “they still behave like MVP checklists” as current code |
| Phase 6 audit | A plan/audit to verify, not a source of truth |
| Implementation blueprint, README “vision” | Historical / target; often stale |

---

# 3. Five-dimension scientific audit

Differences across dimensions are **justified**. Forcing symmetry would be a methodology error. F/R are statistical measurements. I/E/S are documentation/identity disclosure. That split is coherent **if the product says so**. The product currently labels all five as “FRIES probes” and hides the split.

## 3.1 Fairness

| Question | Finding |
| -------- | ------- |
| 1. Measured | Model-faithful pairing: subgroup worst-group accuracy gap (multiclass). Binary pairing: DP/EO/F1 via `compute_fairness_bundle`. Unpaired Adult: sklearn LR **proxy**. |
| 2. Measurable | Yes for rates/gaps on labeled rows with a sensitive attribute. |
| 3. Normatively justified | Disparity measurement is standard. ε=0.02 is an **uncalibrated practical floor** (amendment A5). Not a fairness verdict. |
| 4. Establishes | On HateXplain multiclass: gated gap + bootstrap CI + optional named detection `F-FAIR-PERF`. |
| 5. Does not establish | Fairness of the model, causation, all groups, binary DP/EO as FRIES risks (A1: evidence only). Proxy does not evaluate the imported model. |
| 6. Thresholds | `min_total_n=200`, `min_group_n=50` from dataset pin on pairing; ε=0.02; CI width 0.15. Uncalibrated, documented. Proxy path default `min_group_n=30` is **weaker than the spec** (acceptable only because status is `PROXY`). |
| 7. Uncertainty | Multiclass: Wilson per group + bootstrap gap CI. Binary pairing: **no CIs, no G-FAIR-\* gates, no `aspect_scoring`**. |
| 8. Risk trigger | Multiclass `F-FAIR-PERF` when gap>ε and ci_lower>ε. Does **not** assign O. |
| 9. `scored_risk_id` | Semantically a **Layer A scored-family id**, not a FRIES occurrence. Overloaded word “scored”. |
| 10–11. O/S/D / FRIES | Default: null / withheld. Legacy: gap → O=S, D≈7–8. |
| 12. Confidence | Engine: computed vs skip vs n vs mapping_blocked. Not a fairness quality score. |
| 13. Legacy | Adult `proxy_lr`; HeuristicOSDAgent DP/EO bands. |
| 14. Deferred | Validated O mapping; binary A1 scored-risk selection (EO then DP); regression. |
| 15. User may conclude | “Fairness 0.9 confidence” = model is fair; blank O = fair; PROXY numbers = the HF model. |

**Coherence:** multiclass pairing matches the locked F/R pattern. **Binary pairing is a stub** (`fairness.py` returns `_finish` / `EVALUATED` with a metric bundle). v1 allowlist is HateXplain **multiclass only**, so the stub is latent — but `docs/SUPPORTED_PAIRING_V1.md` says new pairings need no FairnessProbe changes. That sentence is false for binary pairings.

## 3.2 Robustness

| Question | Finding |
| -------- | ------- |
| 1. Measured | Paired clean vs **char-swap** accuracy on an explicit dataset/compat pin. |
| 2. Measurable | Yes as perturbation stability under that attack, not semantic robustness. |
| 3. Justified | As a **declared minimum perturbation** with limitations: yes. As “the model is robust”: no. |
| 4. Establishes | Accuracy drop + paired bootstrap; optional `R-ROB-PERT`. |
| 5. Does not establish | Adversarial robustness, typo-robustness in the wild, domain transfer. |
| 6. Thresholds | ε_drop=0.05; n_eval gate; clean floor (`uninformative_robustness`); CI-wide. Uncalibrated. |
| 7. Uncertainty | Paired bootstrap on drop. Appropriate for this estimator. |
| 8–9. Risk / `scored_risk_id` | `R-ROB-PERT` is a named detection; O still null. Domain mismatch **blocks mapping**. |
| 10–11. O/S/D / FRIES | Default null/withheld. Legacy: scale(clean), scale(robust), scale(degradation). |
| 12. Confidence | n, CI presence, reliability gates — not drop magnitude as “quality”. |
| 13. Legacy | Heuristic bands; skipped attack → abstain. |
| 14. Deferred | Stronger attacks; validated O; A6 FRIES inclusion of `no_material_risk`. |
| 15. User may conclude | Char-swap pass = robust NLP model; `mapping_blocked` = the model is fine. |

**Limits of the claim are in artifacts (`limitations`). They are not on the evaluation UI.** That is a presentation failure, not a probe failure.

## 3.3 Integrity

| Question | Finding |
| -------- | ------- |
| 1. Measured | Hub identity snapshot: revision, file listing, license disclosure, card presence; **conditional** byte compare if operator supplies hashes. |
| 2–3. | Metadata recording is measurable. Not a tamper proof. |
| 4. Establishes | What was disclosed / pinned / listed at evaluation time. |
| 5. Does not establish | Training-data lineage, malware, “not tampered”, reproducibility of training. |
| 6–7. | Empty identity gate. Hash unverified is **claim-scope**, not whole-probe fail. No CI (appropriate). |
| 8. Risk | Named `I-INT-*` detections. |
| 9. `scored_risk_id` | **Always null.** `aspect_scoring` becomes `"scored_risk"` if any named risk. That token is **wrong relative to E/S `risk_detected` and to F/R “scored family”**. It does not emit FRIES. |
| 10–11. | Default null/withheld. Legacy: check pass-rate → O=S, D=8. |
| 12. Confidence | Identity richness + checks dict; hash-unverified 0.85. Not a 0–10 integrity score. |
| 13. Legacy | `integrity_score_0_10` **removed** (tests assert absence). Heuristic pass-rate remains. |
| 14. Deferred | PKI / trusted hash infrastructure; tamper claims. |
| 15. User may conclude | EVALUATED Integrity = the model is authentic. |

**Phase 3 removal of `integrity_score_0_10` is VALID.** The `scored_risk` token is a vocabulary defect, not a scoring backdoor.

## 3.4 Explainability

| Question | Finding |
| -------- | ------- |
| 1. Measured | Track 1: required model-card **section presence** (non-trivial body) + light contradiction flags. |
| 2–3. | Section presence is measurable. It is **not** interpretability. |
| 4. Establishes | Documentation completeness against a heading checklist. |
| 5. Does not establish | Faithfulness, feature attribution quality, “the model is explainable”. |
| 6. | Presence vs `MIN_BODY_CHARS`; coverage_ratio = present/required. Uncalibrated checklist. |
| 7. | No sampling uncertainty (appropriate for a card parse). |
| 8. | `E-DOC-INCOMPLETE`, `E-DOC-CONTRADICTION` as evidence-layer detections. |
| 9. | `scored_risk_id` always null; `aspect_scoring` is `risk_detected` / `no_material_risk` / `not_scored`. **This is the correct token family.** |
| 10–11. | Default null/withheld. Legacy: scale(coverage); empty card → **(2,2,3)** — forbidden on Mode A, still live on legacy. |
| 12. | Engine: status + checks dict + evidence_refs. **Not coverage_ratio** (tests exist). Module **docstring still claims coverage_ratio** — stale. |
| 13–14. | Legacy coverage bands; behavioral/faithfulness eval deferred. |
| 15. | Coverage 1.0 = good explanations. |

## 3.5 Safety

| Question | Finding |
| -------- | ------- |
| 1. Measured | Track 1: four required **safety-governance sections** + lexical `high_impact_claims` as **metadata flags**. |
| 2–3. | Disclosure presence is measurable. Phrase hits are weak evidence of *claims*, not of harm. |
| 4. Establishes | Whether the card mentions required governance topics (by alias match). |
| 5. Does not establish | Model safety, refusal quality, mitigation effectiveness, FRIES2 caps. |
| 6–7. | Same checklist pattern as Explainability. Keywords are explicitly documented as flags. |
| 8–9. | `S-GOV-DISCLOSURE-GAP`; `scored_risk_id` null; `risk_detected` token. Correct. |
| 10–11. | Default null/withheld. Legacy: coverage bands; high-impact **lowers S and D** — keyword → severity. Isolated to legacy. |
| 12. | Same engine shape as Explainability (not coverage, not high-impact). |
| 13–14. | Legacy; behavioral Safety deferred. |
| 15. | Missing sections = unsafe model; “production ready” phrase = high-risk model. |

## 3.6 Are the five dimensions a coherent methodology?

**Yes at Layer A, if labeled honestly.** They are not five copies of the same instrument. They should not be.

**No at the product layer.** The UI treats them as five inputs to a trust score the default run never computes.

**Invariant check (philosophy):**

| Violation to look for | Default path |
| --------------------- | ------------ |
| measurement → quality score | **Avoided** in probes; **reintroduced** in UI as FRIES bars when a score exists |
| documentation → model capability | **Avoided** in I/E/S notes; **invisible**, so users can still infer it |
| keyword → safety | **Avoided** on Mode A; **present** on legacy Safety S/D |
| coverage → confidence | **Avoided** after engine overwrite |
| coverage → quality | **Avoided** on Mode A; **legacy OSD** |
| risk detection → FRIES risk | **Avoided** (O null); Integrity `scored_risk` token muddies this |
| missing evidence → low score | **Avoided** on Mode A (status INSUFFICIENT, no FRIES); **legacy empty-card (2,2,3)** |
| missing O/S/D → 0 | **Avoided** in scorer (row omitted); UI blanks ≠ 0 |
| AI label → ground truth | **No AI measurement**; **labels claim AI anyway** |
| heuristic → scientific measurement | **Default no; API yes** |

---

# 4. Confidence audit

The engine **intends** “evidence strength, not correctness or O/S/D” (`CONFIDENCE_NOTE`, `proposed_calibration: true`).

It is **not**:

- P(model is correct)
- a probe quality score in the FRIES sense
- calibrated

**Factor model:** per dimension, geometric mean of `data_quality`, `probe_reliability`, `evidence_completeness`, each floored at 0.1. Overall: geometric mean of five stored dimension confidences.

**Provisional numeric weights (0.35 / 0.45 / 0.55 / 0.6 / 0.85 / 1.0) are engineering knobs.** They are **not** scientifically justified by being written down as “provisional.” They are defensible only as **ordinal dampers** (failed/insufficient < gated < full run) **if the UI says that**. Today the UI shows `0.93` next to FRIES and a fine-print note.

| Path | Aggregate | Semantic |
| ---- | --------- | -------- |
| `refine` at persist | geo mean of 3 factors | Probe confidence stored on `probe_results` |
| `summarize` on GET | geo mean of 5 stored values | `confidence_summary.overall` |
| Deterministic/heuristic OSD | **arithmetic** mean of 5 aspect confidences | `ai_confidence` / `final_score.overall_confidence` |
| Missing snapshot | **0.2 hardcoded** | Not measured |
| Missing snap.confidence | **0.5 hardcoded** | Not measured |

Showing OSD `overall_confidence` beside FRIES is a **category error**: it is not FRIES certainty.

**Explainability/Safety:** factor functions ignore `coverage_ratio`. **VALID.** Top-of-file docstring still says card `coverage_ratio` feeds `data_quality`. **Incorrect documentation.**

**Fairness `evidence_completeness`:** 1.0 if any evidence_ref (always, because runner requires refs), 0.95 if `needs_human_review`. Amendment A8 wanted completeness tied to primary CI and mapping-not-blocked. **Robustness follows A8 more closely; Fairness does not.** That is a real methodology drift, not a UI issue.

---

# 5. O / S / D audit

| Who | O | S | D |
| --- | - | - | - |
| `DeterministicOSDMapper` | always `None`, source `unavailable` | always `None`, source `None` | always `None`, source `unavailable` |
| `HeuristicOSDAgent` | heuristic int [1,9] or None | same | same; often 7–8 or coverage-scaled |
| Human review, deterministic | **rejected** if supplied | **required** on edit | **rejected** if supplied |
| Human review, legacy | accepted (incl. 0 and 10) | accepted | accepted |
| AI / LLM | **no writer exists** | **no writer exists** | **no writer exists** |
| `fries.py` | never invents | never invents | never invents |

**Null is not converted to 0 in the scorer.** Incomplete aspects are **omitted** from `to_finalized_osd`. FRIES is not called unless five complete triples exist.

**Verbal fabrication is real:** `AUTONOMOUS_DISCLAIMER` says O/S/D “were generated automatically” on the path that stores nulls.

**Default runs do not inherit legacy numeric bands** unless `assessment_engine` resolves to `legacy_heuristic`.

---

# 6. FRIES audit

**Prerequisites (code):** five aspects with integer O, S, and D; then `score_from_finalized_osd`. Math: `Pi = cbrt(O*S*D)` with veto-at-0; aspect mean; equal weights 0.2. Frozen; fixtures exist.

**Withheld when:** any aspect lacks a complete triple. Default deterministic autonomous: **always** (`complete_aspect_count=0`). Evaluation still `FINALIZED`. **No `final_scores` row.**

**Withheld state representation:**

| Surface | Withheld visible? |
| ------- | ----------------- |
| `ai_suggestion.scoring_withheld` | Yes in JSON |
| Evaluation detail UI | **No** — FRIES card omitted |
| Reports | 409 `NOT_FINALIZED` even if status is FINALIZED |
| Review page after assisted finalize | Yes (explicit copy) |

**Legacy can generate FRIES** for all five dimensions from heuristic bands, including I/E/S coverage. **Default UI cannot.** Authenticated API can.

**Dimensions treated differently for FRIES?** Not on the default mapper (all null). Legacy treats all five as one triple each — that **is** a scientific error on I/E/S, isolated to legacy.

## Amendment A6 vs withhold

**This is a real methodology contradiction, not an implementation bug, and not silently resolved.**

- **A6:** `no_material_risk` is evidence-complete; empty `osd_proposals` must not share the withhold path of `INSUFFICIENT_EVIDENCE`; FRIES should reweight over evidence-complete aspects and **must not** treat empty-risk as `Ti=0`.
- **Code + later two-mode lock:** no approved O mapping ⇒ O null ⇒ FRIES withheld until five complete triples. `fries.py` still maps empty risk lists to `Ti=0` if ever called that way.
- **Layer A status distinction is implemented** (`no_material_risk` stays `EVALUATED`). **FRIES-layer A6 is not.**

Judgment: later architecture **implicitly superseded** A6 at aggregation without amending A6. Leaving both documents “binding” is dangerous: a future engineer could “fix withhold to match A6” and emit FRIES without approved O. **Do not change `fries.py` to paper this over.** Record an explicit amendment or an explicit “A6 applies only after O mapping is approved.”

---

# 7. Mode A / Mode B audit

**Mode A (deterministic evidence + abstention):** implemented, default, enforced by server default `assessment_engine=deterministic`.

**Mode B (AI-assisted interpretation of an immutable Layer A snapshot):** **not implemented.** No `llm_assisted` engine. No snapshot LLM. No AI S proposal.

**What exists instead:** `AI_AUTONOMOUS` vs `AI_ASSISTED` as a **finalize workflow**:

- Autonomous: pipeline may write FRIES **if** triples are complete; `human_reviewed=false`.
- Assisted: stop at `AWAITING_REVIEW`; human accept/edit; then finalize.

The project is **currently claiming Mode B in product language** (`AI-Assisted`, “agent O/S/D”) **without implementing Mode B.** That is a naming collision, not a hidden LLM.

**Do not implement Mode B to fix this.** Relabel the workflow axis. Keep the engine axis.

**Current system in one sentence:** a deterministic evidence pipeline with an optional human-review gate and a legacy heuristic scorer, wrapped in AI-agent product copy.

---

# 8. Legacy isolation audit

```text
UI create evaluation  →  no probe_config  →  server sets deterministic  →  isolated
POST /v1/evaluations  →  probe_config.assessment_engine=legacy_heuristic  →  NOT isolated
                      →  extra.assessment_engine=heuristic                 →  NOT isolated
                      →  extra.assessment_engine=legacy_heuristic          →  NOT isolated
```

`ProbeConfigV1.assessment_engine` is `Literal["deterministic","legacy_heuristic"]`, but `extra` is an unconstrained dict and `resolve_assessment_engine` honors `extra.assessment_engine` including the alias `"heuristic"`.

**Can an ordinary authenticated client switch a current evaluation into legacy scoring?** **Yes.** Create a new evaluation with that `probe_config`. They cannot mutate an already-persisted deterministic OSD row into heuristic numbers without a new run.

**Is that acceptable?** As a lab escape hatch with huge banners: maybe. As v1 of a trustworthiness product: **no** — it is a **scoring oracle** that turns coverage into FRIES.

**v1 blocker?** Isolation from the **default UI** is not a freeze blocker. Isolation from **unprivileged API** is a **P1** if v1 is exposed beyond the authors; **P2** if v1 is explicitly a single-tenant lab and README says “legacy is unsafe.” Today the README still advertises mapping → FRIES as the intended pipeline, which **encourages** using the escape hatch.

**Smallest safe fix (recommendation only):** ignore `extra.assessment_engine`; require top-level `legacy_heuristic`; optionally admin-only. Do **not** delete `HeuristicOSDAgent`.

**Historical OSD rows lacking `assessment_engine`:** `_is_deterministic` is false unless `methodology_status==DETERMINISTIC_OSD_V1`. Pre-deterministic rows were heuristic — merge path is then correct. Risk is mixed-era data, not the default new-run path.

---

# 9. API / persistence audit

`GET /v1/evaluations/{id}` (`EvaluationRead`) includes: lifecycle, `probe_config`, `probe_progress` (count only), `confidence_summary`, `osd_agent`, `final_score` (optional), `mode_disclosure`, `human_review`.

**It does not include probe payloads.** Probe `metric_values` (status, methodology_version, gates, risks, claim_boundary, limitations, coverage, identity) live in Postgres and MinIO but **die at the evaluation wire**.

OSD mapper **does** copy an allowlist into `osd_metadata` (including `claim_boundary` when present on metrics). The frontend **does not render** `osd_metadata` except ReviewPage `scored_risk_id`.

| Field | In artifact | In `probe_results.metric_values` | On EvaluationRead | On UI |
| ----- | ----------- | -------------------------------- | ----------------- | ----- |
| methodology_version | F/R artifact yes; I/E/S yes | I/E/S yes; F/R **often missing** (see findings) | No (except inside osd_metadata if copied) | No |
| probe status | Yes | Yes (`probe_status`) | Not as probes[] | No |
| gates / risks / aspect_scoring | Yes | Multiclass F + R + I/E/S yes; binary/proxy F **no** | Buried in osd_metadata | Almost no |
| claim_boundary | I/E/S yes; F/R **not a first-class persist field** | I/E/S yes | Buried | No |
| flags | All artifacts | **None of the five probes persist flags into metric_values** | No | No |
| O/S/D | n/a | n/a | In `ai_suggestion.aspects` (nulls) | Blank cells |
| FRIES withheld | n/a | n/a | `scoring_withheld` on suggestion | Not shown |
| Confidence | factors in metrics | Yes | Yes | Number, weak label |

**Phase 6 error:** it claimed F/R put `flags` in metrics. **Independent check: flags are written to artifacts only** (`fairness.py`, `robustness.py`, `integrity.py`, `explainability.py`, `safety.py`). Report builder reads `metric_values.get("flags")` → **report probe flags are empty for every dimension** unless something else copied them. Confidence `refine` still sees `ProbeOutput.flags` at persist time, so engine behavior is OK.

**Uniqueness:** `probe_results` has no unique `(evaluation_id, dimension)`. Replay/duplicate inserts are possible; `list_for_evaluation` is insertion order; OSD uses all rows as snapshots (duplicate dimensions would duplicate aspects in the mapper loop’s dict — last wins by dimension key). **MVP limitation** unless the pipeline is re-run into the same evaluation (it currently fails closed on non-PENDING).

**Evidence immutability:** MinIO put of new keys; DB holds refs. No public probe rewrite API. **VALID** for v1.

**Stale evidence:** new evaluation required; no in-place probe refresh. Acceptable MVP.

---

# 10. Frontend audit

Screens read: Dashboard, Model detail (create), Evaluation detail, Review, Report, Leaderboard, Login, ModeDisclosure, ScoreBars. **No frontend tests exist.** This audit is source-based, not a browser session.

**Could a technically sophisticated user understand what was measured from the default FINALIZED screen?** **No.** They would see: AI-Autonomous, not human-reviewed, “O/S/D were generated automatically”, an agent table with empty O/S/D, evidence confidence 0.xx, no probe cards, no FRIES, no report button.

| Pattern | Where | Class |
| ------- | ----- | ----- |
| “AI-generated O/S/D” via disclaimer | `modes.py` → banner | **false on Mode A** |
| “Agent O/S/D suggestion” + always “PROPOSED — not ground truth” | Evaluation detail | **wrong genre** for deterministic copy |
| “finalizes automatically from agent O/S/D” | Model detail radios | **false for default engine** |
| “score” / FRIES hero | Report, detail, leaderboard | honest **only when** `final_score` exists |
| Trust score | no exact phrase | ranking still implies it |
| Confidence without explanation | FRIES line uses OSD mean; evidence card has note | **ambiguous** |
| Blank O/S/D | `{aspect.O}` null → empty | **unavailable ≠ blank** |
| Hidden FRIES withhold | omit card | **finished-without-explanation** |
| Missing probe statuses | all pages except buried review metadata | **INSUFFICIENT looks like success** |
| Hidden methodology / claim boundary | all primary pages | **user cannot see claim scope** |
| Docs as Safety/Explainability quality | not explicit; implied by dimension names | **easy false inference** |
| Leaderboard universal ranking | `#` + FRIES; API note if task filter omitted | **note exists; rank still dominates** |
| “auto” vs “human” | leaderboard reviewed badge | **auto ≠ AI measurement** |
| ScoreBars | green fill 0–10 | only if FRIES exists; looks like quality |
| `Number(x) \|\| 0` | ReviewPage | invalid S becomes **0 (veto)** |
| executive summary | ReportPage expects string; API sends `{headline, bullets}` | **card never renders** |
| “Trustworthy ML Benchmarking” | `index.html`, login | **overclaim** |

Review page deterministic branch is the **only** primarily honest surface.

---

# 11. Reporting audit

Reports require `FINALIZED` **and** `final_scores`. Default Mode A **cannot** produce a report. GET uses code `NOT_FINALIZED` with copy “not finalized yet” — **false** when the evaluation is FINALIZED with withheld FRIES.

When a report exists (legacy complete OSD, or a future mapping):

- Canonical JSON includes `probes[].metric_values` (best evidence dump in the product).
- Executive builder always appends “AI-proposed O/S/D is not ground truth (methodology PROPOSED_REQUIRES_VALIDATION)” — **false** for `DETERMINISTIC_OSD_V1`.
- `SCORE_NOTE` same AI-proposed claim.
- HTML headers: **O (Operations) / S (Safeguards) / D (Disclosures)** — **wrong FRIES definitions** (Occurrence / Severity / Detection). This is a **scientific labeling error**, not a typo.
- HTML: “agent-proposed O/S/D is never ground truth.”
- UI Report page: FRIES-first; executive summary **does not render**; probe evidence only inside `<details>` JSON.

JSON vs UI terminology: JSON can be honest if you know where to look; the HTML/UI story is a scoring product.

---

# 12. Security-boundary audit

Not a penetration test.

| Boundary | Judgment |
| -------- | -------- |
| Mutations authenticated; review/finalize RBAC; publish owner/admin | **VALID** |
| List/get evaluations: any auth user, no owner filter; GET unused `current_user` | Lab threat model **P2**; undermines “my evaluation” isolation |
| `assessment_engine` client-trusted | **Undermines the scientific trust model** if the API is shared |
| Integrity hash inputs from `probe_config.extra` | Operator-supplied; limitations exist; still client-trusted |
| Evidence store append-only; no probe edit API | **VALID** |
| Review cannot set O/D on deterministic | **VALID** |
| JWT in `localStorage` | Known XSS tradeoff; **P3** for a local-first lab |

Nothing here lets an LLM rewrite Layer A. The scientific trust model is undermined by **legacy engine selection** and **false provenance copy**, not by missing HTTPS in this review’s scope.

---

# 13. Testing audit

Backend coverage is **strong** for probes, confidence, deterministic OSD, human review, FRIES fixtures, auth, reports-on-FRIES, leaderboard. `test_autonomous_pipeline_finalized_scoring_withheld` exists for the **pipeline** default engine.

**There is no golden path:**

UI → API → evaluation → probes → evidence → confidence → OSD → FRIES decision → **rendered UI**.

Missing (minimum for architecture confidence — not a Playwright empire):

1. API contract: default create payload matches the UI (`AI_AUTONOMOUS`, empty `probe_config`) → `FINALIZED`, `scoring_withheld`, no `final_scores`, **disclaimer text does not claim O/S/D were generated** (this last assertion will fail today).
2. After any API change: `EvaluationRead` includes probe summaries; statuses round-trip.
3. Report 409 when status is FINALIZED without score; message does not say “not finalized yet.”
4. `extra.assessment_engine="heuristic"` behavior (pin current behavior or forbid it).
5. One documented **manual** default-path checklist (login → create → FINALIZED → withheld FRIES + five statuses). Frontend unit tests for `fmtOsd` / disclaimer branching if those are added.

**Do not treat “70 pytest files” as product honesty coverage.** Many FRIES tests **opt into** `legacy_heuristic` or evaluated fakes.

---

# 14. Phase 6 audit verification

Phase 6’s **central thesis is correct:** Layer A is mostly honest; the served product is not. That is not rubber-stamping — it matches independent traces of `evaluate_pipeline.py`, `EvaluationRead`, and `EvaluationDetailPage.tsx`.

Phase 6 is **wrong or overstated** in places below. Use this table, not Phase 6’s severity list, as the freeze list.

| Phase 6 ID | Real? | Severity (this review) | Proposed fix / scope | Methodology change? |
| ---------- | ----- | ---------------------- | -------------------- | ------------------- |
| P0-1 autonomous disclaimer | **Yes.** Fires on every default run. | **P0** | Branch disclaimer on engine + withheld. Small copy fix. | No |
| P0-2 HTML O/S/D names | **Yes.** | **P0** for any published report; default path has no HTML report | One template line. | No |
| P0-3 AI-proposed report notes | **Yes.** | **P0** when reports exist | Branch on `assessment_engine` / methodology_status. | No |
| P1-1 probes missing from EvaluationRead | **Yes.** | **P1** | Additive `probes` array. Do not make the frontend reconstruct from OSD. | No |
| P1-2 withheld FRIES visibility + report 409 copy | **Yes.** | **P1** | Banner + evidence export; fix error copy. New report schema is a **product decision** (open). | Only if you start emitting FRIES without O |
| P1-3 Mode / ModelDetail copy | **Yes.** | **P1** | Relabel workflow; do not rename enums in v1. | No |
| P1-4 always PROPOSED banner | **Yes.** | **P1** | Branch on deterministic vs heuristic. | No |
| P1-5 null OSD blank cells | **Yes.** | **P1** | Render `unavailable`. Small. | No |
| P1-6 confidence labeling | **Yes.** | **P1** presentation | Lead with “evidence strength”; show `proposed_calibration`. Do not recalibrate. | No |
| P1-7 no frontend tests | **Yes as a gap.** | **P2** (process), not a scientific P1 | API disclosure tests + short manual checklist suffice for freeze. | No |
| P1-8 leaderboard vs default no FRIES | **Yes as product shape.** | **P2** if copy explains emptiness; **P1** if branding stays “benchmarking” | Keep FRIES-only leaderboard; explain. Do not rank coverage. | Open Q |
| P1-9 Integrity `scored_risk` | **Yes.** | **P2** | Optional token rename to `risk_detected` (C6). Does not change FRIES. | Vocabulary only |
| P1-10 F/R methodology persist | **Yes**, and **stronger:** binary pairing skips methodology eval entirely. | **P2** for HateXplain-only v1; **P1** before adding binary pairings | Persist `methodology_version`; do not fake binary A1 in this freeze unless pairing is added. | Binary A1 would be methodology **implementation**, not a new spec |
| P1-11 `\|\| 0` | **Yes.** Harmless for FRIES on Mode A; **veto 0 on legacy**. | **P1** while legacy reviews remain reachable; else P2 | `Number.isFinite` / empty → null. | No |
| P1-12 extra.heuristic + old rows | **Yes** for extra alias. Old-row merge is mostly LEGACY-correct. | **P1** extra alias; old rows **LEGACY** | Stop reading engine from `extra`. | No |
| P2-3 flags persist I/E/S only | **Understated.** Flags missing from **all five** metric_values. | **P2** | Copy `flags` into persisted metrics in runner **or** each probe. Non-science. | No |
| P2-11 report executive UI | **Yes.** | **P2** | Render headline + bullets. | No |
| P2-1 legacy creatable | **Yes.** | **P2** lab / **P1** shared API | Admin gate optional. | Policy |
| P2-2 geo vs arithmetic confidence | **Yes.** | **P2** | Do not show OSD mean as FRIES confidence. | No |
| P2-9 mapper default EVALUATED | **Yes, low likelihood** (runner writes status). | **P3** | Default to INSUFFICIENT if missing. | No |
| P2-7 README drift | **Yes.** | **P2** | Current-behavior section. | No |

Phase 6 **scope for Phase 6 work** (honesty + evidence surfacing, not new science) is the right scope. Several P1s were **inflated** (tests, Integrity token, methodology persist for current pairing). P0-1 is **not** inflated.

---

# 15. Findings by severity

Format required by the review charter.

### AV-P0-1

**ID:** AV-P0-1  
**Severity:** P0  
**Location:** `backend/app/schemas/modes.py` `AUTONOMOUS_DISCLAIMER`; consumed by `get_mode_disclosure` → UI banner and reports.  
**Observed:** Default deterministic autonomous runs store O=S=D=null and still disclose “O/S/D were generated automatically and were not human-reviewed.”  
**Expected:** Provenance must match the mapper: O/S/D were **not** generated; representation abstained.  
**Why it matters:** False assessment story on the primary path.  
**Methodology impact:** None if copy is fixed; changing FRIES policy would be a methodology change — do not.  
**User impact:** Believes an AI scored the model.  
**Recommended fix:** Disclaimer branches on `assessment_engine` / `methodology_status` / `scoring_withheld`. Keep a “not human-reviewed” fact.  
**Confidence:** HIGH

### AV-P0-2

**ID:** AV-P0-2  
**Severity:** P0  
**Location:** `backend/app/reports/templates/report_v1.html` finalized O/S/D table headers.  
**Observed:** O (Operations), S (Safeguards), D (Disclosures).  
**Expected:** Occurrence, Severity, Detection (FRIES convention; README even warns that confusing this is a correctness failure).  
**Why it matters:** Wrong construct, not a synonym.  
**Methodology impact:** None.  
**User impact:** Misreads every published report’s triples.  
**Recommended fix:** Rename headers. Do not change `fries.py`.  
**Confidence:** HIGH

### AV-P0-3

**ID:** AV-P0-3  
**Severity:** P0  
**Location:** `reports/builder.py` last executive bullet; `schemas/reports.py` `SCORE_NOTE`; report HTML callout.  
**Observed:** Unconditional “AI-proposed O/S/D”.  
**Expected:** Heuristic path may say proposed/heuristic; deterministic path must not.  
**Why it matters:** Same as P0-1 for the archival artifact.  
**Methodology impact:** None.  
**User impact:** Frozen false provenance in versioned reports.  
**Recommended fix:** Branch on persisted `assessment_engine` / `methodology_status`.  
**Confidence:** HIGH

### AV-P1-1

**ID:** AV-P1-1  
**Severity:** P1  
**Location:** `schemas/evaluations.py` `EvaluationRead`; `EvaluationService.build_detail`; `EvaluationDetailPage.tsx`.  
**Observed:** Probe evidence, status, methodology_version, claim_boundary, limitations not served as first-class evaluation fields; UI cannot show them.  
**Expected:** Default FINALIZED view shows what was measured per dimension.  
**Why it matters:** Evidence-first architecture is not end-to-end.  
**Methodology impact:** None (additive API).  
**User impact:** Cannot distinguish EVALUATED vs INSUFFICIENT vs PROXY.  
**Recommended fix:** Additive `probes` on detail reads; thin UI cards. Do not reconstruct meaning from OSD rationals.  
**Confidence:** HIGH

### AV-P1-2

**ID:** AV-P1-2  
**Severity:** P1  
**Location:** Evaluation detail (FRIES card omitted); `report_service.py` 409 `NOT_FINALIZED`; `ReportPage.tsx` copy.  
**Observed:** Withheld FRIES is an absent widget; reports say the eval is not finalized.  
**Expected:** Explicit `FRIES_WITHHELD` / scoring withheld; reports available as evidence export or honest 409.  
**Why it matters:** FINALIZED looks unfinished or secretly successful.  
**Methodology impact:** Evidence-only report schema is an **open product choice**; do not sneak FRIES in.  
**User impact:** High.  
**Recommended fix:** Banner on detail; fix error string; optional evidence export.  
**Confidence:** HIGH

### AV-P1-3

**ID:** AV-P1-3  
**Severity:** P1  
**Location:** `ModeDisclosure.tsx`; `ModelDetailPage.tsx` mode radios; evaluation detail “Agent” heading.  
**Observed:** Workflow enums presented as AI measurement / agent scoring.  
**Expected:** Auto-finalize vs human-review; assessment engine named separately (`deterministic`).  
**Why it matters:** Mode A vs Mode B collision.  
**Methodology impact:** UI labels only; do not implement Mode B.  
**User impact:** High.  
**Recommended fix:** Relabel; keep API enums.  
**Confidence:** HIGH

### AV-P1-4

**ID:** AV-P1-4  
**Severity:** P1  
**Location:** `EvaluationDetailPage.tsx` always “PROPOSED — not ground truth.”  
**Observed:** Applied to deterministic abstention.  
**Expected:** Deterministic copy from `serialize._SUGGESTION_NOTE_DETERMINISTIC`; heuristic keeps PROPOSED.  
**Why it matters:** “Proposed” implies values exist.  
**Methodology impact:** None.  
**User impact:** Medium–high.  
**Recommended fix:** Branch on `assessment_engine`.  
**Confidence:** HIGH

### AV-P1-5

**ID:** AV-P1-5  
**Severity:** P1  
**Location:** Evaluation detail table `{aspect.O}`; contrast ReviewPage `unavailable` / `—`.  
**Observed:** Null renders blank.  
**Expected:** `unavailable` (or human S). Never implied 0.  
**Why it matters:** Blank is not a semantic state.  
**Methodology impact:** None.  
**User impact:** Medium.  
**Recommended fix:** Shared formatter.  
**Confidence:** HIGH

### AV-P1-6

**ID:** AV-P1-6  
**Severity:** P1  
**Location:** Evaluation detail FRIES line `confidence {overall_confidence}`; evidence card.  
**Observed:** OSD arithmetic mean adjacent to FRIES; `proposed_calibration` unused in UI.  
**Expected:** “Evidence strength (uncalibrated)”; do not attach OSD mean to FRIES.  
**Why it matters:** Confidence ≠ P(correct) ≠ FRIES quality.  
**Methodology impact:** Do not “fix” by changing factor science.  
**User impact:** Medium–high.  
**Recommended fix:** Presentation only.  
**Confidence:** HIGH

### AV-P1-7

**ID:** AV-P1-7  
**Severity:** P1  
**Location:** `osd/deterministic.py` `resolve_assessment_engine`; `schemas/probe_config.py` `extra`.  
**Observed:** `"heuristic"` in `extra` selects `HeuristicOSDAgent`. Any auth user may set `legacy_heuristic`.  
**Expected:** Default path cannot reach heuristic bands; explicit legacy is versioned and obvious.  
**Why it matters:** Production escape hatch for unsupported FRIES including I/E/S.  
**Methodology impact:** Policy on who may select legacy.  
**User impact:** High if API is shared.  
**Recommended fix:** Do not read engine from `extra`; optional admin-only legacy. Keep HeuristicOSDAgent.  
**Confidence:** HIGH

### AV-P1-8

**ID:** AV-P1-8  
**Severity:** P1  
**Location:** `frontend/src/pages/ReviewPage.tsx` `Number(trimmed) \|\| 0`.  
**Observed:** Non-numeric input becomes 0. Legacy complete triples can FRIES-veto.  
**Expected:** Invalid → null / reject.  
**Why it matters:** 0 is a defined FRIES veto, not a parse error.  
**Methodology impact:** None.  
**User impact:** High on legacy; low on Mode A (cannot complete FRIES).  
**Recommended fix:** Finite-integer parse.  
**Confidence:** HIGH

### AV-P2-1

**ID:** AV-P2-1  
**Severity:** P2  
**Location:** All five probes vs `reports/builder.py` flags; Phase 6 P2-3.  
**Observed:** `flags` in artifacts and `ProbeOutput.flags`, not in persisted `metric_values`. Reports’ probe flags empty.  
**Expected:** Flags survive DB → report.  
**Why it matters:** Downstream consumers using DB as SoT lose skip/gate flags.  
**Methodology impact:** None.  
**User impact:** Low today (UI hides them); blocks honest reports.  
**Recommended fix:** Runner copies `output.flags` into persisted metrics.  
**Confidence:** HIGH

### AV-P2-2

**ID:** AV-P2-2  
**Severity:** P2  
**Location:** `fairness.py` binary pairing `_finish`; `_finish_methodology` persist without `methodology_version`; `robustness.py` artifact key `methodology` vs metrics.  
**Observed:** Binary pairing: EVALUATED bundle, no A1 gates/CIs/`aspect_scoring`. Multiclass artifact has version; DB metrics often do not.  
**Expected:** Pairing docs must not claim “no probe changes” for binary; persist version on metrics.  
**Why it matters:** Latent false methodology if a binary pairing is added.  
**Methodology impact:** Implementing binary A1 **is** F/R spec, currently unimplemented.  
**User impact:** None on HateXplain-only v1; high later.  
**Recommended fix:** Document the hole; persist version; do not add binary pairings until eval exists.  
**Confidence:** HIGH

### AV-P2-3

**ID:** AV-P2-3  
**Severity:** P2  
**Location:** `integrity_eval.py` ~370–379.  
**Observed:** `aspect_scoring="scored_risk"` with `scored_risk_id=None`.  
**Expected:** `risk_detected` (E/S family) **or** a real scored-family id if O mapping existed (it does not).  
**Why it matters:** Token collision with F/R “scored”. No FRIES emission found.  
**Methodology impact:** Vocabulary; optional one-line eval change.  
**User impact:** Low until UI shows the token.  
**Recommended fix:** Rename to `risk_detected` when touching Integrity serialization.  
**Confidence:** HIGH

### AV-P2-4

**ID:** AV-P2-4  
**Severity:** P2  
**Location:** `confidence/engine.py` Fairness completeness vs amendment A8; OSD arithmetic vs geo mean.  
**Observed:** Fairness completeness ≈ evidence_ref present; two different “overall confidence” numbers.  
**Expected:** Document as uncalibrated; don’t display two numbers as one concept.  
**Why it matters:** Looks calibrated.  
**Methodology impact:** Recalibration is **deferred**.  
**User impact:** Medium.  
**Recommended fix:** UI + docstring; do not retune weights in freeze.  
**Confidence:** HIGH

### AV-P2-5

**ID:** AV-P2-5  
**Severity:** P2  
**Location:** `evaluations.py` list/get; `README.md`; branding; `ReportPage` executive summary; ScoreBars/leaderboard when heuristic FRIES exists.  
**Observed:** Global eval listing; README target pipeline; benchmarking title; executive card dead; heuristic I/E/S can appear as dimension “scores”.  
**Expected:** Honest current-behavior docs; render executive object; rank only comparable published FRIES with caveats.  
**Why it matters:** Product frame vs lab reality.  
**Methodology impact:** None.  
**User impact:** Medium.  
**Recommended fix:** Copy + small UI bugs. ACL deferred unless multi-tenant.  
**Confidence:** HIGH

### AV-P3-1

**ID:** AV-P3-1  
**Severity:** P3  
**Location:** `engine.py` module docstring; mapper missing-status → EVALUATED; `types.ts` version comment; `ai_*` column names.  
**Observed:** Stale comments; low-likelihood defaults; historical names.  
**Expected:** Comments match code; missing status → insufficient.  
**Why it matters:** Future implementer error.  
**Methodology impact:** None.  
**User impact:** Low.  
**Recommended fix:** Docstrings; keep `ai_suggestion` columns (breaking rename deferred).  
**Confidence:** HIGH

### VALID (selected)

- Default mapper abstention; FRIES withhold; human cannot supply O/D on deterministic review.  
- `integrity_score_0_10` absent.  
- E/S confidence not driven by coverage after `refine`.  
- `scored_risk_id is None` on I/E/S.  
- Frozen `fries.py` + fixtures.  
- Publish opt-in, never auto-publish.  
- PROXY fairness does not complete default FRIES.  
- Append-only evidence objects.

### LEGACY (preserve)

- `HeuristicOSDAgent`, empty-card `(2,2,3)`, Safety keyword S/D nudges, coverage→O/S/D.  
- Tests that opt into complete FRIES.  
- `AI_AUTONOMOUS` FRIES write **when** triples exist.

### DEFERRED

- Mode B / `llm_assisted`.  
- Validated O mappings / `scale_linear`.  
- Behavioral Safety.  
- Confidence calibration.  
- Composite TrustLens score (do not create).  
- Owner ACL (lab app).  
- Heavy Playwright.  
- A6 FRIES reweighting (must be an explicit amendment).  
- Binary fairness methodology eval (until a binary pairing is a v1 target).

---

# 16. Required fixes before v1 freeze

Must change (honesty of the **existing** architecture):

1. Deterministic / withheld disclaimers (AV-P0-1).  
2. Report O/S/D definitions and AI-proposed notes (AV-P0-2, AV-P0-3).  
3. Additive probe evidence on evaluation detail + UI statuses/claim boundaries (AV-P1-1).  
4. Explicit FRIES withheld; honest report 409 or evidence export (AV-P1-2).  
5. Mode/agent copy vs workflow (AV-P1-3, AV-P1-4).  
6. Null O/S/D as unavailable (AV-P1-5).  
7. Confidence labeled as uncalibrated evidence strength; detach OSD mean from FRIES (AV-P1-6).  
8. Close `extra.assessment_engine` alias; decide whether unprivileged `legacy_heuristic` is allowed (AV-P1-7).  
9. Review numeric parse (AV-P1-8).  
10. Persist flags into metric_values (AV-P2-1) so reports are not silently empty.  
11. README / OpenAPI / branding current-behavior (AV-P2-5 subset).  
12. Tests for default-path **disclosure strings** and withheld FRIES (not only pipeline flags).

Must **not** change for freeze:

- `fries.py`  
- HeuristicOSDAgent behavior (except isolation/gating)  
- Probe statistical thresholds  
- Inventing Mode B  
- Inventing a composite score  
- Silently implementing A6 reweighting  

---

# 17. Recommended fixes after v1

- Integrity `aspect_scoring` token alignment (`risk_detected`).  
- Persist `methodology_version` on F/R metric_values; add `claim_boundary` where F/R have one.  
- Binary pairing: implement A1 Layer A **before** allowlisting a binary model.  
- Fairness confidence completeness vs A8 (only with an explicit calibration/completeness note).  
- Owner-scoped lists if the app leaves single-user lab use.  
- Versioned rename of `ai_suggestion` / `AI_*` enums.  
- Evidence-only `evidence_v1` reports (schema decision).  
- Thin frontend tests around OSD formatting and disclaimer branching.

---

# 18. Explicitly deferred items

- LLM-assisted Mode B.  
- Approved O mapping activation.  
- Behavioral Safety / FRIES2.  
- Confidence calibration research.  
- Multi-tenant ACL.  
- Full human-decision taxonomy.  
- Large e2e infrastructure.  
- Deleting legacy compatibility.  
- Making I/E/S statistically identical to F/R.

---

# 19. Open methodology questions

Do **not** silently resolve these.

1. **A6 vs withhold:** Is `no_material_risk` FRIES-complete after O mapping exists? Today withhold is the product rule. **Amend A6 or amend the two-mode lock.**  
2. **Keep `AI_ASSISTED` / `AI_AUTONOMOUS` in the API forever?** UI relabel is enough for v1.  
3. **Evidence-only reports:** new schema vs nullable `score` on `report_v1`.  
4. **Leaderboard without FRIES:** hide vs evidence cards. Recommend keep FRIES-only, explain emptiness.  
5. **Who may select `legacy_heuristic`?**  
6. **`scored_risk` on F/R while O is null:** keep implementation; UI must say “named detection, O not assigned.”  
7. **Human review taxonomy:** accept_all / edit sufficient?  
8. **Are 0.45/0.35 confidence factors frozen as v1 engineering?** If yes, say so; they are not measurements.

---

# 20. Final v1 readiness judgment

1. **Is TrustLens architecturally coherent today?**  
   **Partially.** Layer A + default OSD + frozen FRIES math are coherent. Product vocabulary and API omission make the running system incoherent as a *product*.

2. **Is the scientific methodology coherent across all five dimensions?**  
   **Yes as a split design** (statistical F/R vs disclosure I/E/S). **No as a single “five equal scores” story.** A6 vs withhold remains unresolved at FRIES aggregation.

3. **Is the backend evidence-first model preserved end-to-end?**  
   **Through persistence: mostly yes. Through the evaluation API and UI: no.**

4. **Is the frontend honest about what was measured?**  
   **No.** Review is the exception.

5. **Is Mode A correctly implemented?**  
   **Yes** as an assessment engine. **No** as a user-facing mode.

6. **Is the claimed Mode B actually implemented?**  
   **No.** `AI_ASSISTED` is human review, not LLM interpretation.

7. **Is legacy scoring safely isolated?**  
   **From the default UI: yes. From the API: no.**

8. **Can default runs produce unsupported O/S/D?**  
   **Numeric: no. Verbal: yes.**

9. **Can default runs produce unsupported FRIES?**  
   **No.** Legacy API runs **can.**

10. **Is confidence semantically correct?**  
    **In the engine, as uncalibrated evidence strength: yes. In the UI and as OSD-mean-beside-FRIES: no. Factor magnitudes are not science.**

11. **Are reports scientifically honest?**  
    **Unavailable on the default path. When present: JSON contains evidence; HTML/executive language is not honest.**

12. **Is the API preserving enough evidence?**  
    **The database is. EvaluationRead is not.**

13. **Is the system ready for a v1 freeze?**  
    **No.**

14. **What MUST be fixed before freeze?**  
    Section 16. Especially P0 provenance and P1 evidence visibility / withheld FRIES / mode copy / legacy extra alias.

15. **What should explicitly remain deferred?**  
    Section 18. Especially Mode B, O mapping, behavioral Safety, A6 reweighting, calibration.

---

*End of independent verification. If this document disagrees with Phase 6, this document wins only where it cites code; remaining open questions stay open.*
