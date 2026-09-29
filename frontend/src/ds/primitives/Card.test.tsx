import { render, screen } from "@testing-library/react";
import { Card, Slip } from "./Card";

test("Card renders a titled section", () => {
  render(<Card title="Probe lanes">body</Card>);
  expect(screen.getByRole("heading", { name: "Probe lanes" })).toBeInTheDocument();
  expect(screen.getByText("body")).toBeInTheDocument();
});

test("Slip is evidence material with a label", () => {
  const { container } = render(<Slip label="metric_values">0.368</Slip>);
  expect(container.querySelector(".tl-slip")).not.toBeNull();
  expect(screen.getByText("metric_values")).toBeInTheDocument();
});
