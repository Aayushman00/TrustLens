# TrustLens Backend (Phase 22)

Layered FastAPI: routers → services → repositories/adapters/storage/probes, with JWT auth,
HF Hub import, Celery enqueue, immutable MinIO evidence, **all five FRIES probes**
real (F/R/I/E/S), a shared **Confidence Engine** (Phase 15), a **PROPOSED O/S/D
agent** plus the pure **original FRIES scorer** (Phase 16), **dual-mode policy +
disclosures** (Phase 17), the **AI-Assisted human review workflow** (Phase 18),
**report generation** (Phase 19, ADR 0009), and — Phase 22 — the **opt-in
leaderboard** (ADR 0013): owner-controlled publish/unpublish after FINALIZED
plus a published-only, context-filtered `GET /v1/leaderboard`. No OpenAPI
stubs remain (Phases 20–21 attack sim are post-MVP and unrouted).

## Architecture

```text
app/
  main.py                 create_app(), middleware, routers
  adapters/                Model Adapter boundary (Phase 6, ADR 0012)
  probes/                  FRIES probe plugins
    base.py                FRIES_PROBE_ORDER, ProbeContext, ProbeOutput, Probe
    integrity.py           IntegrityProbe (Phase 10) — metadata audit
    fairness.py            FairnessProbe (Phase 12) — Adult DP/EO/F1
    fairness_metrics.py    Pure stdlib group-fairness helpers
    explainability.py      ExplainabilityProbe (Phase 13) — card sections
    explainability_card.py ATX heading matcher + contradictions
    card_markdown.py       Shared ATX split / nontrivial body helpers
    safety.py              SafetyProbe (Phase 14) — disclosure checklist
    safety_card.py         Mandatory misuse/privacy/security/data checks
    robustness.py          RobustnessProbe (Phase 11) — NLP char_swap
    robustness_nlp.py      transformers runner (lazy import)
    stubs.py               Contract-test stubs only (not in default registry)
    registry.py            ProbeRegistry.all_ordered()
    runner.py              run_all_probes → engine-refined probe_results + evidence
  confidence/
    engine.py              ConfidenceEngine (Phase 15) — pure factors + geometric mean
  osd/
    base.py                AgentContext / AspectOSD / AgentResult / OSDAgent protocol
    agent.py               HeuristicOSDAgent (Phase 16) — PROPOSED metric→O/S/D bands
    serialize.py           AgentResult → ai_suggestion / evidence_used / finalized_osd
    review.py              Phase 18 pure merge (edits over agent) + assisted finalized_osd
  scoring/
    fries.py               Original FRIES math (Phase 16) — ∛ Π, veto, weighted T
  reports/
    builder.py             build_report_json (Phase 19) — canonical report_v1 from repos
    render.py              render_html (Jinja2) + render_pdf (WeasyPrint, optional)
    store.py               ReportStore — versioned reports/{eval_id}/v{n}/ MinIO keys
    templates/report_v1.html  print-friendly Jinja2 template (PDF projection)
  datasets/                pinned yaml + loader.py (HF subsets)
  tasks/
    celery_client.py        enqueue_evaluate_model (producer only)
    evaluate_pipeline.py    status machine + run_all_probes (shared with worker)
  storage/
    evidence_store.py       EvidenceStore — append-only MinIO artifacts (ADR 0004)
  api/
    deps.py                get_db(), get_current_user(), require_roles()
    errors.py              AppError → {code, message, details}
    middleware.py          X-Request-ID + access logs
  core/
    security.py            JWT + password hashing
  routers/v1/              auth, models, import-hf, evaluations, stubs
  schemas/
    internal.py             EvaluateModelPayload (Celery v1 contract)
    evidence.py             EvidenceRef / StoredEvidence (ADR 0004)
    probe_config.py         ProbeConfigV1
    confidence.py           API re-exports of engine types (ConfidenceSummary)
    evaluations.py          EvaluationRead + ProbeProgress + confidence_summary
                            + osd_agent + final_score (Phase 16, detail only)
                            + mode_disclosure (Phase 17, always on detail)
                            + human_review (Phase 18, detail only)
    modes.py                ModeDisclosure + locked disclaimer texts (Phase 17)
    reviews.py              AspectOSDEdit / HumanReviewRequest / HumanReviewRead (Phase 18)
    reports.py              ReportV1 (canonical schema) + ReportRead (Phase 19)
  services/                ModelService, EvaluationService, AuthService, ReportService
  db/                      ORM + Alembic + repositories
  scripts/seed_users.py
```

