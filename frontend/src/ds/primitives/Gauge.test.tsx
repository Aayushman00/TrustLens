import { fireEvent, render, screen } from "@testing-library/react";
import { Gauge, readCI } from "./Gauge";

// Real dp_ci from variant6_compound.json
const DP_CI = { B: 1000, point: 0.36831, method: "bootstrap_percentile", ci_lower: 0.326535, ci_upper: 0.412892 };

test("readCI narrows the backend CI shape", () => {
  expect(readCI(DP_CI)).toEqual({ lower: 0.326535, upper: 0.412892, method: "bootstrap_percentile" });
  expect(readCI(null)).toBeNull();
  expect(readCI({ ci_lower: "x" })).toBeNull();
});

test("renders value, CI band and summary", () => {
  render(<Gauge label="Demographic parity difference" metricKey="demographic_parity_difference" value={0.36831} ci={readCI(DP_CI)} />);
  expect(screen.getByText("0.368")).toBeInTheDocument();
  expect(screen.getByTestId("gauge-ci")).toBeInTheDocument();
  expect(screen.getByRole("figure")).toHaveAccessibleDescription(/0\.368.*0\.327 to 0\.413/);
});

test("null value is 'not reported', no marker", () => {
  render(<Gauge label="EOD" metricKey="equalized_odds_difference" value={null} />);
  expect(screen.getByText("— not reported")).toBeInTheDocument();
  expect(screen.queryByTestId("gauge-mark")).toBeNull();
});

test("out-of-range value clamps the marker but prints the true value", () => {
  render(<Gauge label="X" metricKey="x" value={1.7} max={1} />);
  expect(screen.getByTestId("gauge-mark")).toHaveAttribute("x1", "232");
  expect(screen.getByText("1.700")).toBeInTheDocument();
});

test("table view lists the metric key", () => {
  render(<Gauge label="X" metricKey="subgroup_f1_spread" value={0.160639} />);
  fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
  expect(screen.getByRole("cell", { name: "subgroup_f1_spread" })).toBeInTheDocument();
});

test("NaN value is 'not reported', never NaN", () => {
  render(<Gauge label="X" metricKey="x" value={Number.NaN} />);
  expect(screen.getByText("— not reported")).toBeInTheDocument();
  expect(screen.queryByText(/NaN/)).toBeNull();
  expect(screen.queryByTestId("gauge-mark")).toBeNull();
});

test("degenerate range (min === max) keeps the marker finite", () => {
  render(<Gauge label="X" metricKey="x" value={1} min={1} max={1} />);
  expect(Number.isFinite(Number(screen.getByTestId("gauge-mark").getAttribute("x1")))).toBe(true);
});
