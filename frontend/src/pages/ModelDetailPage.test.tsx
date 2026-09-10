import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