## Fairness probe (Phase 12)

Tabular Adult census path (not SST-2). Objective disparities only — **not** a normative
fair/unfair judgment and **not** O/S/D (`proposed_mapping: false`). When metrics are
computed, `needs_human_review` is always `true`.

| Setting | MVP default |
|---------|-------------|
| Dataset | `datasets.fairness` or **`adult_fairness`** |
| Sensitive attr | `slice_definitions.sensitive_attribute` / `extra.sensitive_attribute` or **`sex`** |
| Samples | `extra.max_samples` or **256** (clamp 20–1000) |
| Thin slice | `extra.min_group_n` or **30** → flag `insufficient_slice_size` |
| Predictions | Tiny sklearn `LogisticRegression` on non-sensitive features (tests inject Ŷ) |

| Metric | Formula |
|--------|---------|
| `demographic_parity_difference` | max−min of P(Ŷ=1\|A) |
| `equalized_odds_difference` | max(\|ΔTPR\|, \|ΔFPR\|) across groups |
| `subgroup_f1_spread` | max−min binary F1 across groups |

NLP-only pins (e.g. `sentiment_fairness`) → `unsupported_modality` + evidence; evaluation
still completes. Optional: `pip install -e ".[fairness]"`.

## Explainability probe (Phase 13)

Metadata-only model-card **section coverage** (not keyword stuffing, not NLP semantic
quality, not SHAP/LIME). Integrity still owns provenance/license/repro identity checks.

**Required sections (5):** `intended_use`, `limitations`, `training_data`, `evaluation`,
`ethical_considerations`. Bonus (tracked only): `architecture`, `citation`, `examples`.

Matcher: ATX `#`/`##`/`###` headings mapped via alias tables; optional `card_data`
fallbacks; empty heading bodies do not count (`≥20` chars).

| Metric | Formula |
|--------|---------|
| `coverage_ratio` | `sections_present / 5` ∈ [0, 1] |
| `proposed_mapping` | always `false` |

**Contradiction flags:** `empty_card`, `open_claim_vs_restrictive_license`,
`no_limitations_but_production_claim`. Also `missing_<section>` and
`needs_human_review` when `coverage_ratio < 0.6`.

## Safety probe (Phase 14)

Mandatory **safety disclosure** checklist on model-card metadata (not NLP claim
extraction, **not** FRIES2 caps, **not** O/S/D). Distinct from Explainability’s
doc-completeness sections — `ethical_considerations` does **not** satisfy `misuse_risks`.

**Required (4):** `misuse_risks`, `privacy`, `security_warnings`, `data_disclosure`.
Bonus (tracked only): `bias_and_fairness_risks`, `human_oversight`.

| Metric | Formula |
|--------|---------|
| `coverage_ratio` | `checks_present / 4` ∈ [0, 1] |
| `proposed_mapping` | always `false` |

**Flags:** `missing_<check>`, `empty_card`, `high_impact_deployment_claim` (production /
healthcare / finance / legal / autonomous / biometric heuristics), `needs_human_review`
when coverage &lt; 1.0 or high-impact present. Autonomous mode still finalizes; flags are
evidence for Assisted attention / later reports.

## Confidence Engine (Phase 15)

Pure module ([`app/confidence/engine.py`](app/confidence/engine.py), no DB/S3) that
overwrites each probe's local confidence heuristic at persist time in `run_all_probes`.
**Evidence-strength signal only — not correctness, not O/S/D** (`proposed_calibration:
true`; calibration is open, RQ5).

Three factors ∈ [0,1] per dimension, combined by **geometric mean**
(`method: "geometric_mean_v1"`); factors are floored at 0.1 so one zero signal can't
collapse the product. Overall = geometric mean of the five dimension confidences.
Factors persist in `probe_results.metric_values.confidence_factors`.

| Dimension | Lower `data_quality` | Lower `probe_reliability` |
|-----------|----------------------|---------------------------|
| Fairness | `insufficient_slice_size` / `min_group_n_observed < min_group_n` (0.55); null metrics (0.35) | `metrics_skipped` / `unsupported_modality` / `dataset_load_failed` (0.45) |
| Robustness | `n_samples` scale (≥64→1.0, ≥16→0.7, else 0.4); null accuracies (0.4) | `attack_skipped` / `unsupported_modality` / `model_load_failed` (0.45) |
| Integrity | fraction of `checks.*.pass` | — (metadata path always runs → 1.0) |
| Explainability | `coverage_ratio` (0 if `empty_card`) | `empty_card` (0.4); coverage &lt; 0.4 → weak parse (0.6) |
| Safety | `coverage_ratio` (0 if `empty_card`) | `empty_card` (0.4); `high_impact_claims` with coverage gaps (0.5) |

