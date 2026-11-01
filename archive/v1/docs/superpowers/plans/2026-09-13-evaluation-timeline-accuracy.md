# Evaluation Timeline Accuracy & Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Evaluation Timeline read as accurate and complete: second-precision timestamps, gap-since-previous labels, retry/attempt grouping, expandable per-event detail, and a live-updating indicator — without touching the backend or the intentional transaction-time data model.

**Architecture:** Entirely frontend. Two files change: `frontend/src/lib/format.ts` (one new formatter) and `frontend/src/components/EvaluationTimeline.tsx` (new pure helpers + rendering). `frontend/src/pages/EvaluationDetailPage.tsx` gets a one-line prop addition. No backend, no schema, no new API calls — the events endpoint and its live-polling loop already exist.

**Tech Stack:** React + TypeScript, Vitest (component tests), Node's built-in `node:test`/`node:assert` (for `format.test.ts` specifically — this repo runs that one file via `node --test`, not Vitest; see `package.json`'s `test` script).

**Spec:** `docs/superpowers/specs/2026-09-13-evaluation-timeline-accuracy-design.md`

## Global Constraints

- No backend, database, or migration changes of any kind.
- Do not change `fmtDateTime`'s existing signature or output — it's used by 8 other files. Add a new function instead.
- Never fabricate a timestamp, duration, or event. A `<1s` gap must render as `"same instant"`, never `"0s"` (which would look like the exact bug being fixed) and never a rounded-up fake value.
- Preserve all 4 existing tests in `EvaluationTimeline.test.tsx` unmodified and passing.
- Single-attempt evaluations (no `evaluation_requeued` event present) must render zero attempt-divider rows — the divider only earns its place when there's more than one attempt.
- Follow existing code style in the touched files: named CSS classes in `index.css` rather than inline `style={{}}` objects for anything reused across rows (the file already mixes both; prefer classes for this pass since these are the "coherent component system" rows).

---

### Task 1: `fmtTimeSeconds` formatter

**Files:**
- Modify: `frontend/src/lib/format.ts`
- Test: `frontend/src/lib/format.test.ts`

**Interfaces:**
- Produces: `fmtTimeSeconds(iso: string | null | undefined): string` — same contract as `fmtDateTime` (returns `"—"` for null/undefined, returns the raw string back if unparseable) but with `second: "2-digit"` added to the `toLocaleString` options.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/lib/format.test.ts`:

```ts
import { fmtTimeSeconds } from "./format.ts";

test("fmtTimeSeconds returns an em dash for null/undefined", () => {
  assert.equal(fmtTimeSeconds(null), "—");
  assert.equal(fmtTimeSeconds(undefined), "—");
});

test("fmtTimeSeconds returns the raw string for an unparseable date", () => {
  assert.equal(fmtTimeSeconds("not-a-date"), "not-a-date");
});

test("fmtTimeSeconds includes seconds in the rendered output", () => {
  const result = fmtTimeSeconds("2026-03-15T10:30:45Z");
  // Locale-independent: assert the seconds component is present as two
  // digits somewhere in the string, without pinning an exact locale format.
  assert.match(result, /\d{2}:\d{2}:\d{2}/);
});
```

(Add the `fmtTimeSeconds` import to the existing `import { parseOsdInput } from "./format.ts";` line instead of a second import statement — combine them: `import { fmtTimeSeconds, parseOsdInput } from "./format.ts";`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && node --experimental-strip-types --test src/lib/format.test.ts`
Expected: FAIL — `fmtTimeSeconds` is not exported from `./format.ts`.

- [ ] **Step 3: Implement `fmtTimeSeconds`**

In `frontend/src/lib/format.ts`, add after `fmtDateTime`:

