# Proposal: Probe Progress Events + SSE Stream (FUTURE — not implemented)

- **Status:** Proposed. Out of scope for the `feat/ui-redesign` iteration (scope decision C).
- **Date:** 2026-09-29
- **Consumer:** Live Evaluation Theatre (`docs/superpowers/specs/2026-09-29-trustlens-ui-redesign-design.md` §8)

## Why

Today the worker emits 10 lifecycle events (`backend/app/db/repositories/evaluation_event.py:24-33`)
and probe progress is `count(probe rows) / 5` (`evaluation_service.py:274`). The Theatre can only
say "awaiting" → "landed" per lane. Real per-lane running state, batch counters and throughput
require the backend to report them.

## Principles (carried from existing contract)

1. Events stay **audit evidence, never a source of truth** — scores/status still come from
   `evaluations`, `probe_results`, `final_scores` (see `frontend/src/api/types.ts:239-245`).
2. Append-only, ordered by `id`, small JSON `detail`.
3. Unknown event types must render generically in old frontends (already true — `event_type: string`).
4. Progress events are **rate-limited** so the events table does not bloat.

## Proposed event types

| event_type | When | `detail` |
|---|---|---|
| `probe_started` | worker begins a dimension's probe | `{ "dimension": "FAIRNESS", "probe_name": "fairness", "planned_units": 3000, "unit": "rows" \| "checks" \| "sections" }` |
| `probe_progress` | at most every 1 s **or** every 10 % of `planned_units`, whichever is rarer | `{ "dimension": "FAIRNESS", "done_units": 1200, "planned_units": 3000, "batch_index": 150 }` |
| `probe_completed` | probe row persisted | `{ "dimension": "FAIRNESS", "status": "EVALUATED", "evidence_ids": ["c8b8f84a-…"] }` |
| `probe_failed` | probe raised, before `evaluation_failed` | `{ "dimension": "…", "reason_code": "…" }` |

Deliberately **not** proposed: partial metric values mid-probe (e.g. running positive rates). A
partial fairness rate is not evidence and would invite over-reading; the Theatre shows metrics
only from the persisted row.

Emission points: `run_all_probes` in `backend/app/tasks/` already accepts
`on_probe_complete=on_progress` (`evaluate_pipeline.py:335`); add `on_probe_start` and a throttled
`on_probe_units(done, planned)` passed down to the local HF batching loop.

## Proposed endpoint

`GET /v1/evaluations/{id}/events/stream` — `text/event-stream`.

- On connect: replays events with `id > Last-Event-ID` (header) or `?after_id=`, then streams new ones.
- Each message: `id: <event.id>`, `event: <event_type>`, `data: <EvaluationEventRead JSON>`.
- Also emits `event: snapshot_hint` (no body) whenever `evaluations.status` changes, telling the
  client to refetch `GET /v1/evaluations/{id}` (keeps the snapshot authoritative; no duplicate
  state in the stream).
- Heartbeat comment `: ping` every 15 s; server closes after a terminal status + final event.
- Local-only single-user deployment: no auth change needed.

## Frontend impact (already prepared)

- New `SseSource implements TheatreSource`; falls back to `PollingSource` on stream error.
- `deriveTheatre` already contains the dormant branch: `probe_started` → lane `running`,
  `probe_progress` → batch counter + throughput (`done_units / Δt`), `probe_completed` → landing
  (still confirmed by the probe row).
- No component redesign: lanes already reserve the counter/throughput slot, today rendered as
  "not reported by backend".

## Open questions (for when this is picked up)

1. Can the local HF batching loop expose unit counts for all five probes, or only
   Fairness/Robustness (inference probes)? Documentation probes may emit start/complete only.
2. Retention: prune `probe_progress` rows after finalisation, keeping start/complete?
3. Does Celery worker → API process need Redis pub/sub for SSE fan-out, or is DB polling
   inside the SSE handler (e.g. 250 ms) acceptable for single-user local?