`evidence_completeness`: evidence_refs present (else 0.2); coverage-scaled for E/S
(`0.6 + 0.4·coverage`); Integrity bumps for the `checks` dict.

`GET /v1/evaluations/{id}` (detail only — list omits it):

```json
"confidence_summary": {
  "overall": 0.72,
  "by_dimension": {"FAIRNESS": 0.55, "ROBUSTNESS": 0.40, "INTEGRITY": 0.91,
                   "EXPLAINABILITY": 0.80, "SAFETY": 0.70},
  "method": "geometric_mean_v1",
  "proposed_calibration": true,
  "note": "Evidence strength only — not correctness or O/S/D"
}
```

## O/S/D Agent + FRIES scorer (Phase 16)

**HeuristicOSDAgent** ([`app/osd/`](app/osd/)) proposes one O/S/D triple per FRIES
dimension (0–10 ints, higher = better/safer) from persisted probe metrics —
**PROPOSED / REQUIRES VALIDATION**, never validated science. Band rules (see the
[`agent.py`](app/osd/agent.py) docstring): proposals clamp to [1, 9] (0 = veto and
10 = optimal are human-finalize calls); fairness scales `1 − disparity gap`;
robustness scales clean/robust accuracy + degradation ratio; integrity scales the
check pass rate; E/S scale `coverage_ratio` with penalties for empty cards and
high-impact claims with gaps. Aspect confidence = the probe's engine-refined
confidence; skips land in a low-mid (4, 4, 3) band.

**FRIESScorer** ([`app/scoring/fries.py`](app/scoring/fries.py)) is pure and only
consumes **finalized** O/S/D: `Π = ∛(O·S·D)` with veto (any 0 → Π = 0; O=S=D=10 →
10), aspect `Tᵢ` = mean of Π over its risks, `T = Σ ωᵢ·Tᵢ` (equal ωᵢ = 0.2 default;
custom weights must each be ≥ 0.1 and sum to 1). Oracle: frozen
[`shared/scoring/fixtures/fries_test_vectors.json`](../shared/scoring/fixtures/fries_test_vectors.json)
(golden Π ≈ 5.04, Table 8 T ≈ 5.05).

Pipeline ([`app/tasks/evaluate_pipeline.py`](app/tasks/evaluate_pipeline.py),
`run_evaluation_pipeline`): probes → agent → `osd_agent_outputs` →
`AGENT_COMPLETED`, then

- `AI_ASSISTED` → `AWAITING_REVIEW`; `final_scores` written later by the Phase 18
  human-review → finalize path (API-side, not the worker)
- `AI_AUTONOMOUS` → agent O/S/D treated as finalized (labeled) → scorer → upsert
  `final_scores` → `FINALIZED`

Detail API adds `osd_agent` (latest suggestion + `methodology_status`) and
`final_score` (`fries_score`, `dimension_scores`, mode) — both null until present.

## Dual-mode policy + finalize (Phase 17, ADR 0011)

`GET /v1/evaluations/{id}` always includes `mode_disclosure`
(`evaluation_mode`, `human_reviewed`, `disclaimer`, `methodology_status`), built
by [`app/schemas/modes.py`](app/schemas/modes.py) — the single source of the
locked disclaimer texts (vendored into the worker so persisted wording matches).
`final_score` is denormalized with `human_reviewed` + `disclaimer`; the
Autonomous pipeline persists both inside `final_scores.finalized_osd`.

`POST /v1/evaluations/{id}/finalize` (RBAC: reviewer/admin for Assisted, any
authenticated user for Autonomous):

| State | Response |
|-------|----------|
| FINALIZED + final_scores row (any mode) | 200 — enriched `EvaluationRead`, idempotent |
| FAILED | 409 `FAILED_EVALUATION` |
| Autonomous, not finalized yet | 409 `NOT_READY` (pipeline is the sole writer; no recompute — re-enqueue) |
| Assisted before AWAITING_REVIEW | 409 `NOT_READY` |
| Assisted at AWAITING_REVIEW, no human_reviews row | 409 `REVIEW_REQUIRED` (details point to human-review) |
| Assisted with a human_reviews row | 200 — human-approved O/S/D → FRIES → `final_scores` → FINALIZED (Phase 18) |

## Human review workflow (Phase 18)

