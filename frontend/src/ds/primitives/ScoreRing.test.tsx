import { render, screen } from "@testing-library/react";
import { RING_CIRCUMFERENCE, ScoreRing } from "./ScoreRing";

test("final score: numeral, meter, static end-state dashoffset", () => {
  render(<ScoreRing value={6.6039} label="Fairness" />);
  expect(screen.getByText("6.60")).toBeInTheDocument();
  const meter = screen.getByRole("meter", { name: "Fairness" });
  expect(meter).toHaveAttribute("data-state", "final");
  expect(screen.getByTestId("ring-arc")).toHaveAttribute(
    "stroke-dashoffset",
    (RING_CIRCUMFERENCE * (1 - 0.66039)).toFixed(3),
  );
});

test("null is 'not scored', no arc, no zero", () => {
  render(<ScoreRing value={null} label="Safety" />);
  expect(screen.getByText("not scored")).toBeInTheDocument();
  expect(screen.queryByTestId("ring-arc")).toBeNull();
  expect(screen.queryByText("0.00")).toBeNull();
});

test("NaN is treated as not scored", () => {
  render(<ScoreRing value={Number.NaN} label="Safety" />);
  expect(screen.getByText("not scored")).toBeInTheDocument();
  expect(screen.queryByText("NaN")).toBeNull();
});

test("veto is labelled, not just darkest colour", () => {
  render(<ScoreRing value={0} veto label="Integrity" />);
  expect(screen.getByText("VETO")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "Integrity" })).toHaveAttribute("data-state", "veto");
});

test("proposed values say so", () => {
  render(<ScoreRing value={5.04} proposed label="Fairness" />);
  expect(screen.getByText("proposed")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "Fairness" })).toHaveAttribute(
    "aria-valuetext",
    "Fairness: 5.04 of 10, proposed — not final",
  );
});

test("out-of-range value clamps the arc but prints the true value", () => {
  render(<ScoreRing value={10.4} label="X" />);
  expect(screen.getByText("10.40")).toBeInTheDocument();
  expect(screen.getByTestId("ring-arc")).toHaveAttribute("stroke-dashoffset", "0.000");
});
