# TrustLens V1 Product Contract / Architecture Drift Audit

**Type:** code-first product requirements audit. Not an implementation. Not a methodology rewrite.  
**Date:** 2026-09-08  
**Scope:** repository as it exists on branch `fix/probes` (working tree). Claims about *current* behavior are from code. Claims about *intent* cite README vision, methodology v1.0, five-probe audit, and this audit’s user-stated non-negotiables.  
**Does not modify:** probes, FRIES math, Mode B, behavioral Safety, O mappings.

**Verdict (plain):** The default product does **not** evaluate a user-selected Hugging Face model locally on a user-required dataset. Import is Hub metadata. Evaluations can be created with optional free-text `task`/`dataset` that probes never read. Fairness’s default path fits a sklearn LogisticRegression on pinned Adult Census. Robustness loads the imported model only for text-classification when a **registry** pin or explicit `probe_config.datasets.robustness` exists; otherwise it skips. Integrity / Explainability / Safety read the model card. One allowlisted pairing (`hatexplain_bert_v1`) is the only model-faithful fairness path — and it is gated on an exact Hub SHA match, so even the intended model often falls through to the Adult proxy.

Phase 6 made that architecture **honest about scores**. It did not restore the original local-first evaluation contract.

---

## A. TrustLens V1 Product Contract

Two layers of “required” exist in the repo. This audit treats them separately so deferred science is not scored as a bug.

### A1. Original product vision (README + target architecture)

From [README.md](../README.md) Vision and Target architecture:

1. **Local-first.** Import a Hugging Face model, check whether it can run on the machine, then run **local inference**. Hosted inference is not the core path.
2. **Compatibility before download.** Disk / RAM / VRAM as separate constraints; unsupported → skip, no download. Short benchmark → runtime estimate → user confirm.
3. **Measured evidence** on the artifact under test, then (later) risk → O/S/D → FRIES. Metrics are not dimension scores.
4. **Five FRIES probes** after local predictions/artifacts: Fairness, Robustness, Safety (behavioral+governance in the *target*), Integrity and Explainability as evidence.
5. **Human review and audit** of every step.
6. **PROXY** (substitute model or dataset) must be labeled, never silent.
7. Unavailable evidence must not become a fabricated numeric score (withhold / statuses).

README **Current implementation** already admits: import is metadata-only; default fairness predictor is proxy LR; I/E/S are metadata; no resource checker; no shared inference backend except robustness NLP (now also pairing-fairness). That admission is evidence of drift, not a waiver of the vision.

### A2. Locked methodology v1.0 (must not be treated as missing product)

Authoritative for *what a probe may claim*, not for shipping a full local-first lab:

| Topic | Methodology position | Audit treatment |
| ----- | -------------------- | ----------------- |
| Fairness / Robustness normative eval | **Model-faithful** on pinned pairing / compat; Adult `proxy_lr` is `PROXY`, no FRIES (A7) | Contract for F/R **when they claim evaluation of the imported model** |
| NLP fairness | `NOT_APPLICABLE` until a pinned corpus with attribute `A` exists | HateXplain pin exists as that corpus — **allowlist**, not arbitrary user data |
| Integrity | Hub identity / disclosure Layer A; production hash verify deferred | Documentation / identity evidence, not weight execution |
| Explainability | Model-card coverage; SHAP/LIME deferred | Documentation-only |
| Safety | Governance checklist; **behavioral suite deferred** (five-probe audit) | Documentation-only for v1 |
| Mode B / LLM O/S/D | Not implemented | Deferred |
| Validated O→FRIES mapping | Default engine abstains; FRIES withheld | Deferred science (Phase 6 honesty) |
| Image / generative / arbitrary HF | `NOT_APPLICABLE` until pinned | Deferred, not a silent eval |

### A3. Non-negotiable contract used in this audit (user + vision ∩ methodology)

Minimum **product** contract to claim “TrustLens evaluated this model”:

1. The **selected model artifact** is available locally (weights loaded from a recorded revision) for any probe that requires model-faithful inference.
2. Import must not be the only model step; evaluation must **execute** that artifact where methodology requires it.
3. A **real evaluation dataset** with recorded identity (path/revision/task/labels) is bound to that run for F/R. It must not be silently replaced by Adult / SST-2 / AG News without an explicit contract.
4. No hidden substitute predictor. Proxy is allowed only as `PROXY` and must be unmissable in API/UI.
5. Create-evaluation enforces the minimum inputs the probes actually use (or refuses).
6. A completed run records enough identity to reproduce model + dataset + config + seeds + methodology versions.
7. I/E/S remaining documentation-only is **consistent with current methodology** (not a P0 vs A2). It **is** drift vs A1 target architecture.