`POST /v1/evaluations/{id}/human-review` (`reviewer`/`admin`, 201) submits a
structured accept/edit of the latest agent suggestion while an **Assisted**
evaluation is at `AWAITING_REVIEW`:

```json
{"accept_all": false,
 "aspects": [{"aspect": "FAIRNESS", "O": 0, "S": 5, "D": 6}],
 "notes": "optional", "review_rationale": "optional"}
```

Merge rules ([`app/osd/review.py`](app/osd/review.py), pure):

- `accept_all=true` → agent suggestion taken as-is (`aspects` must be omitted;
  422 otherwise). `accept_all=false` → ≥ 1 aspect edit required.
- Edited aspects override the agent triple; missing aspects keep agent values.
  Duplicate/unknown aspects → 422.
- Humans may set the extremes the heuristic agent never proposes: `0` (veto)
  and `10` (optimal) — `ge=0, le=10` per component.
- `human_changed` = any approved triple differs from the agent snapshot.
- Each POST appends a `human_reviews` row (`overrides` JSON keeps the approved
  O/S/D + agent snapshot + rationale — audit trail); **latest wins** at finalize.

Guards: 404 missing eval; 409 `ASSISTED_ONLY` (Autonomous), `ALREADY_FINALIZED`,
`FAILED_EVALUATION`, `NOT_READY` (before `AWAITING_REVIEW` or no agent output).

Finalize then builds `finalized_osd` from the latest review's approved O/S/D
with `human_reviewed=true`, `source="human_review_assisted"`, the reviewed
disclaimer, and the PROPOSED methodology label (the metric→O/S/D heuristic
remains unvalidated even after human approval), scores it with the pure FRIES
scorer, upserts `final_scores` (`overall_confidence` = agent `ai_confidence`),
and transitions `AWAITING_REVIEW → FINALIZED` (race-safe conditional update).
`GET /v1/evaluations/{id}` includes the latest review as `human_review`; the
`mode_disclosure` flips to the reviewed disclaimer **only after** finalize.

## Robustness probe (Phase 11)

NLP text-classification path only (vision/ART FGSM deferred). Objective metrics —
**not** O/S/D and **not** product FRIES (`proposed_mapping: false`).

| Setting | MVP default |
|---------|-------------|
| Attack | Discrete `char_swap` (max char substitutions) |
| Budget | `probe_config.attack_budget` or **0.03** → `max_changes = clamp(round(budget*100), 1, 8)` |
| Seed | `extra.seed` or **42** |
| Samples | `extra.max_samples` or **64** (clamp 8–128) |
| Dataset | `datasets.robustness` or `ag_news_robustness` |

Metrics include `clean_accuracy`, `robust_accuracy`, `degradation_ratio` (= robust/clean),
`attack_success_rate`. Non-classification models / vision datasets → flags
`unsupported_modality` + `attack_skipped` (evaluation still completes).

Optional backend install for local runs: `pip install -e ".[robustness]"`. Unit tests use
an injectable fake runner and do **not** require torch.

Recommended live model: `distilbert-base-uncased-finetuned-sst-2-english` (plain DistilBERT
MLM will skip as unsupported modality).

## Integrity probe (Phase 10)

Metadata-only audit (no weight downloads). Emits metrics + evidence for a future O/S/D
Agent — **not** product FRIES and **not** finalized O/S/D.

| Check | Pass when |
|-------|-----------|
| `revision_pinned` | Non-empty Model.revision / checksum (prefer SHA-like) |
| `files_listed` | Non-empty `metadata.files` |
| `license_declared` | Structured `license` / `card_data.license` (card text alone → fail + flag) |
| `card_present` | Non-empty `card_text` |
| `reproducibility_claims` | ≥2 keyword signal groups in card (heuristic; not ground truth) |
| `checksum_recorded` | Non-empty files → `files_fingerprint=sha256:` of sorted names (+ revision) |

**Proposed score (REQUIRES VALIDATION):** base `10.0`, six equal weights, each fail deducts
`10/6`; clamp to `[0, 10]` as `integrity_score_0_10`. Metrics include
`"proposed_mapping": true` and `"scoring": "equal_weight_base_10"`.

## Probe plugins (Phase 9+)

```text
ProbeRegistry (F→R→I→E→S)
  └─ FairnessProbe / RobustnessProbe / IntegrityProbe / ExplainabilityProbe / SafetyProbe
       └─ put_artifact → EvidenceRef → probe_results row
```

- Contract: `Probe.run(ProbeContext) → ProbeOutput` — metrics, confidence ∈ [0,1],
  evidence_refs, flags. Probes must **not** assign O/S/D or FRIES scores.
