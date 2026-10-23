import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { apiFetch } from "../api/client";
import EvaluationsHistoryPage from "./EvaluationsHistoryPage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: vi.fn() };
});

const ev = (id: string, model_id: number, status = "FINALIZED") => ({
  id, model_id, status, evaluation_mode: "AI_ASSISTED", probe_config: {},
  model_revision: null, created_at: "2026-01-01T00:00:00Z",
});
const renderPage = () => render(<MemoryRouter><EvaluationsHistoryPage /></MemoryRouter>);

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
});

test("reports loaded count and flags that more exist", async () => {
  vi.mocked(apiFetch).mockResolvedValue({ items: [ev("aaaaaaaa-1", 1), ev("bbbbbbbb-2", 2)], next_cursor: "c1" });
  renderPage();
  expect(await screen.findByText("2 evaluations loaded; more available.")).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Evaluations, newest first" })).toBeInTheDocument();
});

test("client filters say they cover loaded rows only, and can be cleared", async () => {
  vi.mocked(apiFetch).mockResolvedValue({ items: [ev("aaaaaaaa-1", 12), ev("bbbbbbbb-2", 3)], next_cursor: "c1" });
  renderPage();
  await screen.findByText(/2 evaluations loaded/);
  await userEvent.type(screen.getByLabelText("Model ID contains"), "99");
  expect(await screen.findByText(/0 of 2 loaded evaluations match; older evaluations are not loaded yet/)).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
  expect(await screen.findByText(/2 evaluations loaded/)).toBeInTheDocument();
});

test("status filter goes to the server and a stale response is ignored", async () => {
  let resolveAll!: (v: unknown) => void;
  vi.mocked(apiFetch).mockImplementation(((...args: unknown[]) => {
    if (String(args[0]).includes("status=FAILED")) {
      return Promise.resolve({ items: [ev("ffffffff-9", 9, "FAILED")], next_cursor: null });
    }
    return new Promise((r) => { resolveAll = r; });
  }) as never);
  renderPage();
  await userEvent.selectOptions(screen.getByLabelText("Status"), "FAILED");
  expect(await screen.findByRole("link", { name: "Evaluation ffffffff" })).toBeInTheDocument();
  await act(async () => {
    resolveAll({ items: [ev("aaaaaaaa-1", 1)], next_cursor: null }); // late "All" response
  });
  expect(screen.queryByRole("link", { name: "Evaluation aaaaaaaa" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Evaluation ffffffff" })).toBeInTheDocument();
});

test("error shows retry that refetches", async () => {
  vi.mocked(apiFetch).mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce({ items: [ev("aaaaaaaa-1", 1)], next_cursor: null });
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("link", { name: "Evaluation aaaaaaaa" })).toBeInTheDocument();
});

test("empty history offers next action", async () => {
  vi.mocked(apiFetch).mockResolvedValue({ items: [], next_cursor: null });
  renderPage();
  expect(await screen.findByRole("link", { name: "start a new evaluation" })).toHaveAttribute("href", "/evaluations/new");
});
