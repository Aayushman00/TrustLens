import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import { apiFetch } from "../api/client";
import CreateEvaluationDraftPage from "./CreateEvaluationDraftPage";

vi.mock("../api/client");

const MODELS_PAGE = {
  items: [
    {
      id: 1,
      hf_repo_id: "org/model",
      model_metadata: {},
      checksum: null,
      revision: "abc123def456",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: null,
    },
  ],
  next_cursor: null,
};

const DRAFT_INCOMPLETE = {
  id: "draft-1",
  model_id: 1,
  status: "incomplete",
  fairness_confirmed: false,
  robustness_confirmed: false,
};

const DRAFT_FAIRNESS_CONFIRMED = {
  ...DRAFT_INCOMPLETE,
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
  render(<CreateEvaluationDraftPage />);

  const modelCard = await screen.findByText("org/model");
  fireEvent.click(modelCard);

  vi.mocked(apiFetch).mockResolvedValueOnce(DRAFT_INCOMPLETE);
  fireEvent.click(screen.getByRole("button", { name: /start draft/i }));
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
