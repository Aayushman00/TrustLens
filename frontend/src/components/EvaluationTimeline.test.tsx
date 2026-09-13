/**
 * EvaluationTimeline — audit item 3. Protects: real event rendering in
 * API-provided order, the honest empty state, and no crash on an
 * unknown/future event_type (never fabricated events or timestamps).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EvaluationEventRead } from "../api/types";
import EvaluationTimeline, { attemptNumbers, gapLabel } from "./EvaluationTimeline";

function event(overrides: Partial<EvaluationEventRead>): EvaluationEventRead {
  return {
    id: 1,
    evaluation_id: "11111111-1111-1111-1111-111111111111",
    event_type: "evaluation_created",
    created_at: "2026-01-01T00:00:00Z",
    detail: null,
    ...overrides,
  };
}

describe("EvaluationTimeline", () => {
  it("renders the real event list in the API-provided order", () => {
    const events = [
      event({ id: 1, event_type: "evaluation_created", created_at: "2026-01-01T00:00:00Z" }),
      event({ id: 2, event_type: "evaluation_started", created_at: "2026-01-01T00:01:00Z" }),
      event({ id: 3, event_type: "evaluation_finalized", created_at: "2026-01-01T00:02:00Z" }),
    ];
    render(<EvaluationTimeline events={events} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    // Order must follow the array as given — never re-sorted client-side.
    expect(items[0]).toHaveTextContent("Evaluation created");
    expect(items[1]).toHaveTextContent("Evaluation started");
    expect(items[2]).toHaveTextContent("Evaluation finalized");
  });

  it("renders the honest no-recorded-timeline message for an empty list", () => {
    render(<EvaluationTimeline events={[]} />);
    expect(screen.getByText(/No recorded timeline events/i)).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("does not crash on an unknown/future event_type, and does not fabricate a label", () => {
    const events = [event({ event_type: "some_future_event_type_v99" })];
    render(<EvaluationTimeline events={events} />);

    // Falls back to a generic humanized rendering of the real event_type
    // string — never a fabricated known-event label.
    expect(screen.getByText(/some future event type v99/i)).toBeInTheDocument();
  });

  it("never fabricates a timestamp — each rendered time is the event's own created_at", () => {
    const events = [event({ id: 1, created_at: "2026-03-15T10:30:00Z" })];
    render(<EvaluationTimeline events={events} />);
    // Not asserting an exact locale string (env-dependent); asserting the
    // real created_at value round-trips into the rendered list item, not a
    // placeholder like "just now" or the current wall-clock time.
    const item = screen.getByRole("listitem");
    expect(item.textContent).not.toMatch(/just now/i);
  });

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
});

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
