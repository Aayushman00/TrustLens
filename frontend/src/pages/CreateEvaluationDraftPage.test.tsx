import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { apiFetch, ApiError } from "../api/client";
import CreateEvaluationDraftPage from "./CreateEvaluationDraftPage";

// Real ApiError (not auto-mocked) so tests that reject with it produce a
// correctly-populated error (code/message/details) for ErrorNotice to render.
vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: vi.fn() };
});

function renderPage(initialPath = "/evaluations/new") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      {/* A stub destination route -- proves navigate(`/evaluations/${id}`)
       * actually fires, mirroring the real route in App.tsx without pulling
       * in the full EvaluationDetailPage. */}
      <Routes>
        <Route path="/evaluations/new" element={<CreateEvaluationDraftPage />} />
        <Route path="/evaluations/:id" element={<div data-testid="evaluation-detail-stub" />} />
      </Routes>
    </MemoryRouter>,
  );
}

const MODEL = {
  id: 1,
  hf_repo_id: "org/model",
  model_metadata: {},
  checksum: null,
  revision: "abc123def456",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};

const UNPINNED_MODEL = { ...MODEL, id: 2, hf_repo_id: "org/unpinned-model", revision: null };

const MODELS_PAGE = {
  items: [MODEL],
  next_cursor: null,
};

const DOCS_EMPTY = { items: [] };

const DRAFT_INCOMPLETE = {
  id: "draft-1",
  model_id: 1,
  status: "incomplete",
  fairness_confirmed: false,
  robustness_confirmed: false,
  model_label_snapshot: null,
};

// What the follow-up GET (fired right after POST /evaluation-drafts) returns
// once the backend has inspected the model's real config.
const DRAFT_WITH_SNAPSHOT = {
  ...DRAFT_INCOMPLETE,
  model_label_snapshot: { num_labels: 2, id2label: { "0": "NEGATIVE", "1": "POSITIVE" } },
};

const DRAFT_FAIRNESS_CONFIRMED = {
  ...DRAFT_WITH_SNAPSHOT,
  status: "validated",
  fairness_confirmed: true,
};

const CONTENT = {
  id: "content-1",
  content_hash: "abc",
  byte_size: 100,
  format: "csv",
  row_count: 5,
  columns: [
    { name: "text", inferred_type: "string" },
    { name: "label", inferred_type: "string" },
    { name: "group", inferred_type: "string" },
  ],
  created_at: "2026-01-01T00:00:00Z",
};

const VALIDATION_OK = {
  ok: true,
  errors: [],
  group_preview: [{ value: "a", count: 3, meets_min_group_n: true }],
  groups_remaining: 2,
};

async function selectModelAndCreateDraft() {
  vi.mocked(apiFetch).mockResolvedValueOnce(MODELS_PAGE);
  renderPage();

  const modelCard = await screen.findByText("org/model");
  fireEvent.click(modelCard);

  vi.mocked(apiFetch).mockResolvedValueOnce(DRAFT_INCOMPLETE);
  // The page immediately follows the create POST with a GET, so
  // model_label_snapshot (real model labels for the mapping UI) is
  // populated before the user ever opens a dimension.
  vi.mocked(apiFetch).mockResolvedValueOnce(DRAFT_WITH_SNAPSHOT);
  // DocumentationSourceForm mounts alongside Fairness/Robustness the moment
  // the draft exists and fetches this model's documentation sources.
  vi.mocked(apiFetch).mockResolvedValueOnce(DOCS_EMPTY);
  fireEvent.click(screen.getByRole("button", { name: /start evaluation/i }));
  await screen.findByLabelText(/configure fairness/i);
}

async function fillAndConfirmFairness() {
  // Enable the Fairness checkbox.
  fireEvent.click(screen.getByLabelText(/configure fairness/i));

  // DatasetIntakeForm: fetch a dataset.
  vi.mocked(apiFetch).mockResolvedValueOnce(CONTENT);
  fireEvent.change(screen.getByLabelText(/dataset url/i), {
    target: { value: "https://example.com/d.csv" },
  });
  fireEvent.click(screen.getByRole("button", { name: /fetch dataset/i }));
  await screen.findByText(/5 rows/i);

  // ColumnRoleMappingForm: pick columns, target-values fetch, then validate.
  vi.mocked(apiFetch).mockResolvedValueOnce({ values: ["pos", "neg"] });
  fireEvent.change(screen.getByLabelText(/^text column/i), { target: { value: "text" } });
  fireEvent.change(screen.getByLabelText(/^target column/i), { target: { value: "label" } });
  await screen.findByText(/map dataset labels to model labels/i);
  fireEvent.change(screen.getByLabelText(/sensitive column/i), { target: { value: "group" } });
  fireEvent.change(screen.getByLabelText(/^pos/i), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText(/^neg/i), { target: { value: "0" } });

  vi.mocked(apiFetch).mockResolvedValueOnce(VALIDATION_OK);
  fireEvent.click(screen.getByRole("button", { name: /save.*validate/i }));
  await screen.findByRole("button", { name: /^confirm fairness$/i });

  vi.mocked(apiFetch).mockResolvedValueOnce(DRAFT_FAIRNESS_CONFIRMED);
  fireEvent.click(screen.getByRole("button", { name: /^confirm fairness$/i }));
  await screen.findByRole("button", { name: /fairness confirmed/i });
}

