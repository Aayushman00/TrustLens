import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { apiFetch } from "../api/client";
import { countStatuses } from "../lib/overview";
import OverviewPage from "./OverviewPage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: vi.fn() };
});

const ev = (id: string, status: string) => ({
  id, model_id: 1, status, evaluation_mode: "AI_ASSISTED", probe_config: {},
  created_at: "2026-01-01T00:00:00Z",
});
const model = { id: 1, hf_repo_id: "org/m", revision: "abcdef1234", created_at: "2026-01-01T00:00:00Z" };

function mockApi(evals: unknown, models: unknown) {
  vi.mocked(apiFetch).mockImplementation((path: string) =>
    path.includes("/v1/models") ? (models as never) : (evals as never),
  );
}
const renderPage = () => render(<MemoryRouter><OverviewPage /></MemoryRouter>);

test("counts statuses with explicit buckets and links awaiting review", async () => {
  mockApi(
    Promise.resolve({ items: [ev("aaaaaaaa-1", "AWAITING_REVIEW"), ev("bbbbbbbb-2", "RUNNING"), ev("cccccccc-3", "FINALIZED"), ev("dddddddd-4", "FAILED")], next_cursor: "x" }),
    Promise.resolve({ items: [model], next_cursor: null }),
  );
  renderPage();
  const link = await screen.findByRole("link", { name: /Review evaluation aaaaaaaa/ });
  expect(link).toHaveAttribute("href", "/evaluations/aaaaaaaa-1/review");
  const tile = screen.getByText("Awaiting review", { selector: ".stat-tile-label" }).closest("a")!;
  expect(within(tile).getByText("1")).toBeInTheDocument();
  expect(screen.getByText(/older evaluations exist/)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Evaluation status" })).toBeInTheDocument();
});

test("partial failure: models error does not hide evaluations", async () => {
  mockApi(
    Promise.resolve({ items: [ev("eeeeeeee-5", "FINALIZED")], next_cursor: null }),
    Promise.reject(new Error("boom")),
  );
  renderPage();
  expect(await screen.findByText("Models could not be loaded.")).toBeInTheDocument();
  expect(screen.getByText("#1")).toBeInTheDocument();
  expect(screen.getByText(/all evaluations/)).toBeInTheDocument();
});

test("empty state offers next action", async () => {
  mockApi(Promise.resolve({ items: [], next_cursor: null }), Promise.resolve({ items: [], next_cursor: null }));
  renderPage();
  expect(await screen.findByRole("link", { name: "start a new evaluation" })).toHaveAttribute("href", "/evaluations/new");
});

test("countStatuses puts every status in exactly one bucket, unknown included", () => {
  const statuses = [
    "PENDING", "RUNNING", "PROBES_COMPLETED", "AGENT_COMPLETED",
    "AWAITING_REVIEW", "FINALIZED", "FAILED", "FINALIZED", "SOMETHING_NEW",
  ];
  const c = countStatuses(statuses.map((status) => ({ status })) as never);
  expect(c).toEqual({ awaiting: 1, active: 4, finalized: 2, failed: 1, other: 1, total: 9 });
  expect(c.awaiting + c.active + c.finalized + c.failed + c.other).toBe(c.total);
});