```ts
/** Like fmtDateTime, but with second precision -- for views (the evaluation
 * timeline) where sub-minute gaps between events are meaningful and must be
 * visible, not rounded away. */
export function fmtTimeSeconds(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && node --experimental-strip-types --test src/lib/format.test.ts`
Expected: PASS, all tests including the 5 pre-existing `parseOsdInput` ones.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/format.ts frontend/src/lib/format.test.ts
git commit -m "feat: add second-precision timestamp formatter for the evaluation timeline"
```

---

### Task 2: `gapLabel` and `attemptNumbers` helpers

**Files:**
- Modify: `frontend/src/components/EvaluationTimeline.tsx`
- Test: `frontend/src/components/EvaluationTimeline.test.tsx`

**Interfaces:**
- Consumes: `EvaluationEventRead` from `frontend/src/api/types.ts` (already imported in this file: `{ id, evaluation_id, event_type, created_at, detail }`).
- Produces:
  - `export function gapLabel(prevIso: string, currIso: string): string | null` — `null` if either date fails to parse; `"same instant"` if the difference is under 1000ms; otherwise `"+Ns"` for under 60s, `"+Nm"` for an exact multiple of 60s, `"+Nm Ss"` otherwise (all durations rounded to the nearest second).
  - `export function attemptNumbers(events: EvaluationEventRead[]): number[]` — one entry per event, same order/length as `events`. Starts at `1`; increments for every event *after* one whose `event_type === "evaluation_requeued"` (the requeue event itself keeps the pre-increment number).

- [ ] **Step 1: Write the failing tests**

Add near the top of `frontend/src/components/EvaluationTimeline.test.tsx` (new imports) and new `describe` blocks (keep the existing `describe("EvaluationTimeline", ...)` block untouched):

```tsx
import EvaluationTimeline, { attemptNumbers, gapLabel } from "./EvaluationTimeline";
```

(replace the existing `import EvaluationTimeline from "./EvaluationTimeline";` line with the above.)

```tsx
describe("gapLabel", () => {
  it("returns 'same instant' for sub-second differences", () => {
    expect(gapLabel("2026-01-01T00:00:00.000Z", "2026-01-01T00:00:00.400Z")).toBe("same instant");
  });

  it("returns '+Ns' for a sub-minute gap", () => {
    expect(gapLabel("2026-01-01T00:00:00Z", "2026-01-01T00:00:42Z")).toBe("+42s");
  });

  it("returns '+Nm' for an exact-minute gap", () => {
    expect(gapLabel("2026-01-01T00:00:00Z", "2026-01-01T00:03:00Z")).toBe("+3m");
  });

  it("returns '+Nm Ss' for a gap with both minutes and seconds", () => {
    expect(gapLabel("2026-01-01T00:00:00Z", "2026-01-01T00:03:05Z")).toBe("+3m 5s");
  });

  it("returns null for an unparseable date", () => {
    expect(gapLabel("not-a-date", "2026-01-01T00:00:00Z")).toBeNull();
  });
});