- `ProbeContext` includes `model_revision` / `model_checksum` from the Model ORM.
- `probe_config` validated as `ProbeConfigV1` on create; dataset keys must exist in
  [`configs/datasets_v1.yaml`](../configs/datasets_v1.yaml).
- Phase 15: the runner refines each probe's confidence via the Confidence Engine
  before persisting (see below); probe-local heuristics remain the raw input.

## Evaluation jobs (Phase 7+, ADR 0005)

### Enqueue contract

Task name: `trustlens.evaluate_model` (stable string on API + worker).

```json
{
  "schema_version": "v1",
  "evaluation_id": "<uuid>",
  "model_ref": "<hf_repo_id>",
  "evaluation_mode": "AI_ASSISTED | AI_AUTONOMOUS",
  "probe_config": {"schema_version": "v1", "datasets": {}}
}
```

`POST /v1/evaluations` creates a `PENDING` row, validates/normalizes `probe_config`,
builds the payload from the linked model's `hf_repo_id`, and calls
`enqueue_evaluate_model`. If `REDIS_URL` is unset (or the broker is unreachable), enqueue
is skipped with a warning and the row stays `PENDING` — useful for host-side tests.

### Status machine

| From | To | Notes |
|------|-----|-------|
| PENDING | RUNNING | Worker pick-up |
| RUNNING | PROBES_COMPLETED | After all 5 probes |
| PROBES_COMPLETED | AGENT_COMPLETED | Stub; no `osd_agent_outputs` yet |
| AGENT_COMPLETED | AWAITING_REVIEW | `AI_ASSISTED` |
| AGENT_COMPLETED | FINALIZED | `AI_AUTONOMOUS` |
| * | FAILED | Logic/error path |

Transitions use `EvaluationRepository.transition_status` (atomic `UPDATE … WHERE status IN
expected`) so duplicate/stale updates are no-ops.

### probe_progress (GET by id)

```json
{"completed": 5, "total": 5}
```

`total` is always 5. After a successful run, `completed` is 5. List endpoints leave
`probe_progress` as `null`.

`POST /v1/models` (manual create) and HF import are unchanged.

## Evidence storage (Phase 8, ADR 0004)

[`app.storage.EvidenceStore`](app/storage/evidence_store.py) writes probe metrics JSON to
MinIO. Probe-agnostic: Integrity and stubs call the same `put_artifact` API.

| Concern | Rule |
|---------|------|
| Key layout | `evidence/{evaluation_id}/{evidence_id}.json` |
| URI | `s3://{bucket}/{key}` |
| Hash | `sha256:<hex>` of object bytes |
| Policy | Append-only — new put ⇒ new `evidence_id` + key; never overwrite/delete in MVP |
| Content | Metrics JSON only — never model weights |

`verify_artifact` / `verify_ref` re-fetch bytes and compare hashes (tamper detection).
Five evidence refs per evaluation (one per dimension). S3 put / probe failures → `FAILED`
(no Celery retry for store/logic errors).

Factory: `get_evidence_store(settings) → EvidenceStore | None` (None if S3 unset).
## Hugging Face Hub model ingestion (Phase 6, ADR 0012)

`POST /v1/models/import-hf` resolves a **user-selected** HF repo id or URL to metadata —
never automatic Hub crawling, never weight downloads, never website scraping. The
evaluation engine (Phase 9+) will depend only on `app.adapters.base.NormalizedModelRecord`
/ `ModelAdapter`, never on `huggingface_hub` directly.

### Request

Exactly one of `repo_id` or `url` (enforced by a Pydantic `model_validator`):

```json
{"repo_id": "distilbert-base-uncased"}
{"url": "https://huggingface.co/org/model-name/tree/main"}
{"repo_id": "org/model-name", "revision": "a1b2c3d"}
```

Accepted URL shapes: `https://huggingface.co/<model>`, `https://huggingface.co/<org>/<model>`,
and `.../tree/<rev>`, `.../blob/<rev>/...`, `.../commit/<sha>`, `.../resolve/<rev>/...`
(revision is extracted from the path). Only `huggingface.co`/`www.huggingface.co` hosts are
accepted — this is the SSRF guard; anything else is `422 INVALID_MODEL_REF`.

### Resolution (`app.adapters.hf_hub.HfHubModelAdapter`)

Uses `huggingface_hub.HfApi` only — metadata calls, no file downloads:

1. `HfApi().model_info(repo_id, revision=...)` — tags, `pipeline_tag`, `library_name`,
   `card_data`, `config.architectures`, and the resolved commit `sha`.
