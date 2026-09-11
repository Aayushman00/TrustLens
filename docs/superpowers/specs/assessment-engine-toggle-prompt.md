# Handoff prompt: assessment-engine toggle on evaluation creation

Add an opt-in UI toggle letting a user pick `legacy_heuristic` scoring instead of the default `deterministic` engine when creating an evaluation, WITHOUT changing the default (deterministic stays default; ~6 existing tests assert this and must keep passing).

## Context you need

The creation UI (`frontend/src/pages/CreateEvaluationDraftPage.tsx`) posts to `POST /v1/evaluations-v2`, backed by `CreateEvaluationV2Request` in `backend/app/schemas/evaluation_draft.py:17-22`:

```python
class CreateEvaluationV2Request(BaseModel):
    draft_id: uuid.UUID
    evaluation_mode: EvaluationMode
```

This schema has **no `probe_config`/engine field at all** — that's the gap to close. The engine is selected purely by `resolve_assessment_engine()` in `backend/app/osd/deterministic.py:87-97`:

```python
def resolve_assessment_engine(probe_config: dict[str, Any] | None) -> str:
    cfg = probe_config or {}
    engine = cfg.get("assessment_engine")
    if engine == "legacy_heuristic":
        return "legacy_heuristic"
    return "deterministic"
```

It reads only the top-level `probe_config["assessment_engine"]` key. It deliberately ignores `extra.assessment_engine` (a historical alias) — see `backend/tests/test_phase6_honesty.py:165-183` (`test_extra_heuristic_ignored_stays_deterministic`), which must keep passing unchanged.

The validated shape for `probe_config` is `ProbeConfigV1` in `backend/app/schemas/probe_config.py:10-18`:

```python
class ProbeConfigV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    assessment_engine: Literal["deterministic", "legacy_heuristic"] | None = None
    datasets: dict[str, str] = Field(default_factory=dict)
    attack_budget: float | None = None
    slice_definitions: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
```

A working, tested opt-in already exists on the **older** bare `POST /v1/evaluations` endpoint (`EvaluationCreate` schema, which already has `probe_config: dict`) — see `backend/tests/test_phase6_honesty.py:186-207` (`test_legacy_heuristic_has_no_role_gate`), using `LEGACY_HEURISTIC_PROBE_CONFIG` from `backend/tests/conftest.py:71-74`:

```python
LEGACY_HEURISTIC_PROBE_CONFIG = {
    "schema_version": "v1",
    "assessment_engine": "legacy_heuristic",
}
```

Your job is to bring that same opt-in to the `/v1/evaluations-v2` draft-based path the UI actually uses, plus surface it as a toggle in the UI.

Both engines already implement the same `OSDAgent` protocol (`backend/app/osd/base.py`, `AgentContext -> AgentResult`) — `HeuristicOSDAgent` (`backend/app/osd/agent.py:194`) and `DeterministicOSDMapper` (`backend/app/osd/deterministic.py:140`). You are NOT changing that dispatch or the default resolution logic — only adding a way to pass `assessment_engine: "legacy_heuristic"` through the v2 creation path.

## Required changes

1. **Backend schema**: add `assessment_engine: Literal["deterministic", "legacy_heuristic"] | None = None` to `CreateEvaluationV2Request` (`backend/app/schemas/evaluation_draft.py`).
2. **Backend service**: find where `/v1/evaluations-v2` builds the `Evaluation`/`probe_config` from the draft + `CreateEvaluationV2Request` (search callers of `CreateEvaluationV2Request` and the router handling `/v1/evaluations-v2`), and thread `assessment_engine` into the constructed `probe_config` dict (matching the `ProbeConfigV1` shape: `{"schema_version": "v1", "assessment_engine": <value>}`) when provided. Leave behavior unchanged when the field is omitted/`None` — must still default to `"deterministic"` via existing `resolve_assessment_engine`.
3. **Backend test**: add a test in the style of `test_phase6_honesty.py:186-207`, but hitting `/v1/evaluations-v2` (draft-based flow) with `assessment_engine: "legacy_heuristic"` in the request body, asserting the resulting evaluation's `probe_config["assessment_engine"] == "legacy_heuristic"`. Also add/confirm a test that omitting the field still resolves to `"deterministic"` on this path.
4. **Frontend state**: in `CreateEvaluationDraftPage.tsx`, add a top-level `useState<"deterministic" | "legacy_heuristic">("deterministic")` (evaluation-wide, NOT per-dimension — do not fold this into the existing `DimensionState`/`toggleDimension` pattern at line 156, which is per-dimension FAIRNESS/ROBUSTNESS config and a different concern).
5. **Frontend UI**: add a toggle/checkbox near the evaluation-mode/review step, defaulting off (`deterministic`), labeled clearly (e.g. "Use legacy heuristic scoring" with a short explanatory note that this is opt-in, non-default).
6. **Frontend request**: include `assessment_engine: assessmentEngine` in the `/v1/evaluations-v2` POST body built at `CreateEvaluationDraftPage.tsx:221-224` (currently `{ draft_id: draft.id, evaluation_mode: "AI_ASSISTED" }`) only when it differs from the default, or always — match whatever the backend schema treats as equivalent to omission (`None`/`"deterministic"`).

## Constraints

- Do NOT change `resolve_assessment_engine`'s default or its `extra`-ignoring behavior.
- Do NOT touch the older `/v1/evaluations` (`EvaluationCreate`) path or its existing tests (`test_phase6_honesty.py`) — those stay as-is and must keep passing.
- Follow TDD: write the failing backend test first, then implement, then add the frontend piece.
- Keep the toggle default OFF so no existing default-path test regresses.

Report back with exact file paths and line numbers changed, and the test run output confirming both the new test and the full existing `test_phase6_honesty.py` suite pass.
