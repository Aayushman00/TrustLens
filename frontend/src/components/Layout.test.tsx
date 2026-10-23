import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import Layout, { routeTitle } from "./Layout";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<h1>page</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
});
afterEach(() => vi.unstubAllGlobals());

test("exposes banner, one primary nav, and main landmarks", () => {
  renderAt("/");
  expect(screen.getByRole("banner")).toBeInTheDocument();
  expect(screen.getAllByRole("navigation")).toHaveLength(1);
  expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main-content");
});

test("marks the current page, including nested routes", () => {
  renderAt("/evaluations/abc/review");
  const nav = screen.getByRole("navigation", { name: "Primary" });
  expect(within(nav).getByRole("link", { name: "Evaluations" })).toHaveAttribute("aria-current", "page");
  expect(within(nav).getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  // Exactly one current-page marker: the brand link must not duplicate it.
  expect(document.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
});

test("sets the document title from the route", () => {
  renderAt("/models/import");
  expect(document.title).toBe("Import model · TrustLens");
  expect(routeTitle("/nope")).toBeNull();
  expect(routeTitle("/models/m1")).toBe("Model");
});

test("menu button toggles the panel and Escape closes it", async () => {
  const user = userEvent.setup();
  renderAt("/");
  const button = screen.getByRole("button", { name: "Menu" });
  expect(button).toHaveAttribute("aria-expanded", "false");
  await user.click(button);
  expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
  await user.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "Menu" })).toHaveFocus();
});

test("navigating moves focus to main and closes the menu", async () => {
  const user = userEvent.setup();
  renderAt("/");
  await user.click(screen.getByRole("button", { name: "Menu" }));
  await user.click(screen.getByRole("link", { name: "Models" }));
  expect(screen.getByRole("main")).toHaveFocus();
  expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
});

test("API health is announced as text, with a down state", async () => {
  renderAt("/");
  expect(await screen.findByText("Local API: unreachable")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveAttribute("data-health", "down");
});
