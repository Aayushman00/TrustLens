import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { apiFetch } from "../api/client";
import ModelDetailPage from "./ModelDetailPage";

vi.mock("../api/client");

const PINNED_MODEL = {
  id: 1,
  hf_repo_id: "org/model",
  model_metadata: { license: "apache-2.0", pipeline_tag: "text-classification" },
  checksum: "sha256:deadbeef",
  revision: "abc123def456",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};

const UNPINNED_MODEL = { ...PINNED_MODEL, id: 2, hf_repo_id: "org/unpinned", revision: null };

const NO_EVALUATIONS = { items: [], next_cursor: null };

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
});

function renderPage(modelId: number) {
  return render(
    <MemoryRouter initialEntries={[`/models/${modelId}`]}>
      <Routes>
        <Route path="/models/:id" element={<ModelDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("a pinned model shows the Evaluate link and a pinned-revision badge", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(PINNED_MODEL).mockResolvedValueOnce(NO_EVALUATIONS);
  renderPage(1);

  expect(await screen.findByText("Pinned revision")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /evaluate model/i })).toHaveAttribute(
    "href",
    "/evaluations/new?modelId=1",
  );
});

test("an unpinned model has no Evaluate link and explains why", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(UNPINNED_MODEL).mockResolvedValueOnce(NO_EVALUATIONS);
  renderPage(2);

  expect(await screen.findByText(/not reproducible/i)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /evaluate model/i })).not.toBeInTheDocument();
  expect(screen.getByText(/re-import with a revision/i)).toBeInTheDocument();
});

test("the Model Card tab shows the model card but no documentation-source form", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(PINNED_MODEL).mockResolvedValueOnce(NO_EVALUATIONS);
  renderPage(1);

  await screen.findByText("Pinned revision");
  screen.getByRole("tab", { name: /model card/i }).click();

  expect(await screen.findByText(/model card disclosures/i)).toBeInTheDocument();
  expect(screen.queryByText(/documentation sources/i)).not.toBeInTheDocument();
  expect(screen.queryByPlaceholderText(/arxiv\.org/i)).not.toBeInTheDocument();
  // No second apiFetch call for a documentation list should have happened.
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

// ---- migration regressions: loading / error / retry / empty / truncation ----

const EVAL = (id: string, model_id: number) => ({
  id, model_id, status: "FINALIZED", evaluation_mode: "AI_ASSISTED", probe_config: {},
  created_at: "2026-01-01T00:00:00Z",
});

test("shows a labelled loading state before the model arrives", () => {
  vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
  renderPage(1);
  expect(screen.getByRole("status")).toHaveTextContent("Loading model…");
});

test("a failed model load shows an alert with Retry and a way back, and Retry recovers", async () => {
  vi.mocked(apiFetch)
    .mockRejectedValueOnce(new Error("boom"))
    .mockResolvedValueOnce(NO_EVALUATIONS) // evaluations request of the failed attempt
    .mockResolvedValueOnce(PINNED_MODEL)
    .mockResolvedValueOnce(NO_EVALUATIONS);
  renderPage(1);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  expect(screen.getByRole("link", { name: "Back to models" })).toHaveAttribute("href", "/models");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Pinned revision")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a failed evaluations request does not hide the model; Retry reloads", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce(PINNED_MODEL)
    .mockRejectedValueOnce(new Error("history down"))
    .mockResolvedValueOnce(PINNED_MODEL)
    .mockResolvedValueOnce({ items: [EVAL("aaaaaaaa-1", 1)], next_cursor: null });
  renderPage(1);
  await screen.findByText("Pinned revision");
  await userEvent.click(screen.getByRole("tab", { name: /evaluations/i }));
  const panel = await screen.findByRole("tabpanel");
  expect(await within(panel).findByRole("alert")).toHaveTextContent("history down");
  await userEvent.click(within(panel).getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("link", { name: "Evaluation aaaaaaaa" })).toBeInTheDocument();
});

test("history only lists this model, and says when it searched everything", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce(PINNED_MODEL)
    .mockResolvedValueOnce({ items: [EVAL("aaaaaaaa-1", 1), EVAL("bbbbbbbb-2", 99)], next_cursor: null });
  renderPage(1);
  await screen.findByText("Pinned revision");
  expect(screen.getByRole("tab", { name: "Evaluations (1)" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: /evaluations/i }));
  expect(screen.getByRole("link", { name: "Evaluation aaaaaaaa" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Evaluation bbbbbbbb" })).not.toBeInTheDocument();
  expect(screen.getByText("Searched all evaluations.")).toBeInTheDocument();
});

test("an empty history is not claimed as complete when the API result was truncated", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce(PINNED_MODEL)
    .mockResolvedValueOnce({ items: [EVAL("bbbbbbbb-2", 99)], next_cursor: "more" });
  renderPage(1);
  await screen.findByText("Pinned revision");
  expect(screen.getByRole("tab", { name: "Evaluations (0+)" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: /evaluations/i }));
  expect(screen.getByText(/Searched the 200 most recent evaluations; older runs/)).toBeInTheDocument();
  expect(screen.getByText(/None found yet/)).toBeInTheDocument();
});

test("tabs follow the keyboard pattern: arrows move selection and focus, panel is labelled", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(PINNED_MODEL).mockResolvedValueOnce(NO_EVALUATIONS);
  renderPage(1);
  await screen.findByText("Pinned revision");
  const overview = screen.getByRole("tab", { name: "Overview" });
  overview.focus();
  expect(overview).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("tab", { name: "Model Card" })).toHaveAttribute("tabindex", "-1");
  await userEvent.keyboard("{ArrowRight}");
  const evaluations = screen.getByRole("tab", { name: /evaluations/i });
  expect(evaluations).toHaveFocus();
  expect(evaluations).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveAccessibleName(/evaluations/i);
  await userEvent.keyboard("{End}");
  expect(screen.getByRole("tab", { name: "Model Card" })).toHaveFocus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveFocus();
});