describe("attemptNumbers", () => {
  it("assigns attempt 1 to every event when there is no requeue", () => {
    const events = [
      event({ id: 1, event_type: "evaluation_created" }),
      event({ id: 2, event_type: "evaluation_started" }),
      event({ id: 3, event_type: "evaluation_finalized" }),
    ];
    expect(attemptNumbers(events)).toEqual([1, 1, 1]);
  });

  it("increments after a requeue, keeping the requeue event itself on the old attempt", () => {
    const events = [
      event({ id: 1, event_type: "evaluation_created" }),
      event({ id: 2, event_type: "evaluation_requeued" }),
      event({ id: 3, event_type: "evaluation_started" }),
      event({ id: 4, event_type: "evaluation_requeued" }),
      event({ id: 5, event_type: "evaluation_finalized" }),
    ];
    expect(attemptNumbers(events)).toEqual([1, 1, 2, 2, 3]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/EvaluationTimeline.test.tsx`
Expected: FAIL — `gapLabel` and `attemptNumbers` are not exported from `./EvaluationTimeline`.

- [ ] **Step 3: Implement the helpers**

In `frontend/src/components/EvaluationTimeline.tsx`, add after the `EVENT_LABELS` block (before `labelFor`):

```ts
export function gapLabel(prevIso: string, currIso: string): string | null {
  const prev = new Date(prevIso).getTime();
  const curr = new Date(currIso).getTime();
  if (Number.isNaN(prev) || Number.isNaN(curr)) return null;
  const diffMs = curr - prev;
  if (diffMs < 1000) return "same instant";
  const totalSeconds = Math.round(diffMs / 1000);
  if (totalSeconds < 60) return `+${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds === 0 ? `+${minutes}m` : `+${minutes}m ${seconds}s`;
}

export function attemptNumbers(events: EvaluationEventRead[]): number[] {
  const result: number[] = [];
  let attempt = 1;
  for (const evt of events) {
    result.push(attempt);
    if (evt.event_type === "evaluation_requeued") attempt += 1;
  }
  return result;
}
```

(`EvaluationEventRead` is already imported at the top of this file via `import type { EvaluationEventRead } from "../api/types";`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/EvaluationTimeline.test.tsx`
Expected: PASS, all tests including the 4 pre-existing ones.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/EvaluationTimeline.tsx frontend/src/components/EvaluationTimeline.test.tsx
git commit -m "feat: add gap-since-previous and attempt-numbering helpers to the evaluation timeline"
```

---

### Task 3: Requeue labeling and shared enqueue-detail summary

**Files:**
- Modify: `frontend/src/components/EvaluationTimeline.tsx`
- Test: `frontend/src/components/EvaluationTimeline.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `EVENT_LABELS["evaluation_requeued"]` now set; `detailSummary("evaluation_requeued", detail)` behaves identically to `detailSummary("evaluation_created", detail)`.

- [ ] **Step 1: Write the failing test**

Add to the existing `describe("EvaluationTimeline", ...)` block in `frontend/src/components/EvaluationTimeline.test.tsx`:

```tsx
it("labels a re-queued evaluation and summarizes its enqueue detail like a fresh create", () => {
  const events = [
    event({
      id: 1,
      event_type: "evaluation_requeued",
      detail: { enqueued: true, task_id: "abcdef0123456789" },
    }),
  ];
  render(<EvaluationTimeline events={events} />);
  const item = screen.getByRole("listitem");
  expect(item).toHaveTextContent("Evaluation re-queued");
  expect(item).toHaveTextContent("Task abcdef012345");
});

it("shows the stuck-PENDING warning on a requeue whose enqueue also failed", () => {
  const events = [
    event({ id: 1, event_type: "evaluation_requeued", detail: { enqueued: false } }),
  ];
  render(<EvaluationTimeline events={events} />);
  expect(screen.getByText(/may be stuck at PENDING/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/EvaluationTimeline.test.tsx`
Expected: FAIL — renders `"evaluation requeued"` (generic fallback) instead of `"Evaluation re-queued"`, and no detail summary.

- [ ] **Step 3: Implement**

In `frontend/src/components/EvaluationTimeline.tsx`:

Update `EVENT_LABELS`:

```ts
const EVENT_LABELS: Record<string, string> = {
  evaluation_created: "Evaluation created",
  evaluation_requeued: "Evaluation re-queued",
  evaluation_started: "Evaluation started",
  probes_completed: "Probes completed",
  agent_completed: "O/S/D representation proposed",
  evaluation_failed: "Evaluation failed",
  awaiting_review: "Awaiting human review",
  human_review_submitted: "Human review submitted",
  evaluation_finalized: "Evaluation finalized",
  report_generated: "Report generated",
};
```

Extract and reuse the enqueue-detail logic in `detailSummary`:

```ts
function enqueueDetailSummary(detail: Record<string, unknown>): string | null {
  const enqueued = detail.enqueued;
  if (enqueued === false) {
    return "Not enqueued — the evaluation may be stuck at PENDING (no worker task was sent).";
  }
  return typeof detail.task_id === "string" ? `Task ${String(detail.task_id).slice(0, 12)}…` : null;
}

function detailSummary(eventType: string, detail: Record<string, unknown> | null): string | null {
  if (!detail) return null;
  switch (eventType) {
    case "evaluation_created":
    case "evaluation_requeued":
      return enqueueDetailSummary(detail);
    case "probes_completed":
      return typeof detail.probe_count === "number" ? `${detail.probe_count} probe(s) ran` : null;
    case "evaluation_failed":
      return typeof detail.reason_code === "string" ? `Reason: ${String(detail.reason_code).replaceAll("_", " ")}` : null;
    case "human_review_submitted": {
      const parts: string[] = [];
      if (detail.accept_all === true) parts.push("accepted as-is");
      if (detail.accept_all === false) parts.push("edited");
      if (detail.human_changed === true) parts.push("values changed");
      return parts.length ? parts.join(" · ") : null;
    }
    case "evaluation_finalized": {
      const withheld = detail.scoring_withheld;
      if (withheld === true) return "FRIES withheld — see evaluation for why.";
      if (withheld === false) return "FRIES scored — see the evaluation's own FRIES card for the number.";
      return null;
    }
    case "report_generated":
      return typeof detail.version === "number" ? `Version ${detail.version}` : null;
    default:
      return null;
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/EvaluationTimeline.test.tsx`
Expected: PASS, all tests including the 4 original ones and Task 2's new ones.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/EvaluationTimeline.tsx frontend/src/components/EvaluationTimeline.test.tsx
git commit -m "feat: label and summarize the evaluation_requeued event in the timeline"
```

---

### Task 4: Row rendering — seconds, gaps, attempt dividers, expandable detail, live badge

**Files:**
- Modify: `frontend/src/components/EvaluationTimeline.tsx`
- Modify: `frontend/src/pages/EvaluationDetailPage.tsx:409`
- Modify: `frontend/src/index.css`
- Test: `frontend/src/components/EvaluationTimeline.test.tsx`

**Interfaces:**
- Consumes: `fmtTimeSeconds` from `../lib/format` (Task 1), `gapLabel`/`attemptNumbers` (Task 2).
- Produces: `EvaluationTimeline`'s prop type becomes `{ events: EvaluationEventRead[] | null; live?: boolean }` (default `false`). `EvaluationDetailPage` passes `live={isActive}` at its existing `isActive` variable (already computed at `EvaluationDetailPage.tsx:96`).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/components/EvaluationTimeline.test.tsx`'s `describe("EvaluationTimeline", ...)` block:

```tsx
it("shows a gap label between consecutive events with different timestamps", () => {
  const events = [
    event({ id: 1, created_at: "2026-01-01T00:00:00Z" }),
    event({ id: 2, event_type: "evaluation_started", created_at: "2026-01-01T00:00:05Z" }),
  ];
  render(<EvaluationTimeline events={events} />);
  const items = screen.getAllByRole("listitem");
  expect(items[1]).toHaveTextContent("+5s");
});

it("shows 'same instant' rather than a fabricated duration for identical timestamps", () => {
  const events = [
    event({ id: 1, created_at: "2026-01-01T00:00:00Z" }),
    event({ id: 2, event_type: "evaluation_started", created_at: "2026-01-01T00:00:00Z" }),
  ];
  render(<EvaluationTimeline events={events} />);
  const items = screen.getAllByRole("listitem");
  expect(items[1]).toHaveTextContent("same instant");
});

it("renders no attempt dividers for a single-attempt evaluation", () => {
  const events = [
    event({ id: 1, event_type: "evaluation_created" }),
    event({ id: 2, event_type: "evaluation_finalized" }),
  ];
  render(<EvaluationTimeline events={events} />);
  expect(screen.queryByText(/Attempt \d/)).not.toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

it("renders an attempt divider at each requeue boundary", () => {
  const events = [
    event({ id: 1, event_type: "evaluation_created" }),
    event({ id: 2, event_type: "evaluation_requeued", detail: { enqueued: true } }),
    event({ id: 3, event_type: "evaluation_started" }),
  ];
  render(<EvaluationTimeline events={events} />);
  expect(screen.getByText("Attempt 2")).toBeInTheDocument();
});

it("renders an expandable detail disclosure only when the event has detail", () => {
  const events = [
    event({ id: 1, event_type: "probes_completed", detail: { probe_count: 3 } }),
    event({ id: 2, event_type: "evaluation_started", detail: null }),
  ];
  render(<EvaluationTimeline events={events} />);
  const disclosures = screen.getAllByText("Details");
  expect(disclosures).toHaveLength(1);
});

it("shows a live badge only when live is true, even before any events arrive", () => {
  const { rerender } = render(<EvaluationTimeline events={null} live />);
  expect(screen.getByText(/Live/i)).toBeInTheDocument();

  rerender(<EvaluationTimeline events={null} />);
  expect(screen.queryByText(/Live/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/EvaluationTimeline.test.tsx`
Expected: FAIL — none of gap text, attempt dividers, detail disclosures, or the live badge exist yet.

- [ ] **Step 3: Implement the rendering**

First, replace this file's existing import line:

```tsx
import { fmtDateTime } from "../lib/format";
```

with:

```tsx
import { fmtTimeSeconds } from "../lib/format";
```

(`fmtDateTime` is no longer used in this file after this task — the only caller here becomes `fmtTimeSeconds`.)

Then replace the default export (keep everything above it — `EVENT_LABELS`, `labelFor`, `enqueueDetailSummary`, `detailSummary`, `gapLabel`, `attemptNumbers` — unchanged) with:

```tsx
export default function EvaluationTimeline({
  events,
  live = false,
}: {
  events: EvaluationEventRead[] | null;
  live?: boolean;
}) {
  const liveBadge = live ? (
    <div className="live-badge">
      <span className="live-badge-dot" />
      Live — updating automatically
    </div>
  ) : null;

  if (events == null) {
    return (
      <>
        {liveBadge}
        <p className="muted">Loading timeline…</p>
      </>
    );
  }
  if (events.length === 0) {
    return (
      <>
        {liveBadge}
        <p className="empty">
          No recorded timeline events for this evaluation — either it predates event
          tracking, or it has not progressed yet.
        </p>
      </>
    );
  }

  const attempts = attemptNumbers(events);
  const showAttempts = attempts[attempts.length - 1] > 1;

  return (
    <>
      {liveBadge}
      <ol className="timeline-list" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {events.map((event, idx) => {
          const summary = detailSummary(event.event_type, event.detail);
          const gap = idx > 0 ? gapLabel(events[idx - 1].created_at, event.created_at) : null;
          const hasDetail = event.detail != null && Object.keys(event.detail).length > 0;
          const rows = [];

          if (showAttempts && (idx === 0 || attempts[idx] !== attempts[idx - 1])) {
            rows.push(
              <li key={`attempt-${attempts[idx]}`} className="timeline-attempt-divider">
                Attempt {attempts[idx]}
              </li>,
            );
          }

          rows.push(
            <li key={event.id} className="timeline-row">
              <span className="mono muted timeline-row-time">
                {fmtTimeSeconds(event.created_at)}
                {gap ? <span className="timeline-row-gap"> · {gap}</span> : null}
              </span>
              <span className="timeline-row-body">
                <strong>{labelFor(event.event_type)}</strong>
                {summary ? <span className="muted"> — {summary}</span> : null}
                {hasDetail ? (
                  <details className="timeline-row-details">
                    <summary>Details</summary>
                    <pre className="mono">{JSON.stringify(event.detail, null, 2)}</pre>
                  </details>
                ) : null}
              </span>
            </li>,
          );

          return rows;
        })}
      </ol>
    </>
  );
}
```

Remove the old inline `<li style={{...}}>` block entirely (it's fully replaced above).

In `frontend/src/pages/EvaluationDetailPage.tsx`, change line 409 from:

```tsx
        <EvaluationTimeline events={events} />
```

to:

```tsx
        <EvaluationTimeline events={events} live={isActive} />
```

(`isActive` is already computed at `EvaluationDetailPage.tsx:96` — no other change needed in this file.)

In `frontend/src/index.css`, append after the existing dark-mode block (end of file):

```css
/* ---- evaluation timeline ---- */

.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--accent-strong);
  background: var(--accent-soft);
  border-radius: var(--radius-pill);
  padding: 0.2rem 0.6rem;
  margin-bottom: 0.75rem;
}

.live-badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: live-pulse 1.4s ease-in-out infinite;
}

@keyframes live-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

.timeline-attempt-divider {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0 0.2rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}

.timeline-attempt-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border);
}

.timeline-row {
  display: flex;
  gap: 0.75rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--border);
}

.timeline-row:last-child {
  border-bottom: none;
}

.timeline-row-time {
  font-size: 0.78rem;
  min-width: 11.5rem;
  flex: none;
}

.timeline-row-gap {
  color: var(--muted);
}

.timeline-row-body {
  flex: 1;
  min-width: 0;
}

.timeline-row-details {
  margin-top: 0.35rem;
}

.timeline-row-details summary {
  cursor: pointer;
  font-size: 0.78rem;
  color: var(--ink-accent);
}

.timeline-row-details pre {
  margin: 0.4rem 0 0;
  padding: 0.6rem 0.7rem;
  background: var(--surface-sunken);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  overflow-x: auto;
}

@media (max-width: 560px) {
  .timeline-row {
    flex-direction: column;
    gap: 0.2rem;
  }
  .timeline-row-time {
    min-width: 0;
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/EvaluationTimeline.test.tsx`
Expected: PASS — all original 4 tests, Task 2's helper tests, Task 3's requeue tests, and this task's 6 new tests.

- [ ] **Step 5: Type-check and run the full frontend suite**

Run: `cd frontend && npx tsc --noEmit -p . && node --experimental-strip-types --test src/lib/format.test.ts && npx vitest run`
Expected: tsc reports no errors; both test runners pass with 0 failures.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/EvaluationTimeline.tsx frontend/src/components/EvaluationTimeline.test.tsx frontend/src/pages/EvaluationDetailPage.tsx frontend/src/index.css
git commit -m "feat: render gaps, attempt dividers, expandable detail, and a live badge in the evaluation timeline"
```

---

## Manual verification (after Task 4)

No automated browser test is in scope for this plan. Before considering the feature done, start the app against a real/local backend (not a stale build — verify with `curl http://localhost:<port>/src/components/EvaluationTimeline.tsx | grep live-badge` before trusting what's rendered, per prior session lesson) and check on an actual evaluation's detail page:

1. A running (non-terminal-status) evaluation shows the live badge; a finished one does not.
2. Rows within the same pipeline transaction show "same instant", not a fake duration.
3. Reconciling a stuck-PENDING evaluation (or any evaluation with a real `evaluation_requeued` event, if one exists in seed data) shows "Evaluation re-queued" with a working detail summary and an "Attempt 2" divider before the next row.
4. A row with detail (e.g. `probes_completed`) has a working "Details" disclosure; a row without detail has none.
5. Responsive: narrow the window below 560px and confirm timeline rows stack without overlap.
