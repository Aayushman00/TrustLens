import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import ColumnRoleMappingForm from "./ColumnRoleMappingForm";
import { apiFetch } from "../api/client";
import type { ModelLabelSnapshot } from "../api/types";

vi.mock("../api/client");

const SNAPSHOT_2CLASS: ModelLabelSnapshot = {
  num_labels: 2,
  id2label: { "0": "NEGATIVE", "1": "POSITIVE" },
};

const SNAPSHOT_3CLASS: ModelLabelSnapshot = {
  num_labels: 3,
  id2label: { "0": "LABEL_0", "1": "LABEL_1", "2": "LABEL_2" },
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
    <ColumnRoleMappingForm draftId="draft-1" dimension="FAIRNESS" content={CONTENT} modelLabelSnapshot={SNAPSHOT_2CLASS} onValidated={onValidated} />
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
    <ColumnRoleMappingForm draftId="draft-1" dimension="ROBUSTNESS" content={CONTENT} modelLabelSnapshot={SNAPSHOT_2CLASS} onValidated={vi.fn()} />
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

test("shows an ErrorNotice when the target-values fetch fails, instead of failing silently", async () => {
  vi.mocked(apiFetch).mockRejectedValueOnce(new Error("could not read target_column"));
  render(
    <ColumnRoleMappingForm draftId="draft-1" dimension="ROBUSTNESS" content={CONTENT} modelLabelSnapshot={SNAPSHOT_2CLASS} onValidated={vi.fn()} />
  );

  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });

  await screen.findByText(/could not read target_column/i);
  // No mapping rows are rendered when discovery failed — nothing to map.
  expect(screen.queryByText(/map dataset labels to model labels/i)).toBeNull();
});

test("a 3-class model snapshot shows exactly three real model-label choices", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce({ values: ["negative", "neutral", "positive"] });
  render(
    <ColumnRoleMappingForm
      draftId="draft-1"
      dimension="FAIRNESS"
      content={CONTENT}
      modelLabelSnapshot={SNAPSHOT_3CLASS}
      onValidated={vi.fn()}
    />
  );

  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });
  const negativeRow = (await screen.findByLabelText(/^negative/i)) as HTMLSelectElement;

  // Exactly three options besides the "unmapped" sentinel, and they are the
  // model's real (generic) labels -- not a hardcoded NEGATIVE/POSITIVE pair
  // that can't represent a third class.
  const optionTexts = Array.from(negativeRow.options).map((o) => o.textContent);
  expect(optionTexts).toEqual(["Select model label…", "LABEL_0", "LABEL_1", "LABEL_2"]);
  expect(screen.queryByText("NEGATIVE")).toBeNull();
  expect(screen.queryByText("POSITIVE")).toBeNull();
});

test("a 2-class model snapshot shows exactly two real model-label choices", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce({ values: ["pos", "neg"] });
  render(
    <ColumnRoleMappingForm
      draftId="draft-1"
      dimension="FAIRNESS"
      content={CONTENT}
      modelLabelSnapshot={SNAPSHOT_2CLASS}
      onValidated={vi.fn()}
    />
  );

  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });
  const posRow = (await screen.findByLabelText(/^pos/i)) as HTMLSelectElement;

  const optionTexts = Array.from(posRow.options).map((o) => o.textContent);
  expect(optionTexts).toEqual(["Select model label…", "NEGATIVE", "POSITIVE"]);
});

test("generic LABEL_N values are displayed unchanged, never renamed or inferred", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce({ values: ["neutral"] });
  render(
    <ColumnRoleMappingForm
      draftId="draft-1"
      dimension="ROBUSTNESS"
      content={CONTENT}
      modelLabelSnapshot={SNAPSHOT_3CLASS}
      onValidated={vi.fn()}
    />
  );

  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });
  await screen.findByLabelText(/^neutral/i);

  // The snapshot's generic id2label strings appear verbatim in the DOM.
  expect(screen.getByText("LABEL_0")).toBeTruthy();
  expect(screen.getByText("LABEL_1")).toBeTruthy();
  expect(screen.getByText("LABEL_2")).toBeTruthy();
});

test("with no model_label_snapshot, configuration is blocked rather than falling back to invented labels", () => {
  render(
    <ColumnRoleMappingForm
      draftId="draft-1"
      dimension="FAIRNESS"
      content={CONTENT}
      modelLabelSnapshot={null}
      onValidated={vi.fn()}
    />
  );

  // No hardcoded NEGATIVE/POSITIVE fallback, no column selects, no submit --
  // the form blocks with an explicit message instead of guessing.
  expect(screen.getByText(/model label metadata is not available/i)).toBeTruthy();
  expect(screen.queryByLabelText(/text column/i)).toBeNull();
  expect(screen.queryByRole("button", { name: /save.*validate/i })).toBeNull();
});

test("a stale target-values response does not overwrite a newer selection's rows", async () => {
  let resolveFirst!: (value: { values: string[] }) => void;
  let resolveSecond!: (value: { values: string[] }) => void;
  vi.mocked(apiFetch)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        })
    )
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSecond = resolve;
        })
    );

  render(
    <ColumnRoleMappingForm draftId="draft-1" dimension="ROBUSTNESS" content={CONTENT} modelLabelSnapshot={SNAPSHOT_2CLASS} onValidated={vi.fn()} />
  );

  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });
  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "group" } });

  // The second (current) request resolves first...
  resolveSecond({ values: ["a", "b"] });
  await screen.findByLabelText(/^a/i);

  // ...then the stale first request resolves late. It must be ignored.
  resolveFirst({ values: ["pos", "neg"] });

  await new Promise((r) => setTimeout(r, 0));
  expect(screen.queryByLabelText(/^pos/i)).toBeNull();
  expect(screen.getByLabelText(/^a/i)).toBeTruthy();
});