test("full flow: select model, create draft, configure and confirm Fairness, Continue enables", async () => {
  await selectModelAndCreateDraft();

  expect(screen.getByLabelText(/configure fairness/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/configure robustness/i)).toBeInTheDocument();

  const continueButton = screen.getByRole("button", { name: /continue to review/i });
  expect(continueButton).toBeDisabled();

  await fillAndConfirmFairness();

  await waitFor(() => expect(continueButton).not.toBeDisabled());

  // Robustness was never enabled — it must not block Continue.
  expect(screen.getByLabelText(/configure robustness/i)).not.toBeChecked();
});

test("Continue stays disabled if a second enabled dimension is not yet confirmed", async () => {
  await selectModelAndCreateDraft();
  await fillAndConfirmFairness();

  const continueButton = screen.getByRole("button", { name: /continue to review/i });
  await waitFor(() => expect(continueButton).not.toBeDisabled());

  // Enabling Robustness (unconfirmed) must re-block Continue even though
  // Fairness is already confirmed.
  fireEvent.click(screen.getByLabelText(/configure robustness/i));
  expect(continueButton).toBeDisabled();
});

test("unchecking a confirmed dimension resets its confirmed state instead of leaving it stale", async () => {
  await selectModelAndCreateDraft();
  await fillAndConfirmFairness();

  const continueButton = screen.getByRole("button", { name: /continue to review/i });
  await waitFor(() => expect(continueButton).not.toBeDisabled());

  // Uncheck Fairness after confirming it.
  fireEvent.click(screen.getByLabelText(/configure fairness/i));

  // Continue has nothing enabled left, so it must go back to disabled.
  expect(continueButton).toBeDisabled();

  // Re-checking Fairness must start over — no stale "confirmed" button, and
  // no fresh DatasetIntakeForm content carried over from before.
  fireEvent.click(screen.getByLabelText(/configure fairness/i));
  const fairnessCard = screen.getByLabelText(/configure fairness/i).closest(".card") as HTMLElement;
  expect(within(fairnessCard).queryByRole("button", { name: /fairness confirmed/i })).toBeNull();
  expect(within(fairnessCard).queryByRole("button", { name: /^confirm fairness$/i })).toBeNull();
  expect(continueButton).toBeDisabled();
});

test("reached with ?modelId= skips model selection entirely", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(MODEL);
  renderPage("/evaluations/new?modelId=1");

  await screen.findByText("org/model");

  expect(screen.queryByText(/choose a model/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /choose a different model/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /start evaluation/i })).toBeInTheDocument();
});

test("reached without ?modelId= still offers to pick a model, and pick lets you go back", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(MODELS_PAGE);
  renderPage();

  const modelCard = await screen.findByText("org/model");
  fireEvent.click(modelCard);

  expect(
    screen.getByRole("button", { name: /choose a different model/i }),
  ).toBeInTheDocument();
});

test("an unpinned model blocks starting an evaluation, with no way around it", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(UNPINNED_MODEL);
  renderPage("/evaluations/new?modelId=2");

  await screen.findByText(/no pinned revision/i);
  expect(screen.queryByRole("button", { name: /start evaluation/i })).not.toBeInTheDocument();
});

