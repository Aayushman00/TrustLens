import { render, screen } from "@testing-library/react";
import { arcPath, Dial } from "./Dial";

test("arcPath is deterministic", () => {
  // 135° → (13.62, 50.38); 405° ≡ 45° → (50.38, 50.38); 270° sweep → large-arc flag 1
  expect(arcPath(32, 32, 26, 135, 405)).toBe("M 13.62 50.38 A 26 26 0 1 1 50.38 50.38");
});

test("dial announces value with the inverted convention", () => {
  render(<Dial letter="O" value={6} source="agent" />);
  const meter = screen.getByRole("meter", { name: "Occurrence" });
  expect(meter).toHaveAttribute("aria-valuenow", "6");
  expect(meter).toHaveAttribute("aria-valuetext", "Occurrence 6 of 10, higher is safer");
  expect(screen.getByTestId("dial-arc")).toBeInTheDocument();
  expect(screen.getByText("agent")).toBeInTheDocument();
});

test("null is unavailable, never zero", () => {
  render(<Dial letter="D" value={null} />);
  expect(screen.getByRole("meter", { name: "Detection" })).toHaveAttribute("aria-valuetext", "Detection unavailable");
  expect(screen.queryByTestId("dial-arc")).toBeNull();
  expect(screen.queryByText("0")).toBeNull();
});

test("zero shows 0 with no arc", () => {
  render(<Dial letter="S" value={0} />);
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.queryByTestId("dial-arc")).toBeNull();
});

test.each([Number.NaN, Number.POSITIVE_INFINITY])("non-finite %s is unavailable and does not crash", (bad) => {
  render(<Dial letter="O" value={bad} />);
  expect(screen.getByRole("meter", { name: "Occurrence" })).toHaveAttribute("aria-valuetext", "Occurrence unavailable");
  expect(screen.queryByText(/NaN|Infinity/)).toBeNull();
  expect(screen.queryByTestId("dial-arc")).toBeNull();
});
