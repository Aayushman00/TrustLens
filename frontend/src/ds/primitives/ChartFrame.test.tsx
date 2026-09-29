import { fireEvent, render, screen } from "@testing-library/react";
import { ChartFrame } from "./ChartFrame";

test("summary describes the figure; table toggle swaps the chart", () => {
  render(
    <ChartFrame title="Demo" summary="Two values." table={{ columns: ["k", "v"], rows: [["a", 1]] }}>
      <svg data-testid="chart" />
    </ChartFrame>,
  );
  expect(screen.getByRole("figure")).toHaveAccessibleDescription("Two values.");
  expect(screen.getByTestId("chart")).toBeInTheDocument();
  const toggle = screen.getByRole("button", { name: "Show as table" });
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.queryByTestId("chart")).toBeNull();
  expect(screen.getByRole("columnheader", { name: "k" })).toBeInTheDocument();
});
