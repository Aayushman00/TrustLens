# LLM-Assisted O/S/D Scoring for Integrity, Explainability, Safety

## Context

TrustLens currently ships two O/S/D scoring engines, selected per-evaluation via `probe_config["assessment_engine"]` and resolved by `resolve_assessment_engine()` (`backend/app/osd/deterministic.py:87-97`):

- **`deterministic`** (default) — `DeterministicOSDMapper` abstains on every O/S/D; a human fills in all values during review.
- **`legacy_heuristic`** (opt-in) — `HeuristicOSDAgent` (`backend/app/osd/agent.py:191-269`) proposes O/S/D for all five FRIES dimensions from fixed ratio formulas over persisted probe metrics (`scale(x) = clamp(round(10x), 1, 9)`).

For FAIRNESS and ROBUSTNESS, the heuristic's inputs are clean quantitative metrics (demographic parity gap, clean/robust accuracy) and the formulas are adequate. For INTEGRITY, EXPLAINABILITY, and SAFETY, the heuristic collapses to counting things (`pass_rate` over metadata checks, `coverage_ratio` over model-card sections) — it detects *presence* of a section, not *quality* or *adequacy* of what's written there. This is the gap LLM-assisted scoring closes: for these three dimensions specifically, judgment over the underlying text (model-card `card_text`, safety disclosures, integrity checks) can do better than a coverage ratio.

This work is scoped to the scoring methodology only. It is unrelated to, and does not block, a separate assignment task of running two subject models (one "trustworthy", one "less trustworthy") through the existing pipeline unchanged for comparison — that uses whichever engine is already selected and needs no new code.

## Goals

- Add a third assessment engine, `llm_v1`, that improves O/S/D proposals for INTEGRITY, EXPLAINABILITY, and SAFETY using an LLM's judgment over the same evidence the heuristic already has access to.
- Leave FAIRNESS and ROBUSTNESS scoring untouched (still heuristic formulas).
- Never regress to a worse experience than today's heuristic: any LLM failure transparently falls back to the heuristic's number for that evaluation, with the fallback visibly tagged.
- Fit the existing engine-selection, review, and merge machinery with minimal new surface area.

## Non-Goals

- Not replacing FAIRNESS/ROBUSTNESS heuristic formulas.
- Not changing the `deterministic` engine's default or abstain semantics.
- Not building a general-purpose "LLM judge" framework — this is scoped to three FRIES dimensions.
- Not addressing the separate, already-known O/S/D frontend mislabeling bug (Operations/Safeguards/Disclosures vs Occurrence/Severity/Detection) — out of scope here.

## Design

### New engine: `HybridOSDAgent`

A new class in `backend/app/osd/hybrid.py` implementing the existing `OSDAgent` protocol (`propose(ctx: AgentContext) -> AgentResult`, `backend/app/osd/base.py:85-86`):