test("navigating to another model clears the previous model instead of showing stale data", async () => {
  let resolveSecond!: (v: unknown) => void;
  vi.mocked(apiFetch).mockImplementation(((...args: unknown[]) => {
    const path = String(args[0]);
    if (path === "/v1/models/1") return Promise.resolve(PINNED_MODEL);
    if (path === "/v1/models/2") return new Promise((r) => { resolveSecond = r; });
    return Promise.resolve(NO_EVALUATIONS);
  }) as never);
  render(
    <MemoryRouter initialEntries={["/models/1"]}>
      <Link to="/models/2">next</Link>
      <Routes>
        <Route path="/models/:id" element={<ModelDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "model" });
  await userEvent.click(screen.getByRole("link", { name: "next" }));
  expect(screen.queryByRole("heading", { name: "model" })).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Loading model…");
  resolveSecond(UNPINNED_MODEL);
  expect(await screen.findByRole("heading", { name: "unpinned" })).toBeInTheDocument();
});

test("a genuinely empty, non-truncated history says searched all and offers to start one", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce(PINNED_MODEL)
    .mockResolvedValueOnce({ items: [EVAL("bbbbbbbb-2", 99)], next_cursor: null });
  renderPage(1);
  await screen.findByText("Pinned revision");
  expect(screen.getByRole("tab", { name: "Evaluations (0)" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: /evaluations/i }));
  const panel = screen.getByRole("tabpanel");
  expect(within(panel).getByText("Searched all evaluations.")).toBeInTheDocument();
  expect(within(panel).queryByText(/most recent evaluations/)).not.toBeInTheDocument();
  expect(within(panel).getByText(/None yet/)).toBeInTheDocument();
  expect(within(panel).queryByText(/None found yet/)).not.toBeInTheDocument();
  expect(within(panel).getByRole("link", { name: "start one" })).toHaveAttribute(
    "href", "/evaluations/new?modelId=1",
  );
  expect(within(panel).queryByRole("table")).not.toBeInTheDocument();
});

test("an unpinned model with no history explains re-import instead of offering to start one", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce(UNPINNED_MODEL)
    .mockResolvedValueOnce({ items: [], next_cursor: null });
  renderPage(2);
  await screen.findByText(/not reproducible/i);
  await userEvent.click(screen.getByRole("tab", { name: /evaluations/i }));
  const panel = screen.getByRole("tabpanel");
  expect(within(panel).getByText(/re-import with a revision to evaluate/i)).toBeInTheDocument();
  expect(within(panel).queryByRole("link", { name: "start one" })).not.toBeInTheDocument();
});