---

## B. Current Architecture (as implemented)

```text
UI/API  POST /v1/models/import-hf
          → HfHubModelAdapter.resolve (model_info, file names, ModelCard)
          → models row: hf_repo_id, revision=Hub SHA, checksum=same SHA (not weights hash)
          → NO weight download, NO resource check, NO local load

UI/API  POST /v1/evaluations  { model_id, evaluation_mode, optional task/dataset/config }
          → probe_config defaults assessment_engine=deterministic
          → evaluation.dataset / task are comparability strings (ADR 0013)
          → NOT passed into ProbeContext
          → Celery EvaluateModelPayload = { evaluation_id, model_ref, mode, probe_config }

Worker  run_evaluation_pipeline
          → run_all_probes F→R→I→E→S
          → deterministic OSD abstain (default) or HeuristicOSDAgent (admin)
          → FINALIZED; FRIES withheld unless complete O/S/D
```

### B1. Model import and identity

| Fact | Location |
| ---- | -------- |
| Import never downloads weights | `backend/app/adapters/hf_hub.py`, `backend/app/routers/v1/import_hf.py` |
| `checksum` column = Hub commit SHA, aliased from `info.sha` | `HfHubModelAdapter.resolve` |
| Card text loaded without revision pin | `ModelCard.load(ref)` — default branch |
| File list is names only | `list_repo_files` |

### B2. Local execution (when it happens)

`LocalHFBackend` (`backend/app/inference/local_hf.py`): `AutoTokenizer` / `AutoModelForSequenceClassification.from_pretrained(ref, revision=...)`. Cache is the default Hugging Face hub cache (typically `~/.cache/huggingface/hub`), not a TrustLens-managed artifact store. Device from pairing/config, default CPU. No VRAM/RAM/disk gate.

Callers:

- **Fairness pairing path only:** `FairnessProbe._run_pairing_faithful` loads **`pairing.model_ref` + `pairing.model_revision`** (YAML pin), not `ctx.model_revision`.
- **Robustness NLP:** `TransformersCharSwapRunner` loads **`ctx.model_ref` + `ctx.model_revision`** (imported row).

Pipeline docstring still says “Does not download HF weights.” That is false for those two paths; it remains true for import and for I/E/S.

### B3. Datasets

Pinned registry: `configs/datasets_v1.yaml` (Adult, SST-2, AG News, CIFAR placeholder, HateXplain).

Pairings: `configs/supported_pairings_v1.yaml` — **one** row: Hate-speech-CNERG/bert-base-uncased-hatexplain @ `e487c81…` × `hatexplain_fairness` @ `f6a8b7d…`.

Robustness compat: `configs/supported_robustness_compat_v1.yaml` — **two** models (AG News BERT, SST-2 BERT) with matching pins.

Loaders: `backend/app/datasets/loader.py` — Hub `datasets.load_dataset` (or HateXplain GitHub JSON). Evaluation’s `dataset` field is unused.

Default fairness logical key if no pairing: **`adult_fairness`**.

### B4. Evaluation contract (API/UI)

`EvaluationCreate`: required `model_id`, `evaluation_mode`. Optional `task`, `dataset`, `config`, `model_revision`, `trustlens_version`, `probe_config`.

Frontend `ModelDetailPage` sends `model_id`, mode, optional free-text task/dataset. It does **not** send `probe_config.datasets`, pairing id, label schema, or modality.

`create_evaluation` copies `data.model_revision` from the client (usually null). Pipeline inference uses **`models.revision`**, not `evaluations.model_revision`.

### B5. Probe runner

`ProbeContext` = `evaluation_id`, `model_ref`, `model_metadata`, `probe_config`, evidence store, `model_revision`, `model_checksum`. No user dataset, no task, no label map.

### B6. Frontend honesty surface

Detail page shows probe **status / methodology_version / claim_boundary / limitations / flags / named risks**. `ProbeEvidenceRead.fairness_mode` and `pairing_id` exist in TS types and are **not rendered**.

---

## C. Drift Matrix

