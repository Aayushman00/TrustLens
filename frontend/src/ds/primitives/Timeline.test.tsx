import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { Timeline, type TimelineEvent } from "./Timeline";

const EVENTS: TimelineEvent[] = [
  { id: 3, event_type: "probes_completed", created_at: "2026-09-15T00:06:08Z", detail: { probe_count: 5 } },
  { id: 1, event_type: "evaluation_created", created_at: "2026-09-15T00:04:50Z" },
  { id: 2, event_type: "evaluation_started", created_at: "2026-09-15T00:04:51Z" },
  { id: 4, event_type: "probe_heartbeat_v9", created_at: "2026-09-15T00:06:09Z" },
];

test("orders by id and shows +Δs from the first event", () => {
  render(<Timeline events={EVENTS} />);
  const items = screen.getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Evaluation created");
  expect(items[0]).toHaveTextContent("+0.0s");
  expect(items[2]).toHaveTextContent("Probes completed");
  expect(items[2]).toHaveTextContent("+78.0s");
});

test("is a polite live log", () => {
  render(<Timeline events={EVENTS} />);
  const log = screen.getByRole("log");
  expect(log).toHaveAttribute("aria-live", "polite");
});

test("unknown event types render verbatim", () => {
  render(<Timeline events={EVENTS} />);
  expect(screen.getAllByText("probe_heartbeat_v9").length).toBeGreaterThan(0);
});

test("filter narrows to one type", () => {
  render(<Timeline events={EVENTS} />);
  fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "evaluation_started" } });
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
});

test("rows are selectable when onSelect is given", () => {
  const onSelect = vi.fn();
  render(<Timeline events={EVENTS} onSelect={onSelect} />);
  fireEvent.click(screen.getAllByRole("button")[0]);
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
});

test("empty state is explicit", () => {
  render(<Timeline events={[]} />);
  expect(screen.getByText("No events recorded yet.")).toBeInTheDocument();
});

test("list keeps list semantics; the live log announces only the latest event", () => {
  render(<Timeline events={EVENTS} />);
  expect(screen.getByRole("list", { name: "Evaluation events" })).toBeInTheDocument();
  const log = screen.getByRole("log");
  expect(log).toHaveTextContent("Latest event: probe_heartbeat_v9");
  fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "evaluation_started" } });
  expect(screen.getByRole("log")).toHaveTextContent("Latest event: probe_heartbeat_v9");
});