1. Calls `HeuristicOSDAgent().propose(ctx)` to get a full baseline `AgentResult` covering all five dimensions.
2. Builds one batched prompt covering INTEGRITY, EXPLAINABILITY, and SAFETY evidence (see "LLM call" below) and calls Gemini once.
3. On a well-formed response: for each of the three dimensions, overwrites that aspect's `O`/`S`/`D` with the LLM's values, sets `O_source`/`S_source`/`D_source` to `"llm_v1"`, and replaces `rationale` with the LLM's rationale for that dimension. FAIRNESS/ROBUSTNESS aspects from the heuristic baseline pass through unmodified.
4. On any failure (API error, timeout, malformed/unparseable JSON, schema validation failure): all three aspects keep the heuristic's original values unmodified, but `O_source`/`S_source`/`D_source` are set to `"heuristic_fallback"` so the review UI and any report can show that the LLM did not produce a value for this run.
5. Returns one `AgentResult` with `assessment_engine="llm_v1"` and `methodology_status="LEGACY_HEURISTIC_OSD_V1"` (unchanged from the heuristic engine's status — see "Review/merge compatibility" below for why).

### Engine selection wiring

Three Literal types and one call site need a new `"llm_v1"` value:

- `ProbeConfigV1.assessment_engine: Literal["deterministic", "legacy_heuristic", "llm_v1"] | None` (`backend/app/schemas/probe_config.py:33`)
- `CreateEvaluationV2Request.assessment_engine: Literal["deterministic", "legacy_heuristic", "llm_v1"] | None` (`backend/app/schemas/evaluation_draft.py:23`)
- `resolve_assessment_engine()` (`backend/app/osd/deterministic.py:87-97`) gains a branch returning `"llm_v1"` when `probe_config["assessment_engine"] == "llm_v1"`.
- `evaluate_pipeline.py:144-145` gains a third branch: `mapper = HybridOSDAgent() if engine == "llm_v1" else (HeuristicOSDAgent() if engine == "legacy_heuristic" else DeterministicOSDMapper())`.
- Frontend: `CreateEvaluationDraftPage.tsx`'s existing engine toggle gets a third option, `"llm_v1"`, labeled to make clear it's LLM-assisted for integrity/explainability/safety only (not a general "better" mode).

### LLM call

- Provider: Google Gemini (free tier), via the `google-genai` SDK. API key read from `GEMINI_API_KEY` environment variable — never hardcoded, never committed.
- One batched call per evaluation run under this engine, covering all three dimensions in a single prompt/response (trades independent-failure isolation for lower free-tier quota usage — an explicit tradeoff; if any one dimension's JSON is bad, all three fall back together per the failure rule above).
- Input per dimension: the corresponding `ProbeSnapshot.metric_values` and `evidence_refs` already computed by the existing probes (e.g. explainability's `checks`, `flags`, `risks_triggered`, `coverage_ratio`), plus the raw `ctx.model_metadata["card_text"]` shared across dimensions. No changes needed to `AgentContext`/`ProbeSnapshot` — this data already flows into `AgentContext` today; the heuristic agent simply doesn't read `card_text`.
- Output: a single JSON object, one entry per dimension, each with `O`/`S`/`D` (ints, 1-9, same clamp convention as the heuristic) and `rationale` (string). Validated against a Pydantic response model before use; validation failure is treated as an LLM failure (triggers fallback).

### Review/merge compatibility

`backend/app/osd/review.py:93-95` dispatches merge logic on `_is_deterministic(agent_suggestion)`, which checks `methodology_status`. The deterministic path (`_merge_deterministic`) assumes the agent never proposes O/S/D (always `None`) and requires the human to supply everything; the legacy-heuristic path (`_merge_legacy_heuristic`) expects the agent to have proposed a complete triple per aspect, which the reviewer may accept or override.

Because `HybridOSDAgent` always proposes complete triples (from the heuristic baseline, then optionally overwritten by the LLM), it must route through the legacy-heuristic merge path. Keeping `methodology_status="LEGACY_HEURISTIC_OSD_V1"` on the `llm_v1` engine's output achieves this with no change to `review.py`. The `O_source`/`S_source`/`D_source` per-aspect fields (already present on `AspectOSD`, `backend/app/osd/base.py:70-72`) are what let a reviewer or report distinguish an LLM-proposed value from a heuristic or fallback one — no new schema needed there either.

### Failure handling summary

| Scenario | O/S/D shown | Source tag |
|---|---|---|
| Gemini call succeeds, valid JSON | LLM's values | `llm_v1` |
| Gemini call fails/times out/invalid JSON | Heuristic's values (unchanged) | `heuristic_fallback` |
| Dimension has no probe evidence at all | `None` (abstain, same as heuristic today) | n/a |

## Testing

- Unit tests for `HybridOSDAgent.propose()`: successful LLM response overwrites the three aspects correctly and leaves FAIRNESS/ROBUSTNESS untouched; malformed/missing JSON falls back correctly per-field with the right source tags; no-probe-evidence dimensions still abstain.
- Mock the Gemini client in tests — no real network calls in the test suite.
- Extend `resolve_assessment_engine()` tests (alongside existing `test_phase6_honesty.py` cases) to cover `"llm_v1"` resolving correctly and unknown/omitted values still defaulting to `"deterministic"`.
- Extend the existing `/v1/evaluations-v2` engine-toggle test (from the prior `assessment-engine-toggle-prompt.md` handoff) to also accept `"llm_v1"`.

## Open items for implementation time (not blocking this spec)

- Exact Gemini model name/version to pin (e.g. a `gemini-*-flash` variant) — pick the cheapest/free-tier model that reliably returns valid structured JSON; verify empirically once implementing.
- Exact prompt wording/few-shot examples for the batched call — implementation detail, not an architectural decision.