| Requirement | Expected | Actual | Gap | Severity | Evidence |
| ----------- | -------- | ------ | --- | -------- | -------- |
| Local-first model available at import | Weights fetched or compatibility-gated skip | Metadata only | Import is not execution | **P0** vs product vision; **DEFERRED** as “Hub catalog step” only if a later **load** step is mandatory | `hf_hub.py`, README “does not download weights” |
| Evaluation executes selected model | All model-faithful probes load recorded revision | Default F does not; R only if text-clf + pin/config; I/E/S never | Default FINALIZED without local forward pass | **P0** | `fairness.py` `_run_legacy`; `evaluate_pipeline.py`; `integrity.py` |
| No metadata-only *evaluation* | Evaluation implies local run | Evaluation = probes + OSD; 3/5 probes metadata; F often proxy | Product “evaluate” ≠ execute | **P0** | runner + probes |
| No hidden substitute | PROXY labeled; UI unmissable | Adult LR default; `fairness_mode=proxy_lr`, status `PROXY`; UI does not show `fairness_mode` | Silent at product layer | **P0** product / **P1** if operators read raw JSON | `fairness.py` `_PROXY_NOTE`; `EvaluationDetailPage.tsx` |
| Pairing load uses *imported* identity | `from_pretrained(imported ref, imported sha)` | Pairing loads **YAML** `model_ref`/`model_revision` | If resolve succeeds, pin overrides import SHA (usually same repo). If import SHA ≠ pin, resolve **fails** → proxy | **P1** | `fairness.py` `backend.load(pairing.model_ref, revision=pairing.model_revision)`; `resolve_pairing` exact SHA |
| Required dataset on every substantive eval | Bound, versioned, used by F/R | Optional string; probes ignore it | Underspecified evals always allowed | **P0** | `schemas/evaluations.py`; `ProbeContext`; `ModelDetailPage.tsx` |
| Dataset not replaced by internal bench | User dataset or explicit allowlist choice | Adult / SST-2 / AG News / HateXplain from YAML | Registry datasets are the real eval data | **P0** vs “user’s dataset”; **VALID** vs methodology allowlist *if* user selected that pin | `datasets_v1.yaml`; `_DEFAULT_DATASET_KEY` |
| F/R model-faithful | Imported model on contracted dataset | F: 1 pairing else proxy LR. R: imported model on **compat/registry** set, else N/A skip | Arbitrary import is not F/R-eval of that model | **P0** default path | `supported_pairings_v1.yaml` (1 row); `supported_robustness_compat_v1.yaml` (2 rows) |
| Distinguish A/B/C/D in UI/API | Unmissable | Persist `fairness_mode`, flags, statuses; UI omits mode/pairing | Partial API, weak UI | **P1** | `ProbeEvidenceRead`; detail page |
| Task / labels / modality enforced | Required for F/R | Optional; inferred from pairing YAML or Hub tags | Underspecified | **P0** create path | `EvaluationCreate`; `_is_text_classification` |
| Resource checker | Before download | Absent; `from_pretrained` at probe time | Can OOM mid-eval | **P1** vs vision; methodology does not implement it | README roadmap Phase 2 Absent |
| Record model revision on evaluation | Frozen on the run | Client field optional; probes use `models.revision` | Split identity | **P1** | `evaluation_service.create_evaluation`; `run_evaluation_pipeline` |
| Record dataset revision on evaluation | First-class | Only inside probe `metric_values.dataset` when a pin ran | Eval row can be FINALIZED with `dataset=null` | **P0** | `evaluations.dataset`; probe metrics |
| Weight checksum | Artifact hash | SHA = Hub commit id | Not a weights hash | **P1** | `hf_hub.py` `checksum=resolved_revision` |
| Reproduce seeds / attack / methodology | On the run | F/R persist seed, budget, methodology_version in metrics when they run | Missing if skipped; not on evaluation header | **P2** if probes ran; **P1** if skipped path looks complete | probe `metric_values` |
| I/E/S documentation-only | Vision: more; methodology: card/governance | Card/checklist | Matches A2; drifts A1 | **DEFERRED** vs methodology; **P2** vs vision | five-probe audit; `explainability.py`, `safety.py` |
| Behavioral Safety | Deferred | Not implemented | — | **DEFERRED** | five-probe audit § Safety |
| Default FRIES / O mapping | Vision maps evidence→OSD; methodology abstains | Deterministic withhold | Honest vs unvalidated mapping | **VALID** vs Phase 6 / methodology; **DEFERRED** vs vision Layer B | `deterministic.py`; pipeline withhold |
| Mode B | Deferred | Absent | — | **DEFERRED** | README open questions |
| Shared inference backend | Target architecture | `LocalHFBackend` exists; not used at import; not used by I/E/S | Partial | **P1** | `local_hf.py`; pipeline |
| Pipeline “no weight download” comment | Accurate docs | Stale; F pairing + R NLP download | Misleading | **P2** | `evaluate_pipeline.py` header |