2. `HfApi().list_repo_files(repo_id, revision=sha)` — **filenames only**, never fetched.
3. `ModelCard.load(repo_id)` — model card markdown text (best-effort; missing cards don't
   fail the import).
4. The resolved commit `sha` is pinned as both `revision` and `checksum` (a commit-SHA
   proxy, per the ADR/roadmap — TrustLens doesn't compute a weights checksum since weights
   are never downloaded).

`HF_TOKEN` (optional, `.env`) is passed to all three calls for gated/private repos you have
access to; public repos work without it.

### Normalized `model_metadata` (JSONB)

```json
{
  "source": "huggingface_hub",
  "architecture": "DistilBertForMaskedLM",
  "pipeline_tag": "fill-mask",
  "task": "fill-mask",
  "license": "apache-2.0",
  "tags": ["transformers", "pytorch", "..."],
  "card_text": "# DistilBERT base model...",
  "card_data": {"language": "en", "license": "apache-2.0", "...": "..."},
  "files": ["config.json", "pytorch_model.bin", "tokenizer.json", "..."],
  "library_name": "transformers",
  "transformers_info": {"auto_model": "AutoModelForMaskedLM", "...": "..."},
  "hub_url": "https://huggingface.co/distilbert-base-uncased"
}
```

### Upsert policy

`import_from_hf` looks up the resolved `hf_repo_id`:

- **Not found** → create a new row → `201 Created`.
- **Found** → refresh `model_metadata`/`revision`/`checksum` in place (re-import refreshes
  metadata, e.g. after an upstream model card update) → still `201 Created` (the route's
  status code is fixed; the response body's `id` is unchanged on update, confirming no
  duplicate row was created).

`POST /v1/models` (manual create, unchanged) still `409 CONFLICT`s on a duplicate
`hf_repo_id` — only `import-hf` upserts.

### Error codes (Phase 6)

| Code | Status | When |
|------|--------|------|
| `INVALID_MODEL_REF` | 422 | Malformed repo id, or URL host isn't `huggingface.co` |
| `VALIDATION_ERROR` | 422 | Neither/both of `repo_id`/`url` provided (Pydantic) |
| `MODEL_NOT_FOUND` | 404 | Repo or revision doesn't exist on the Hub |
| `HF_AUTH_REQUIRED` | 403 | Gated/private repo and no (or insufficient) `HF_TOKEN` |
| `HF_HUB_UNAVAILABLE` | 502 | Network/API failure talking to the Hub |

### Scope guards (ADR 0012)

No automatic crawling/search/index endpoints, no local filesystem or upload import paths,
no downloading of model weight files at import time. Each import is logged (info level)
with `request_id` (via the existing `X-Request-ID` logging filter) and the requesting
user's email.

## Authentication and authorization (Phase 5)

- **Login:** `POST /v1/auth/login` with `{email, password}` → `{access_token, refresh_token,
  token_type, expires_in}`. Bad credentials return a generic `401 UNAUTHORIZED` message
  (`"Invalid email or password"`) — never reveals whether the email exists.
- **Refresh:** `POST /v1/auth/refresh` with `{refresh_token}` → a new **rotated** access +
  refresh pair (old refresh token is not persisted/tracked; rotation alone is the MVP
  revocation story — see "Out of scope" below).
- **Current user:** `GET /v1/auth/me` (Bearer) → `{id, email, role}` — never
  `password_hash`.
- **Token lifetimes:** access = 15 minutes, refresh = 7 days (`JWT_ACCESS_EXPIRE_MINUTES`,
  `JWT_REFRESH_EXPIRE_DAYS`).
- **All other `/v1/*` routes require `Authorization: Bearer <access_token>`.** Missing,
  malformed, or expired tokens → `401` (`UNAUTHORIZED` if missing, `INVALID_TOKEN` if
  present but invalid/expired).

### Roles

| Role | Notes |
|------|-------|
| `researcher` | Default role; can create/read models & evaluations; owner of evaluations they create |
| `reviewer` | Everything a researcher can do, plus human-review and AI-Assisted finalize |
| `admin` | Everything, including publish/unpublish on any evaluation |

### RBAC on evaluation lifecycle routes

