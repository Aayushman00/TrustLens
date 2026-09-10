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
  vi.mocked(apiFetch).mockResolvedValueOnce({
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
  fireEvent.change(screen.getByLabelText(/sensitive column/i), { target: { value: "group" } });
  fireEvent.click(screen.getByRole("button", { name: /save.*validate/i }));

  await waitFor(() => expect(onValidated).toHaveBeenCalledWith(expect.objectContaining({ ok: true })));
});
