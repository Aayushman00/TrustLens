import { fireEvent, render, screen } from "@testing-library/react";
import { Pentagon, vertex } from "./Pentagon";

const COMPOUND = { FAIRNESS: 6.6039, ROBUSTNESS: 9.0, INTEGRITY: 2.2894, EXPLAINABILITY: 1.2599, SAFETY: 1.2599 };

test("vertex 0 at full scale points straight up", () => {
  const [x, y] = vertex(0, 10);
  expect(x).toBeCloseTo(120, 6);
  expect(y).toBeCloseTo(28, 6);
});

test("complete scores draw a closed, filled shape", () => {
  const { container } = render(<Pentagon scores={COMPOUND} />);
  expect(container.querySelector("svg")).toHaveAttribute("data-complete", "true");
  expect(screen.getByTestId("penta-shape").getAttribute("d")).toMatch(/Z$/);
  expect(container.querySelectorAll("[data-dim]")).toHaveLength(5);
});

test("missing dimension is hollow, not zero, and not closed", () => {
  const { container } = render(<Pentagon scores={{ ...COMPOUND, SAFETY: null }} />);
  expect(container.querySelector("svg")).toHaveAttribute("data-complete", "false");
  expect(screen.getByTestId("penta-shape").getAttribute("d")).not.toMatch(/Z/);
  expect(container.querySelector('[data-missing="SAFETY"]')).not.toBeNull();
  expect(screen.getByRole("figure")).toHaveAccessibleDescription(/Safety not scored.*not counted as zero/);
  fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
  expect(screen.getByRole("row", { name: /Safety not scored/ })).toBeInTheDocument();
  expect(screen.queryByRole("cell", { name: "0.0000" })).toBeNull();
});

test("absent keys behave like null", () => {
  const { container } = render(<Pentagon scores={{ FAIRNESS: 5 }} />);
  expect(container.querySelectorAll("[data-missing]")).toHaveLength(4);
});

test("ghost outline renders proposed values", () => {
  render(<Pentagon scores={{}} ghost={COMPOUND} />);
  expect(screen.getByTestId("penta-ghost")).toBeInTheDocument();
});
