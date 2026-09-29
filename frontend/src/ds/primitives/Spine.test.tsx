import { render, screen, within } from "@testing-library/react";
import { Spine, type SpineStage } from "./Spine";

const STAGES: SpineStage[] = [
  { key: "draft", label: "Draft", state: "done", at: "2026-09-15T00:04:50Z" },
  { key: "probes", label: "Probes", state: "current" },
  { key: "review", label: "Human review", state: "not_required", note: "AI_AUTONOMOUS mode" },
  { key: "final", label: "Final score", state: "pending" },
];

test("current stage is aria-current=step and says Active in words", () => {
  render(<Spine stages={STAGES} />);
  const current = screen.getByText("Probes").closest("li")!;
  expect(current).toHaveAttribute("aria-current", "step");
  expect(within(current).getByText("Active")).toBeInTheDocument();
});

test("done stages lock with a timestamp; pending ones have none", () => {
  render(<Spine stages={STAGES} />);
  expect(screen.getByText("Draft").closest("li")!.querySelector("time")).toHaveAttribute("datetime", "2026-09-15T00:04:50Z");
  expect(screen.getByText("Final score").closest("li")!.querySelector("time")).toBeNull();
});

test("not-required stage explains why", () => {
  render(<Spine stages={STAGES} />);
  expect(screen.getByText("Not required")).toBeInTheDocument();
  expect(screen.getByText("AI_AUTONOMOUS mode")).toBeInTheDocument();
});