---

## D. What is genuinely complete

- Auth, RBAC, evaluation lifecycle, Celery enqueue, MinIO evidence blobs, probe status enum, confidence engine (uncalibrated), deterministic OSD abstention, admin-gated legacy heuristic, FRIES math when triples exist, reports/leaderboard gated on scores, Phase 6 disclosure copy, withheld-FRIES UI card.
- **LocalHFBackend** is real sequence-classification inference (CPU), with revision passed through, tests around `from_pretrained`.
- **One** model-faithful fairness pairing implementation (HateXplain adapter, multiclass metrics, `fairness_mode=model_faithful`, Adult path `PROXY` + A7-empty OSD).
- **Robustness** char-swap on the **imported** model when a dataset key resolves and Hub tags look like text-classification; domain mismatch gates; skip is `NOT_APPLICABLE` not a fake score (default engine).
- I/E/S honestly measure **cards / Hub metadata**, with claim boundaries and named risks — consistent with locked v1 methodology for those aspects.
- Dataset **pins** (full git SHAs) for registry keys; pairing YAML refuses floating `main`.
- Proxy **code comments and metric fields** are explicit (`proxy_lr`, `_PROXY_NOTE`).

---

## E. What is NOT complete

- A local-first **product**: import → confirm resources → download/load **this** model → bind **this** dataset → infer → probe.
- User-supplied datasets. There is no upload, no Hub dataset picker wired to `evaluations.dataset`, no label-map UI.
- Evaluation create **refusing** underspecified F/R.
- Default-path evaluation of an arbitrary imported model (the README demo `distilbert-…-sst-2` / `bert-tiny` path).
- Unmissable product distinction of model-faithful vs proxy vs documentation vs skipped robustness.
- Resource / compatibility states (`SUPPORTED` / `CONSTRAINED` / `UNSUPPORTED`).
- True artifact checksums (weight hashes).
- Using `evaluations.task` / `evaluations.dataset` as the probe contract.
- Pairing catalog beyond one fairness model and two robustness models.
- Target-architecture Safety behavioral tests, SHAP, Mode B, validated O mapping (correctly unfinished).

**Bottom line:** you can FINALIZE an evaluation that never loaded weights and never used a dataset the user named. That is the current happy path.

---

## F. Recommended implementation order

Do not resume Phase 6 polish first. Close the **product contract**.

1. **Freeze the evaluation contract (API + UI)**  
   Require, for any run that claims F or R evidence: model id, **model revision** (default from `models.revision`), **dataset logical key or pairing id**, task/label contract. Reject empty `probe_config` default Adult. Copy `models.revision` onto `evaluations.model_revision` at create.

2. **Stop silent Adult proxy as default**  
   No pairing → Fairness `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE`, not `proxy_lr` on Adult. Keep `proxy_lr` only behind an explicit operator flag (already methodology A7).

3. **Align pairing resolve with import**  
   Today exact SHA mismatch → proxy. Either pin import to pairing SHA, or resolve by `model_ref` then load the **pairing** revision and record the mismatch. Never fall through to Adult.

4. **Bind dataset identity onto the evaluation row**  
   Persist logical key, `hf_path`, dataset revision, source (`pairing` / `compat` / `explicit`). Stop using free-text `dataset` as a leaderboard-only decoration.

5. **Make A/B/C/D first-class in UI**  
   Render `fairness_mode`, `pairing_id`, robustness `resolution_source`, documentation-only for I/E/S.

6. **Load step + resource check before probes**  
   Explicit “materialize model locally” (cache dir, recorded files, failure = FAILED not FINALIZED empty F/R). Compatibility states from README Phase 2.

7. **Only then** expand pairing/compat allowlists (more models/datasets). Do not expand FRIES, Mode B, or behavioral Safety in this phase.

---

## G. Things we must NOT touch

- `backend/app/scoring/fries.py` and frozen FRIES fixtures  
- HeuristicOSDAgent numeric bands (legacy isolation)  
- Mode B / `llm_assisted`  
- Behavioral Safety suite  
- Invented O mappings / ending default FRIES withhold without validated science  
- Probe **metric formulas** (DP/EO, char-swap math, card coverage checklists) except where the contract phase must change **control flow** (when to run, what data, what status)  
- Silent rewrite of `results/` historical CSVs  
- Phase 6 honesty rules (no “AI proposed O/S/D” on deterministic; PROXY not into FRIES)

---

## H. Proposed next phase — Product Contract (local model × required dataset)

