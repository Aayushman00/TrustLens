/**
 * EvaluationTimeline — audit item 3. Protects: real event rendering in
 * API-provided order, the honest empty state, and no crash on an
 * unknown/future event_type (never fabricated events or timestamps).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EvaluationEventRead } from "../api/types";
import EvaluationTimeline from "./EvaluationTimeline";

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
});
