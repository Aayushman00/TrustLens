import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { EvidenceChip, toEvidenceRef } from "./EvidenceChip";

// Real ref from results/flawed_model_suite/eval_results_v2/variant6_compound.json
const RAW = {
  uri: "s3://trustlens/evidence/39efa7ad-95a2-4281-85f5-b5dbaa7c4a8c/c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5.json",
  hash: "sha256:86ad1cd39099df1de8ddc73c2af90c53a60de07e9cff1d081dc782922b5ca149",
  created_at: "2026-09-15T00:05:29.311587Z",
  probe_name: "fairness",
  evidence_id: "c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5",
  content_type: "application/json",
};

test("toEvidenceRef keeps string fields and nulls the rest", () => {
  expect(toEvidenceRef(RAW).evidence_id).toBe(RAW.evidence_id);
  expect(toEvidenceRef({ hash: 42 }).hash).toBeNull();
  expect(toEvidenceRef({}).content_type).toBeNull();
});

test("chip shows short id, type and hash", () => {
  render(<EvidenceChip evidence={toEvidenceRef(RAW)} />);
  expect(screen.getByText("ev_c8b8f84a")).toBeInTheDocument();
  expect(screen.getByText("application/json")).toBeInTheDocument();
  expect(screen.getByText("86ad1cd3…a149")).toBeInTheDocument();
});

test("clicking traces the evidence", () => {
  const onTrace = vi.fn();
  render(<EvidenceChip evidence={toEvidenceRef(RAW)} onTrace={onTrace} />);
  fireEvent.click(screen.getByRole("button", { name: `Trace evidence ${RAW.evidence_id}` }));
  expect(onTrace).toHaveBeenCalledWith(expect.objectContaining({ evidence_id: RAW.evidence_id }));
});

test("missing fields are labelled, not blank", () => {
  render(<EvidenceChip evidence={toEvidenceRef({})} />);
  expect(screen.getByText("ev_unknown")).toBeInTheDocument();
  expect(screen.getByText("unknown type")).toBeInTheDocument();
  expect(screen.getByText("— not recorded")).toBeInTheDocument();
});