| Route | Policy |
|-------|--------|
| `POST /v1/evaluations/{id}/human-review` | `reviewer` or `admin` only → else `403 FORBIDDEN` (real since Phase 18) |
| `POST /v1/evaluations/{id}/finalize` | `AI_ASSISTED` evaluation → `reviewer`/`admin` only; `AI_AUTONOMOUS` → any authenticated user |
| `POST /v1/evaluations/{id}/publish` | Evaluation owner (`created_by`) or `admin` → else `403 FORBIDDEN` (real since Phase 22) |
| `POST /v1/evaluations/{id}/unpublish` | Same as publish |
| `GET /v1/reports/{id}` + `POST /v1/reports/{id}/generate` | Any authenticated user (documented MVP choice — reports expose nothing beyond evaluation detail reads) |
| `GET /v1/leaderboard` | Any authenticated user (Bearer kept for MVP; "public" = published-only visibility, not anonymous) |

`POST /v1/evaluations` sets `created_by` to the authenticated user's id (nullable FK,
`SET NULL` on user deletion — Alembic `002_add_evaluation_created_by`).

### Dev seed users

```powershell
make seed-users
# or: docker compose exec api python -m app.scripts.seed_users
```

| Email | Role | Password env var | Default (dev only) |
|-------|------|-------------------|---------------------|
| admin@trustlens.local | admin | `SEED_ADMIN_PASSWORD` | `trustlens-admin-dev` |
| researcher@trustlens.local | researcher | `SEED_RESEARCHER_PASSWORD` | `trustlens-researcher-dev` |
| reviewer@trustlens.local | reviewer | `SEED_REVIEWER_PASSWORD` | `trustlens-reviewer-dev` |

Seeding is idempotent — re-running skips any email that already exists.

### Env vars (see `.env.example`)

`JWT_SECRET`, `JWT_ALGORITHM` (default `HS256`), `JWT_ACCESS_EXPIRE_MINUTES` (default 15),
`JWT_REFRESH_EXPIRE_DAYS` (default 7). The API **fails fast at startup** if `APP_ENV` is not
`development`/`test` and `JWT_SECRET` is still the placeholder value.

### Out of scope (Phase 5)

OAuth/SSO, rate limiting, refresh-token blacklist/revocation table (rotation alone is OK for
MVP), real publish/unpublish logic (Phase 22), frontend login UI (Phase 23).

## Error format

```json
{"code": "NOT_FOUND", "message": "Model 42 not found", "details": {"model_id": 42}}
```

Every response includes `X-Request-ID`.

