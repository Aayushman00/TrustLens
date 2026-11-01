# Evaluation Timeline Accuracy & Detail — Design

## Problem

The Evaluation Timeline (`frontend/src/components/EvaluationTimeline.tsx`,
rendered from `EvaluationDetailPage.tsx`) shows one row per recorded
`EvaluationEvent`, but most rows in a given run display the exact same
timestamp. Users read this as a rendering bug.

## Root cause (investigated, not assumed)

`EvaluationEvent.created_at` uses `server_default=func.now()` via the shared
`TimestampMixin` (`backend/app/db/base.py`). PostgreSQL's `now()` is frozen
for the whole transaction, and the deterministic evaluation pipeline
(`backend/app/tasks/evaluate_pipeline.py`) writes most lifecycle events for
one run inside a single transaction — so they legitimately share one
instant. This is **documented as intentional** in `EvaluationEvent`'s own
docstring (`backend/app/db/models.py:309-328`): ordering is by `id`, not
`created_at`, and the same convention applies to `ProbeResult` and
`HumanReview`. Changing this to per-row Python-side timestamps would
contradict that documented, codebase-wide convention and — worse — would
fabricate a false impression of elapsed real time between steps that, inside
one DB transaction, did not actually elapse. TrustLens's own stated ethos
(see comments in `DatasetIntakeForm.tsx`, `ColumnRoleMappingForm.tsx`) is to
never fabricate evidence; inventing sub-second timestamps would violate that.

**Decision: no backend or schema change.** The identical timestamps are
correct. The fix is entirely in how the frontend displays and labels them.

## Also discovered during investigation

- Live polling of events already exists: `EvaluationDetailPage.tsx`'s `tick()`
  effect calls `loadEvents()` every `POLL_MS` (2500ms) while
  `ACTIVE_STATUSES.includes(evaluation.status)`. There is no user-visible
  indication that this is happening — it just silently works.
- A "re-queue" (retry) event type already exists —
  `EVENT_EVALUATION_REQUEUED` (`backend/app/db/repositories/evaluation_event.py:25`),
  emitted by `EvaluationService.reconcile_enqueue_failure` with the same
  detail shape (`{enqueued, task_id}`) as `evaluation_created`. The frontend's
  `EVENT_LABELS` map and `detailSummary()` switch never handle it, so a
  requeued evaluation's timeline shows an unlabeled, un-summarized
  `evaluation requeued` row and no indication that everything after it is a
  second attempt.

## Design

All changes are additive to existing files; no new components, no backend
changes, no new API calls.

1. **Second-precision timestamp for this view only.** Add `fmtTimeSeconds`
   to `frontend/src/lib/format.ts` (does not touch the widely-used
   `fmtDateTime`). Distinguishes genuinely-different sub-minute timestamps
   (e.g. `evaluation_created` vs. a human review submitted moments later)
   that the existing minute-precision `fmtDateTime` was hiding.

2. **Gap-since-previous label.** A pure `gapLabel(prevIso, currIso)` helper
   in `EvaluationTimeline.tsx`: returns `"same instant"` for a <1s diff
   (the honest label for same-transaction events — not `"0s"`, which would
   read as broken), otherwise `"+Ns"` / `"+Nm"` / `"+Nm Ns"`. Rendered next
   to each row's timestamp after the first row.

3. **Attempt grouping.** A pure `attemptNumbers(events)` helper: attempt
   number starts at 1 and increments for every event *after* an
   `evaluation_requeued` event (the requeue event itself stays labeled with
   the attempt it closed out). When an evaluation has more than one attempt,
   render a divider row (`"Attempt N"`) at each boundary; single-attempt
   evaluations (the common case) render no dividers at all — no new visual
   noise for evaluations that were never retried.

4. **Requeue labeling.** Add `evaluation_requeued: "Evaluation re-queued"`
   to `EVENT_LABELS`. Extract the existing `evaluation_created` detail logic
   in `detailSummary()` into a shared `enqueueDetailSummary()` and reuse it
   for `evaluation_requeued` (identical detail shape, so identical summary
   logic — not new logic).

5. **Expandable per-row detail.** Each row with a non-empty `event.detail`
   gets a native `<details><summary>Details</summary>` disclosure showing
   the raw JSON (`JSON.stringify(event.detail, null, 2)`) in a `<pre>`. Rows
   with no detail render no disclosure control.

6. **Live badge.** `EvaluationTimeline` gains an optional `live?: boolean`
   prop. When true, a small pulsing-dot "Live — updating automatically"
   badge renders above the list (and above the empty/loading states too, so
   it's visible even before the first event lands). `EvaluationDetailPage`
   passes `live={isActive}` — it already computes `isActive` from
   `ACTIVE_STATUSES.includes(evaluation.status)` for the progress bar. No
   new polling logic; this only surfaces the polling that already exists.

## Explicitly out of scope

- Any backend/model/migration change.
- Per-probe start/completed events (the `EvaluationEvent` docstring already
  rejects this granularity by design — that detail lives in
  `ProbeResult`/`EvidenceDossier`).
- A general-purpose "retry" data model beyond the existing
  `evaluation_requeued` event (that event only covers the one existing
  recovery path — a stuck-PENDING reconcile — there is no other retry
  mechanism in the codebase to visualize).

## Testing

- `frontend/src/lib/format.test.ts` (node:test runner): new cases for
  `fmtTimeSeconds`.
- `frontend/src/components/EvaluationTimeline.test.tsx` (vitest): new cases
  for `gapLabel`, `attemptNumbers`, requeue label/summary rendering, attempt
  divider rendering (and its absence for single-attempt lists), detail
  disclosure presence/absence, and the live badge. All 4 existing tests in
  this file must keep passing unmodified.