**Name:** Phase 7 — Evaluation contract (not “more honesty copy”).

**Goal:** A researcher cannot reach `FINALIZED` believing TrustLens scored *their* model on *their* data unless the run actually loaded that model (where F/R require it) on an **explicit, versioned** dataset contract.

**In scope**

- Create-evaluation schema + UI: required pairing **or** (model_revision + registry dataset key + task) **or** explicit `fairness_mode=proxy_lr` (admin/lab).  
- ProbeContext carries dataset identity; F/R read it; ignore orphan `evaluations.dataset` or replace it with the real pin.  
- Default no-pairing fairness: do not call Adult LR.  
- Import remains metadata, **plus** a documented second step *or* first-probe load that fails the evaluation if weights cannot be obtained.  
- UI surfaces mode A/B/C/D.  
- Tests: default distilbert-style import+eval must **not** emit Adult DP as if it were the HF model; HateXplain pairing still model-faithful; SHA mismatch must not silently proxy.

**Out of scope:** FRIES, Mode B, behavioral Safety, new O science, visual redesign, expanding beyond control-flow/contract.

**Exit test:** “Does this implementation evaluate a real model locally on a real required dataset?”  
Answer must be **yes** for every FINALIZED run that shows F/R `EVALUATED` / `model_faithful`, and **no silent Adult** otherwise.

---

## Appendix: Five probes (requirement 6)

| Probe | What it evaluates | Input data | User’s selected `evaluations.dataset`? | Runs user’s model? | Class | vs methodology |
| ----- | ----------------- | ---------- | -------------------------------------- | ------------------- | ----- | -------------- |
| **F** pairing | Group disparity on HateXplain labels / `target_community` | Pinned HateXplain JSON/Hub | No — YAML `pairing.dataset` | Yes, but **pairing pin** load | **A** model-faithful (allowlist) | Intended |
| **F** default | DP/EO/F1 on Adult `sex` | Pinned Adult Census | No | **No** — sklearn LR | **C** proxy | Allowed only as PROXY; **not** allowed as default product eval |
| **R** compat/explicit | Clean vs char-swap accuracy | SST-2 or AG News pin (or other registry key) | No | **Yes** `ctx.model_ref` | **A** model + **B** benchmark dataset | Intended for pinned domain; not user dataset |
| **R** else | Nothing (skip) | None | No | No | N/A skip | Consistent if not presented as robustness of the model |
| **I** | Hub identity/disclosure | `model_metadata` + revision string | No | No | **D** documentation / identity | v1 intended |
| **E** | Card section coverage | `card_text` | No | No | **D** | v1 intended |
| **S** | Governance phrases / high-impact flags | `card_text` | No | No | **D**; behavioral **DEFERRED** | v1 intended |

## Appendix: Product flow (requirement 7) — each arrow

| Arrow | Implementation |
| ----- | ---------------- |
| Import model | Hub metadata → Postgres `models`. **No local weights.** |
| Select/provide dataset | Optional text field. **Probes do not read it.** Dataset comes from YAML pairing/compat/`probe_config.datasets`/Adult default. |
| Configure task | Optional text; Hub `pipeline_tag` used for robustness tag check; pairing supplies task_type. |
| Load model locally | **Not at import.** At F pairing or R NLP `from_pretrained`. Else never. |
| Local inference | Same two paths. F default: LR `fit`/`predict` on Adult features. |
| Run probes | Always F→R→I→E→S. Soft skip / PROXY / N/A still persist a row. |
| Persist evidence | MinIO JSON + `probe_results`. |
| O/S/D | Deterministic: null. Legacy admin: heuristic bands. |
| FRIES | Only complete triples; default withheld. |
| Report | 409 if withheld; exists only if scored. |

## Appendix: Classification index

**P0** — Default eval without user dataset; default F proxy; import-only “model”; FINALIZED without local execution; pairing SHA miss → Adult; create API/UI underspecified.  
**P1** — Resource checker absent; checksum≠weights; eval vs model revision split; UI hides `fairness_mode`; pairing loads YAML identity; shared backend unused at import.  
**P2** — Stale pipeline comment; README probe table lagging pairing; card load unpinned.  
**VALID** — Deterministic withhold; I/E/S documentation vs methodology; PROXY fields in metrics; robustness skip N/A; LocalHFBackend itself.  
**DEFERRED** — Mode B, behavioral Safety, SHAP, validated O mapping, arbitrary user datasets as a *methodology* feature (still P0 as a *product* gap if the UI implies the user supplied one).