test("a failed replacement dataset fetch clears the previously confirmed dimension's stale state", async () => {
  await selectModelAndCreateDraft();
  await fillAndConfirmFairness();

  const fairnessCard = screen.getByLabelText(/configure fairness/i).closest(".card") as HTMLElement;
  expect(within(fairnessCard).getByRole("button", { name: /fairness confirmed/i })).toBeInTheDocument();
  expect(within(fairnessCard).getByText(/5 rows/i)).toBeInTheDocument();

  // Try to replace the dataset with a URL that turns out to be HTML, not CSV.
  vi.mocked(apiFetch).mockRejectedValueOnce(
    new ApiError(422, {
      code: "VALIDATION_ERROR",
      message: "downloaded file is not a valid CSV: this URL points to a webpage (HTML), not a raw CSV dataset",
      details: {},
    }),
  );
  fireEvent.change(within(fairnessCard).getByLabelText(/dataset url/i), {
    target: { value: "https://huggingface.co/datasets/nyu-mll/glue" },
  });
  fireEvent.click(within(fairnessCard).getByRole("button", { name: /fetch dataset/i }));

  await within(fairnessCard).findByText(/not a raw CSV dataset/i);

  // The previously-confirmed dataset's rows/columns and the "confirmed"
  // state must not remain visible -- a failed replacement fetch drops the
  // stale confirmation and mapping UI immediately, not just on success.
  expect(within(fairnessCard).queryByText(/5 rows/i)).not.toBeInTheDocument();
  expect(within(fairnessCard).queryByRole("button", { name: /fairness confirmed/i })).not.toBeInTheDocument();
  expect(within(fairnessCard).queryByRole("button", { name: /^confirm fairness$/i })).not.toBeInTheDocument();
  expect(within(fairnessCard).queryByLabelText(/^text column/i)).not.toBeInTheDocument();

  const continueButton = screen.getByRole("button", { name: /continue to review/i });
  expect(continueButton).toBeDisabled();
});

test("the model card is included automatically, with room to attach more documentation", async () => {
  await selectModelAndCreateDraft();

  expect(screen.getByRole("heading", { name: /documentation/i })).toBeInTheDocument();
  expect(screen.getByText(/pinned model card is included automatically/i)).toBeInTheDocument();
});

test("Continue to review creates the real evaluation and navigates to it", async () => {
  await selectModelAndCreateDraft();
  await fillAndConfirmFairness();

  const continueButton = screen.getByRole("button", { name: /continue to review/i });
  await waitFor(() => expect(continueButton).not.toBeDisabled());

  const CREATED_EVALUATION = { id: "eval-999", model_id: 1, status: "PENDING" };
  vi.mocked(apiFetch).mockResolvedValueOnce(CREATED_EVALUATION);
  fireEvent.click(continueButton);

  // The exact contract this session's curl call verified the backend
  // accepts: draft_id + evaluation_mode + assessment_engine, POSTed to
  // /v1/evaluations-v2. assessment_engine defaults to "deterministic"
  // (the toggle below is unchecked unless the user opts in).
  await waitFor(() =>
    expect(apiFetch).toHaveBeenCalledWith("/v1/evaluations-v2", {
      method: "POST",
      body: {
        draft_id: "draft-1",
        evaluation_mode: "AI_ASSISTED",
        assessment_engine: "deterministic",
      },
    }),
  );

  // Navigated to the created evaluation's own page -- the stub route
  // standing in for EvaluationDetailPage renders, proving the navigation
  // actually fired rather than the button silently doing nothing.
  await screen.findByTestId("evaluation-detail-stub");
});

test("checking the legacy-heuristic toggle sends assessment_engine: legacy_heuristic", async () => {
  await selectModelAndCreateDraft();
  await fillAndConfirmFairness();

  const continueButton = screen.getByRole("button", { name: /continue to review/i });
  await waitFor(() => expect(continueButton).not.toBeDisabled());

  fireEvent.click(screen.getByLabelText(/legacy heuristic scoring/i));

  const CREATED_EVALUATION = { id: "eval-999", model_id: 1, status: "PENDING" };
  vi.mocked(apiFetch).mockResolvedValueOnce(CREATED_EVALUATION);
  fireEvent.click(continueButton);

  await waitFor(() =>
    expect(apiFetch).toHaveBeenCalledWith("/v1/evaluations-v2", {
      method: "POST",
      body: {
        draft_id: "draft-1",
        evaluation_mode: "AI_ASSISTED",
        assessment_engine: "legacy_heuristic",
      },
    }),
  );
});

test("a failed evaluation-creation request surfaces via ErrorNotice, not a silent no-op", async () => {
  await selectModelAndCreateDraft();
  await fillAndConfirmFairness();

  const continueButton = screen.getByRole("button", { name: /continue to review/i });
  await waitFor(() => expect(continueButton).not.toBeDisabled());

  vi.mocked(apiFetch).mockRejectedValueOnce(
    new ApiError(422, {
      code: "VALIDATION_ERROR",
      message: "draft is missing a confirmed dimension",
      details: {},
    }),
  );
  fireEvent.click(continueButton);

  await screen.findByText(/draft is missing a confirmed dimension/i);
  // Stays on this page -- no silent navigation on failure.
  expect(screen.queryByTestId("evaluation-detail-stub")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /continue to review/i })).not.toBeDisabled();
});
