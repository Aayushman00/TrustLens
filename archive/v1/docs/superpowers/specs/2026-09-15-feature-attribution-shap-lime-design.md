# FEATURE_ATTRIBUTION (SHAP/LIME) — Design Doc

Status: DRAFT — no code/migrations yet. Locked constraints from prior turn:
- Fully separate from FRIES probe system. Never touches `FriesDimension`, `ProbeRegistry`, `probe_results`, confidence engine, `dimension_scores`.
- v1 = text-classification models only, via existing `LocalHFBackend`.
- Own backend package, persistence model, API surface, frontend panel.

## 1. Architecture

New package `backend/app/attribution/`:

```
backend/app/attribution/
  __init__.py
  service.py        # AttributionService — orchestration
  shap_text.py       # SHAP explainer wrapper for HF text-classification
  schemas.py         # FeatureAttributionRead / Request / TokenAttribution
  errors.py          # UnsupportedModelTypeError etc (AppError subclasses)
```

Data flow (one request):
`model_id + text + method` → `ModelRepository.get_by_id` (existing) → `LocalHFBackend.load(hf_repo_id, revision)` (existing, `app/inference/local_hf.py`) → `predict_batch([text])` for the predicted label/score (existing `BatchPrediction`) → SHAP explainer runs against the same loaded model/tokenizer → `TokenAttribution[]` built → row persisted + full raw SHAP output written as an evidence artifact via `EvidenceStore.put_artifact` (existing, already probe-agnostic per its own docstring) → `FeatureAttributionRead` returned.

Reused as-is (no duplication):
- `app/inference/base.py` (`InferenceBackend`, `TaskType`, `InferenceConfig`) and `app/inference/local_hf.py` (`LocalHFBackend`) — same load/predict contract Robustness already uses.
- `app/storage/evidence_store.py` (`EvidenceStore.put_artifact`) — generic MinIO writer, takes `probe_name` as a free-text label (pass `"feature_attribution"`), no coupling to `FriesDimension`.
- `app/db/repositories/model.py` (`ModelRepository`) — resolve `model_id` → `hf_repo_id`/`revision`.
- `app/api/errors.py` (`AppError`, `NotFoundError`, `ValidationAppError`) — same `{code, message, details}` envelope every other router uses.
- `app/core/config.py` (`Settings.hf_token`) — same token resolution `LocalHFBackend` already does internally.

No auth dependency anywhere — confirmed via `alembic/versions/008_remove_auth_and_ownership.py`, auth was deliberately removed from this codebase. New router carries none, matching every existing `/v1/*` router.

Not reused, deliberately: `ProbeContext`, `ProbeOutput`, `ProbeRegistry`, `run_all_probes`, `confidence.engine.refine`, `ProbeResultRepository`. None of these fit — they all assume a `FriesDimension`-scoped, evaluation-lifecycle-bound run.

## 2. Persistence

New table `feature_attribution_results` (new model in `app/db/models.py`, separate from `ProbeResult`):

