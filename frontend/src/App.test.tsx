import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { apiFetch } from "./api/client";
import App from "./App";

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return { ...actual, apiFetch: vi.fn() };
});

test("evaluations/new renders the draft-based wizard by default", async () => {
  vi.mocked(apiFetch).mockResolvedValue({ items: [], next_cursor: null });
  window.history.pushState({}, "", "/evaluations/new");

  render(<App />);

  expect(await screen.findByText("New evaluation (draft wizard)")).toBeInTheDocument();
});
