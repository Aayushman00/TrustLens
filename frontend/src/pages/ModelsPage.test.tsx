import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { apiFetch } from "../api/client";
import ModelsPage from "./ModelsPage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: vi.fn() };
});

const model = (id: number, repo: string, revision: string | null) => ({
  id, hf_repo_id: repo, model_metadata: {}, checksum: null, revision,
  created_at: "2026-01-01T00:00:00Z", updated_at: null,
});
const renderPage = () => render(<MemoryRouter><ModelsPage /></MemoryRouter>);

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
});

test("pinned model links to evaluate; unpinned explains why it cannot", async () => {
  vi.mocked(apiFetch).mockResolvedValue({
    items: [model(1, "org/pinned", "abcdef1234"), model(2, "org/loose", null)],
    next_cursor: null,
  });
  renderPage();
  expect(await screen.findByRole("link", { name: "Evaluate org/pinned" })).toHaveAttribute(
    "href", "/evaluations/new?modelId=1",
  );
  expect(screen.queryByRole("link", { name: "Evaluate org/loose" })).not.toBeInTheDocument();
  expect(screen.getByText(/Evaluation needs a pinned revision/)).toBeInTheDocument();
  expect(screen.getByText("Not reproducible")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View model org/loose" })).toHaveAttribute("href", "/models/2");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

test("summary states loaded count; filter covers loaded rows only", async () => {
  vi.mocked(apiFetch).mockResolvedValue({
    items: [model(1, "org/bert-a", "r1"), model(2, "org/gpt-b", "r2")],
    next_cursor: "c1",
  });
  renderPage();
  expect(await screen.findByText("2 models loaded; more available.")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Filter loaded models by repo"), "bert");
  expect(screen.getByText(/1 of 2 loaded models match; older models are not loaded yet/)).toBeInTheDocument();
  expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(1);
  await userEvent.clear(screen.getByLabelText("Filter loaded models by repo"));
  await userEvent.type(screen.getByLabelText("Filter loaded models by repo"), "zzz");
  await userEvent.click(await screen.findByRole("button", { name: "Clear filter" }));
  expect(await screen.findByText("2 models loaded; more available.")).toBeInTheDocument();
});

test("load more appends using the cursor", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce({ items: [model(1, "org/a", "r")], next_cursor: "c1" })
    .mockResolvedValueOnce({ items: [model(2, "org/b", "r")], next_cursor: null });
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "Load 25 more models" }));
  expect(await screen.findByText("2 models loaded (all).")).toBeInTheDocument();
  expect(vi.mocked(apiFetch).mock.calls[1][0]).toBe("/v1/models?limit=25&cursor=c1");
});

test("error is not mislabelled as an empty registry and retry refetches", async () => {
  vi.mocked(apiFetch)
    .mockRejectedValueOnce(new Error("boom"))
    .mockResolvedValueOnce({ items: [model(1, "org/a", "r")], next_cursor: null });
  renderPage();
  const retry = await screen.findByRole("button", { name: "Retry" });
  expect(screen.queryByText(/No models registered yet/)).not.toBeInTheDocument();
  await userEvent.click(retry);
  expect(await screen.findByRole("link", { name: "View model org/a" })).toBeInTheDocument();
});

test("empty registry offers import", async () => {
  vi.mocked(apiFetch).mockResolvedValue({ items: [], next_cursor: null });
  renderPage();
  expect(await screen.findByRole("link", { name: "import one first" })).toHaveAttribute("href", "/models/import");
});