| column | type | notes |
|---|---|---|
| id | UUID pk | |
| model_id | int, FK `models.id` | required — attribution is model-centric |
| evaluation_id | UUID, nullable, **no FK** | see open question §9 |
| method | varchar | `"shap"` only in v1, schema allows future values |
| input_text | text | as submitted |
| input_hash | varchar(71) | sha256, dedupe/audit, same `format_sha256` helper as evidence store |
| predicted_label | varchar | from `id2label` |
| predicted_index | int | |
| predicted_score | float | |
| label_space | JSONB | `id2label` snapshot at run time |
| token_attributions | JSONB | `[{token, weight, position}]` |
| model_ref | varchar | frozen identity, same pattern as `robustness.py`'s `base_metrics["model_ref"]` |
| model_revision | varchar, nullable | |
| inference_metadata | JSONB | device/GPU info, same shape as `DeviceInfo` (reuse the dataclass, don't invent a new one) |
| methodology_version | varchar | e.g. `"tl-attribution-v1.0"` |
| status | varchar | `EVALUATED` \| `FAILED` \| `UNSUPPORTED_MODEL_TYPE` |
| status_reason | text, nullable | |
| evidence_refs | JSONB | `[EvidenceRef]`, reuse existing schema verbatim |
| created_at | timestamptz | |

New migration `alembic/versions/014_add_feature_attribution_results.py` (next after the current head, `013_add_positive_label_index.py`).

`EvidenceRef`'s own docstring currently reads "Immutable reference stored in `probe_results.evidence_refs` JSONB" — that's a words-only artifact of the schema having only ever had one caller, not an FK or code coupling. Reusing it here is fine; the docstring gets a one-line update (drop the `probe_results`-specific wording) when this ships, so it doesn't misdescribe its own second caller.

One row = one (model, input_text, method) run. The row holds the queryable summary; the full raw SHAP `Explanation` object (base values, all per-class arrays, masker config) goes into the MinIO evidence blob via `put_artifact`, mirroring exactly how every probe splits "metrics in DB" vs "full artifact in evidence store."

Persist: token weights, prediction, model identity+revision, device info, method+config, status. Do **not** persist: model weights/activations, a fabricated "confidence" number implying correctness (see §5), any `FriesDimension`/FRIES-relevant field — this table must never be joinable into `dimension_scores` or report scoring.

## 3. API

New router `backend/app/routers/v1/attribution.py`, prefix `/attribution`. Registration is a two-line addition to `backend/app/routers/v1/__init__.py`, matching the existing pattern exactly:
```python
from app.routers.v1 import (..., attribution, ...)
api_router.include_router(attribution.router)
```

- `POST /v1/attribution/runs` — body `{model_id: int, text: str, method: "shap", model_revision?: str}`. Synchronous (see rationale below). Response: `FeatureAttributionRead`.
- `GET /v1/attribution/runs/{id}` — fetch a stored result.
- `GET /v1/attribution/runs?model_id=&limit=&cursor=` — cursor list, same `CursorPage` convention as `ModelList`/`EvaluationList` (`CursorPage` is a thin stub — `next_cursor: str | None` only — so this buys shape consistency, not real pagination infra; cursor encoding is each list endpoint's own job, same as today).

Validation / errors (all via existing `AppError` machinery, no new error-handling infra):
- `model_id` not found → `NotFoundError` (404).
- `text` empty or over a length cap (recommend 2000 chars) → `ValidationAppError` (422).
- `method` not in `{"shap"}` → `ValidationAppError` (422) — reject `"lime"` explicitly rather than silently ignoring, since the schema's `Literal["shap","lime"]` allows it structurally.
- Model loads but isn't a sequence-classification head (`LocalHFBackend.load` already raises `InferenceError(UNSUPPORTED_TASK, ...)`) → caught and mapped to a new `UnsupportedModelTypeError(AppError)` → 422, code `"UNSUPPORTED_MODEL_TYPE"`.

Sync vs async: v1 stays **synchronous**, unlike Robustness/Fairness which run under Celery (`worker/app/tasks/evaluate.py`). Justification: this is one short text through one forward pass + one SHAP explainer call — bounded, interactive, "explain this prediction now" UX, not a dataset-wide batch job. The async path exists in this codebase (`celery_app`, `task_default_queue="trustlens"`) and can be reused unchanged in a later phase if usage shows this needs queuing (see §7 performance flag — this is the one place sync is a real risk, not a free choice).

## 4. SHAP vs LIME

Both are viable for HF text-classification (`shap.Explainer` over a `transformers.pipeline("text-classification", model=..., tokenizer=...)`; `lime.lime_text.LimeTextExplainer`). For v1, single short input, single call:

- **SHAP**: `shap.Explainer` auto-selects a Partition/Permutation explainer for a HF pipeline, returns per-token Shapley-value estimates for the predicted class directly, multiclass output falls out of the same call (values indexed by class), actively maintained transformers integration, and is the term normally meant by "feature attribution" in ML-trust tooling — matches this feature's own name.
- **LIME**: perturbs the input (word removal/replacement), fits a local linear surrogate, must be re-invoked per class of interest for multiclass, weaker theoretical grounding (local surrogate fit, not an axiomatic allocation), lighter dependency footprint but no meaningful compute advantage here since input is a single short string either way.

**Recommendation: SHAP only for v1.** Do not add LIME for parity — no computational or coverage reason to at this scope, and the user's own instruction was not to duplicate libraries without justification. Keep `method: Literal["shap", "lime"]` in the schema (so a v2 LIME addition is additive, not a migration) but reject `"lime"` at the API layer until implemented.

Dependency: `shap` only, gated the same way `torch`/`transformers` are gated today — an optional extra (e.g. `trustlens-backend[attribution]`), following the exact pattern `LocalHFBackend.load()` uses (`ImportError` → `InferenceError(MODEL_LOAD_ERROR, "... install trustlens-backend[robustness]")`).

## 5. Evidence semantics

A feature-attribution result states: for **this one input text** and **this one loaded model snapshot** (`model_ref` + `model_revision`), the SHAP explainer's local estimate of how much each token's presence shifted the model's output score toward the predicted class.

It is **not**: a causal claim about the real-world concept a token represents, a statement about the model's global decision logic (single-instance only), or a faithfulness guarantee (SHAP's Partition/Permutation explainer is an approximation — its own background/masker choice affects the numbers).

No numeric "confidence" field — a confidence score would misleadingly imply the *correctness* of the attribution is quantified, which SHAP doesn't provide. Instead, every result carries a fixed `limitations: list[str]`, always populated (not conditional), e.g.:
```
["single-instance explanation, not global model behavior",
 "approximate — Shapley values are estimated by sampling, not exact for non-linear models",
 "sensitive to explainer configuration (background distribution / masker choice)"]
```
This mirrors how `ExplainabilityProbe`/`RobustnessProbe` already always emit a `limitations`/`reliability` block rather than a single trust-implying scalar.

## 6. Frontend

New standalone page, `frontend/src/pages/FeatureAttributionPage.tsx` — **not** inside `DimensionCard.tsx`, `EvidenceDossier.tsx`, or `ReportTraceabilityPanel.tsx` (all three are keyed to `FriesDimension` in `api/types.ts`). Entry point: an action on `ModelDetailPage.tsx` ("Explain a prediction"), since this is model-centric and ad hoc, not evaluation-lifecycle-bound.

Displayed: input text (editable), predicted label + score, method (`SHAP`), per-token rendering with signed color/intensity (positive = supports predicted label, negative = opposes), model_ref + revision, generated_at, and the fixed limitations block always visible (not collapsed away — matches the intent of §5).

States: loading (explicit "loading model — first request can take longer" message, since `LocalHFBackend.load()` does a real `from_pretrained` call), failure (reuse existing `ErrorNotice` component), unsupported-model (distinct message for `UNSUPPORTED_MODEL_TYPE`, not the generic error path, so the text-classification-only v1 scope is legible to the user), empty (bare input form, no prior submission).

## 7. Security / performance

- Input cap (recommend 2000 chars) enforced server-side — unbounded text inflates both tokenization and SHAP's permutation cost.
- Loading an arbitrary `hf_repo_id` via `from_pretrained` is an existing accepted risk (Robustness already does this) — no new surface, same caveat (only import trusted repos, already gated at model-import time).
- **Real risk, now resolved for v1**: this is a new *synchronous* endpoint that loads a full transformer model per call. Robustness/Fairness do the same load but always under Celery's single-queue serialization; this endpoint has no such gate. `LocalHFBackend` is a stateful, non-thread-safe instance (mutable `_model`/`_tokenizer`/`_device` fields) — it must never be shared or cached across concurrent requests without a lock, and v1 adds no such lock. **Decision: v1 constructs a fresh `LocalHFBackend()` instance per request, used and discarded within that request** — no process-wide model cache, no cross-request reuse. This is correct-but-slow (full reload every call) rather than fast-but-unsafe; a warm-model cache is explicitly deferred, not silently assumed. Recommend a request timeout (~30s) at minimum for v1; revisit queuing (or a locked cache) in phase 2 if usage shows concurrent or repeated-model traffic.
- No rate limiting exists anywhere in this codebase today (checked `main.py`'s middleware stack) — pre-existing gap, worth naming since this feature adds a cheap trigger for repeated full model loads, but not this feature's job to fix.

## 8. Future extensibility

Keep two discriminators open from v1 even though only one value each is valid today, so phase-2 additions are additive, not a schema migration:
- `method: Literal["shap", "lime", ...]` (already covered above).
- `modality: Literal["text"]` in the persisted row and request schema (reject anything else at the API layer now) — phase 2 image support would add a `LocalVisionBackend` (new `InferenceBackend` impl) + `shap.maskers.Image`, phase 2 tabular would add a tabular backend + `TreeExplainer`/`KernelExplainer`, both dispatched by `modality` inside `AttributionService` without touching the v1 text path.

## Recommended design

Everything in §1–§8 above: separate `app/attribution/` package, new `feature_attribution_results` table, sync `/v1/attribution/*` router, SHAP-only v1, standalone frontend page off `ModelDetailPage`.

## Rejected alternatives

- **6th `FriesDimension` value** — rejected per locked constraint; would force a Postgres enum migration, a new confidence-engine factor function, and a `dimension_scores` schema change purely to carry a non-O/S/D-scored diagnostic.
- **Reuse `probe_results` with a nullable `dimension`** — rejected. `ProbeResult.dimension` is backed by the non-null `fries_dimension_enum` Postgres type; relaxing that to nullable is itself a migration with the same blast radius as touching the enum directly, so it buys nothing over a dedicated table.
- **Both SHAP and LIME in v1** — rejected; no coverage or cost reason at this scope, and the brief was explicit not to duplicate for parity alone.
- **Celery/async execution in v1** — rejected for now; single short text is sub-several-second and better served as an immediate interactive response. The async path exists unchanged in this codebase if phase 2 needs it.

## Unresolved decisions

- Text length cap exact value (2000 chars proposed, arbitrary).
- Request timeout value for the synchronous endpoint (30s proposed, arbitrary).
- Optional extra name (`trustlens-backend[attribution]` proposed, matches existing `[robustness]` convention).

These are all defaults I can pick and adjust later without changing the architecture — not load-bearing.

## Implementation phases

1. `app/attribution/` package + `feature_attribution_results` table + migration `014_add_feature_attribution_results.py` + SHAP wrapper, with `backend/tests/test_attribution_service.py` (unit tests against a small local text-classification model) written alongside it, matching this repo's existing per-module test convention (e.g. `test_explainability_probe.py`, `test_robustness_nlp.py`) — not deferred to a later phase.
2. `/v1/attribution/*` router + schemas + error mapping, with `backend/tests/test_attribution_router.py`.
3. Frontend `FeatureAttributionPage` + `ModelDetailPage` entry point, with a matching `.test.tsx` per this repo's convention (e.g. `ModelDetailPage.test.tsx`).
4. (later) LIME as a second `method`, queuing if usage demands it, image/tabular modality.

---

## Resolved: evaluation_id linkage

`feature_attribution_results.evaluation_id` is a **nullable UUID column, no FK constraint** (§2's table already listed it this way). A report/evidence trail can reference "attribution was run for this evaluation's model" without it counting toward FRIES/O/S/D. The primary UI entry point stays `ModelDetailPage` (§6); an evaluation's report page may optionally surface a link to any attribution runs recorded against its `model_id`/`evaluation_id` in a later phase, but that surfacing is not required for v1.

Spec is now fully resolved — no remaining open questions. Ready for `writing-plans`.
