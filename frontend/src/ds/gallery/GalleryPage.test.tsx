import { fireEvent, render, screen } from "@testing-library/react";
import GalleryPage from "./GalleryPage";

const SECTIONS = [
  "Colour", "Type", "Motion", "Materials", "Status", "Dimensions", "Evidence",
  "Gauge", "Dial", "Score ring", "Pentagon", "Spine", "Timeline", "Trace panel",
];

test("every primitive has a gallery section", () => {
  render(<GalleryPage />);
  for (const name of SECTIONS) {
    expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
  }
});

test("labels itself as specimen data, never an audit", () => {
  render(<GalleryPage />);
  expect(screen.getByText(/Specimen data — not an audit/)).toBeInTheDocument();
});

test("theme and reduced-motion toggles set root attributes", () => {
  const { container } = render(<GalleryPage />);
  const root = container.firstElementChild!;
  expect(root).toHaveAttribute("data-theme", "dark");
  fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
  expect(root).toHaveAttribute("data-theme", "light");
  fireEvent.click(screen.getByRole("button", { name: "Reduce motion" }));
  expect(root).toHaveAttribute("data-motion", "reduce");
});

test("clicking a score opens the trace panel", () => {
  render(<GalleryPage />);
  fireEvent.click(screen.getByRole("button", { name: "Trace Fairness 6.60" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
