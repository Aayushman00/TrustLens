import { render, screen } from "@testing-library/react";
import { FRIES_DIMENSIONS } from "../../api/types";
import { DIMENSIONS } from "../dimensions";
import { DimensionMark } from "./DimensionMark";

test.each(FRIES_DIMENSIONS)("%s shows monogram + label", (d) => {
  render(<DimensionMark dimension={d} />);
  expect(screen.getByText(DIMENSIONS[d].monogram)).toBeInTheDocument();
  expect(screen.getByText(DIMENSIONS[d].label)).toBeInTheDocument();
});

test("label-less mark still has an accessible name", () => {
  render(<DimensionMark dimension="SAFETY" showLabel={false} />);
  expect(screen.getByRole("img", { name: "Safety" })).toBeInTheDocument();
});

test("each dimension has a distinct glyph shape", () => {
  const shapes = FRIES_DIMENSIONS.map((d) => DIMENSIONS[d].shape);
  expect(new Set(shapes).size).toBe(5);
});
