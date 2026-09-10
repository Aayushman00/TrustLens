import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import ColumnRoleMappingForm from "./ColumnRoleMappingForm";
import { apiFetch } from "../api/client";

vi.mock("../api/client");

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

test("submits column roles and shows validation result", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce({ values: ["pos", "neg"] })
    .mockResolvedValueOnce({
      ok: true,
      errors: [],
      group_preview: [{ value: "a", count: 3, meets_min_group_n: true }],
      groups_remaining: 2,
    });
  const onValidated = vi.fn();
  render(
    <ColumnRoleMappingForm draftId="draft-1" dimension="FAIRNESS" content={CONTENT} onValidated={onValidated} />
  );

  fireEvent.change(screen.getByLabelText(/text column/i), { target: { value: "text" } });
  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });
  await screen.findByText(/map dataset labels to model labels/i);
  fireEvent.change(screen.getByLabelText(/sensitive column/i), { target: { value: "group" } });

  // Confirm mapping rows before mapping them: never pre-selected.
  fireEvent.change(screen.getByLabelText(/^pos/i), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText(/^neg/i), { target: { value: "0" } });

  fireEvent.click(screen.getByRole("button", { name: /save.*validate/i }));

  await waitFor(() => expect(onValidated).toHaveBeenCalledWith(expect.objectContaining({ ok: true })));
});

test("label-mapping rows default to unmapped and never auto-select a matching label", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce({ values: ["positive", "negative"] });
  render(
    <ColumnRoleMappingForm draftId="draft-1" dimension="ROBUSTNESS" content={CONTENT} onValidated={vi.fn()} />
  );

  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });

  const positiveRow = (await screen.findByLabelText(/^positive/i)) as HTMLSelectElement;
  const negativeRow = screen.getByLabelText(/^negative/i) as HTMLSelectElement;

  // Even though "positive"/"negative" look like obvious case-insensitive
  // matches for model labels "POSITIVE"/"NEGATIVE", neither row is
  // pre-selected — both must start at the "unmapped" sentinel (-1).
  expect(positiveRow.value).toBe("-1");
  expect(negativeRow.value).toBe("-1");
});