## Implemented routes

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/health` | Public | Dependency checks (503 if postgres/redis down) |
| POST | `/v1/auth/login` | Public | Returns access + refresh tokens |
| POST | `/v1/auth/refresh` | Public | Rotated access + refresh tokens |
| GET | `/v1/auth/me` | Bearer | Current user (no `password_hash`) |
| POST | `/v1/models` | Bearer | Manual registry create |
| GET | `/v1/models` | Bearer | List (`limit`, `cursor`) |
| GET | `/v1/models/{id}` | Bearer | Get by id |
| POST | `/v1/models/import-hf` | Bearer | Resolve HF repo id/URL via Hub metadata API; upsert (see above) |
| POST | `/v1/evaluations` | Bearer | Create `PENDING`, enqueue Celery stub job; sets `created_by` |
| GET | `/v1/evaluations` | Bearer | List; optional `?status=` |
| GET | `/v1/evaluations/{id}` | Bearer | Get by UUID + enriched detail (progress, confidence, osd_agent, final_score, mode_disclosure, human_review) |
| POST | `/v1/evaluations/{id}/human-review` | Bearer (reviewer/admin) | Accept/edit agent O/S/D (Phase 18, see workflow above) |
| POST | `/v1/evaluations/{id}/finalize` | Bearer (see RBAC) | Dual-mode finalize policy; Assisted writes FRIES from the approved O/S/D |
| GET | `/v1/reports/{id}` | Bearer | Latest report_v1 (auto-generates v1 for FINALIZED evals); 409 `NOT_FINALIZED` otherwise |
| POST | `/v1/reports/{id}/generate` | Bearer | Force-regenerate as version latest+1 (append-only) |
| POST | `/v1/evaluations/{id}/publish` | Bearer (owner/admin) | Opt-in leaderboard publish; FINALIZED only (409 `NOT_FINALIZED`); idempotent |
| POST | `/v1/evaluations/{id}/unpublish` | Bearer (owner/admin) | Revoke publish; clears `published_at`/`published_by`; idempotent |
| GET | `/v1/leaderboard` | Bearer | Published + FINALIZED only; `task`/`dataset`/`evaluation_mode` filters + cursor (see below) |

## Reports (Phase 19, ADR 0009)

The **canonical JSON** (`report_v1`) is the source of truth; the PDF is a
projection rendered from the same JSON (Jinja2 `report_v1.html` → WeasyPrint).
`ReportService` guards (404 / 409 `NOT_FINALIZED` — requires `FINALIZED` +
`final_scores` row), builds via `build_report_json`, stores both artifacts, and
inserts a versioned `reports` row.

Top-level JSON keys: `schema_version` (`"report_v1"`), `report_version`,
`generated_at`, `evaluation` (id/status/mode/model_ref/model_id/created_at/
`finalized_context`), `mode_disclosure` (verbatim Phase 17/18 wording),
`score` (`score_type="original_FRIES"`, `fries_score`, `dimension_scores`,
`finalized_osd`, `overall_confidence`, not-ground-truth `note`),
`confidence_summary`, `probes[]` (dimension/metric_values/confidence/`flags`/
`evidence_refs` with ids + sha256 hashes), `osd_agent` (PROPOSED), `human_review`,
`attack_flags` (empty until Phases 20–21), `executive_summary`.

Storage layout (append-only; new version = new keys, never overwritten):

```text
s3://trustlens/reports/{evaluation_id}/v1/report.json
s3://trustlens/reports/{evaluation_id}/v1/report.pdf   # when PDF enabled
s3://trustlens/reports/{evaluation_id}/v2/report.json  # after POST generate
```

`GET` returns the latest `reports` row with the stored JSON read back from MinIO
(not rebuilt) + `json_uri`/`pdf_uri`/hashes; the first `GET` on a FINALIZED
evaluation auto-generates version 1. sha256 hashes are returned in the response
and stored as S3 object metadata (no DB columns).

**PDF / WeasyPrint:** `Dockerfile.api` installs `libpango-1.0-0
libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core
shared-mime-info`. On hosts without these (e.g. Windows), or with
`REPORT_PDF_ENABLED=false`, PDF generation degrades gracefully: a warning is
logged and the report ships with `pdf_uri=null` (JSON always generated).

## Leaderboard (Phase 22, ADR 0013)

Opt-in only: evaluations are **private by default** and finalize never
auto-publishes. `POST /v1/evaluations/{id}/publish` (owner/admin) requires
`FINALIZED` + a `final_scores` row (else 409 `NOT_FINALIZED`), stamps
`published_at`/`published_by`, and is idempotent — republishing keeps the
original stamp. `unpublish` clears both fields (documented choice; republish
restamps). Publish is a pure DB flip — no report generation is triggered;
leaderboard entries attach the latest report URIs when a report exists.

`GET /v1/leaderboard` query params: `task`, `dataset` (exact match),
`evaluation_mode` (`AI_ASSISTED` | `AI_AUTONOMOUS`), `limit` (default 50, max
200), `cursor` (opaque — last row's evaluation UUID). Only
`is_published=true` + `FINALIZED` rows joined to `final_scores` are listed,
sorted `fries_score desc, published_at desc, id desc` (keyset pagination).
Entry fields: `evaluation_id`, `model_id`, `hf_repo_id`, `model_revision`,
`evaluation_mode`, `human_reviewed` (from `finalized_osd`), `task`, `dataset`,
`config`, `trustlens_version`, `fries_score`, `overall_confidence`,
`published_at`, `report {version, json_uri, pdf_uri} | null`. When `task` is
omitted the response `note` warns entries may not be comparable across tasks —
the leaderboard never implies a universal cross-task trust ranking.

## Run

```powershell
docker compose up --build -d
docker compose exec api alembic upgrade head
make seed-users

# Login
docker compose exec api curl -s -X POST http://127.0.0.1:8000/v1/auth/login `
  -H "Content-Type: application/json" `
  -d "{\"email\":\"researcher@trustlens.local\",\"password\":\"trustlens-researcher-dev\"}"

# Use the returned access_token
docker compose exec api curl -s http://127.0.0.1:8000/v1/models `
  -H "Authorization: Bearer <access_token>"
# OpenAPI: http://127.0.0.1:8000/docs
```

## Test

```powershell
cd backend
python -m pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens"
python -m pytest -q
```

## Out of scope

Vision/ART FGSM robustness, FRIES2 caps, NLP card-quality / risk extraction,
public evidence download API, attack simulation (20–21, post-MVP), frontend
leaderboard page / demo UI (23), anonymous public leaderboard access / CDN,
auto-publish on finalize, cryptographic report signing.
Treating DP/EO/F1, card `coverage_ratio`, safety checklist coverage,
`integrity_score_0_10`, or robustness accuracies as product FRIES / O/S/D.
