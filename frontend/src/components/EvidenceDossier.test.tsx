/**
 * EvidenceDossier — audit items 3 & 5. Protects: evidence categories render
 * from real ProbeEvidenceRead data, gate/rule info comes straight from the
 * backend (no recomputation), unavailable/not-run states are honest, and
 * (item 5) the primary Evidence Dossier tags its evidence chain with the
 * same EvidenceChainTag taxonomy ReportTraceabilityPanel uses on the Report
 * page — observed evidence, derived metric, gate/rule, risk decision, human
 * judgment, and limitation are each visibly distinct.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProbeEvidenceRead } from "../api/types";
import EvidenceDossier from "./EvidenceDossier";

function probe(overrides: Partial<ProbeEvidenceRead> = {}): ProbeEvidenceRead {
  return {
    dimension: "FAIRNESS",
    status: "EVALUATED",
    status_reason: null,
    methodology_version: "v1",
    gates: null,
    risks_triggered: null,
    aspect_scoring: null,
    scored_risk_id: null,
    claim_boundary: null,
    limitations: null,
    flags: null,
    coverage_ratio: null,
    n_evaluated: 500,
    fairness_mode: "model_faithful",
    pairing_id: "pairing-1",
    confidence: 0.87,
    evidence_refs: [{ hash: "sha256:deadbeef", uri: "s3://trustlens/evidence/x.json" }],
    model_ref: "bert-base-uncased",
    model_revision: "abc123",
    dataset_key: "sst2",
    dataset_revision: "rev1",
    evaluation_class: "model_faithful",
    inference_executed: true,
    metric_values: { demographic_parity_difference: 0.03 },
    ...overrides,
  };
}

describe("EvidenceDossier", () => {
  it("renders honest 'Not run' state when no probe evidence exists for the dimension", () => {
    render(<EvidenceDossier dimension="ROBUSTNESS" probe={undefined} />);
    expect(screen.getByText("Not run for this evaluation.")).toBeInTheDocument();
  });

  it("renders real evidence-hash/URI directly from the backend probe (no recomputation)", () => {
    render(<EvidenceDossier dimension="FAIRNESS" probe={probe()} />);
    expect(screen.getByText("sha256:deadbeef")).toBeInTheDocument();
    expect(screen.getByText("s3://trustlens/evidence/x.json")).toBeInTheDocument();
    // Model identity is a straight read, not derived.
    expect(screen.getByText("bert-base-uncased")).toBeInTheDocument();
    expect(screen.getByText("abc123")).toBeInTheDocument();
  });

  it("displays gate/rule information exactly as recorded, not synthesized", () => {
    render(
      <EvidenceDossier
        dimension="ROBUSTNESS"
        probe={probe({ dimension: "ROBUSTNESS", gates: ["G-ROB-EPSILON-DROP", "G-ROB-MIN-N"] })}
      />,
    );
    expect(screen.getByText("G-ROB-EPSILON-DROP, G-ROB-MIN-N")).toBeInTheDocument();
  });

  it("renders an honest 'Unavailable' for fields the backend did not persist", () => {
    render(
      <EvidenceDossier
        dimension="FAIRNESS"
        probe={probe({ model_revision: null, evidence_refs: [], confidence: null })}
      />,
    );
    // Field helper renders "Unavailable" for a null/undefined value.
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });

  it("shows an honest insufficient-evidence status via the status pill, not a fabricated pass", () => {
    render(
      <EvidenceDossier
        dimension="FAIRNESS"
        probe={probe({ status: "INSUFFICIENT_EVIDENCE", status_reason: "Too few rows in the smallest group." })}
      />,
    );
    expect(screen.getByText("Too few rows in the smallest group.")).toBeInTheDocument();
  });

  describe("EvidenceChainTag taxonomy (item 5)", () => {
    it("renders every taxonomy category with its correct label", () => {
      render(
        <EvidenceDossier
          dimension="FAIRNESS"
          probe={probe({ gates: ["G-FAIR-MIN-N"], aspect_scoring: "material_disparity", limitations: ["Small sample."] })}
        />,
      );
      expect(screen.getByText("Observed evidence")).toBeInTheDocument();
      expect(screen.getByText("Derived metric")).toBeInTheDocument();
      expect(screen.getByText("Gate / rule")).toBeInTheDocument();
      expect(screen.getByText("Risk decision")).toBeInTheDocument();
      expect(screen.getByText("Human judgment")).toBeInTheDocument();
      expect(screen.getByText("Limitation")).toBeInTheDocument();
    });

    it("distinguishes observed evidence from the derived metric", () => {
      render(<EvidenceDossier dimension="FAIRNESS" probe={probe({ confidence: 0.75 })} />);
      const observed = screen.getByText("Observed evidence");
      const metric = screen.getByText("Derived metric");
      expect(observed).not.toBe(metric);
      expect(observed.className).toContain("chain-tag-evidence");
      expect(metric.className).toContain("chain-tag-metric");
      // The derived metric step shows the real confidence, not invented.
      expect(screen.getByText(/0\.75/)).toBeInTheDocument();
    });

    it("distinguishes gate/rule from risk decision", () => {
      render(
        <EvidenceDossier
          dimension="ROBUSTNESS"
          probe={probe({
            dimension: "ROBUSTNESS",
            gates: ["G-ROB-EPSILON-DROP"],
            aspect_scoring: "material_drop",
            scored_risk_id: "R-ROB-PERT",
          })}
        />,
      );
      const gate = screen.getByText("Gate / rule");
      const risk = screen.getByText("Risk decision");
      expect(gate.className).toContain("chain-tag-gate");
      expect(risk.className).toContain("chain-tag-risk");
      expect(screen.getByText(/G-ROB-EPSILON-DROP/)).toBeInTheDocument();
      expect(screen.getByText(/R-ROB-PERT/)).toBeInTheDocument();
    });

    it("distinguishes human judgment from machine-measured evidence — no O/S/D fabricated here", () => {
      render(<EvidenceDossier dimension="FAIRNESS" probe={probe()} />);
      const human = screen.getByText("Human judgment");
      expect(human.className).toContain("chain-tag-human");
      expect(
        screen.getByText(/Human O\/S\/D for this dimension is entered separately/i),
      ).toBeInTheDocument();
      // Never infers/fabricates an O, S, or D value inside the dossier itself.
      expect(screen.queryByText(/^O:\s*\d/)).not.toBeInTheDocument();
    });

    it("renders the unavailable tag honestly when a probe never ran", () => {
      render(<EvidenceDossier dimension="SAFETY" probe={undefined} />);
      const unavailable = screen.getByText("Unavailable");
      expect(unavailable.className).toContain("chain-tag-unavailable");
      expect(screen.getByText("Not run for this evaluation.")).toBeInTheDocument();
    });

    it("renders the unavailable tag for a missing derived metric, without fabricating a number", () => {
      render(<EvidenceDossier dimension="FAIRNESS" probe={probe({ confidence: null })} />);
      // At least the metric-step's own "Unavailable" tag is present alongside its label.
      const unavailableTags = screen
        .getAllByText("Unavailable")
        .filter((el) => el.className.includes("chain-tag-unavailable"));
      expect(unavailableTags.length).toBeGreaterThan(0);
    });

    it("does not introduce an unsupported trust/safety claim via the new taxonomy rows", () => {
      render(<EvidenceDossier dimension="SAFETY" probe={probe({ dimension: "SAFETY" })} />);
      expect(screen.queryByText(/^Safe$/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/is a safe model/i)).not.toBeInTheDocument();
    });

    it("keeps existing evidence values unchanged (hash/URI/model identity still render)", () => {
      render(<EvidenceDossier dimension="FAIRNESS" probe={probe()} />);
      expect(screen.getByText("sha256:deadbeef")).toBeInTheDocument();
      expect(screen.getByText("s3://trustlens/evidence/x.json")).toBeInTheDocument();
      expect(screen.getByText("bert-base-uncased")).toBeInTheDocument();
    });

    it("shows gates only once — the chain-step row is not duplicated in Raw/technical evidence", () => {
      render(
        <EvidenceDossier
          dimension="ROBUSTNESS"
          probe={probe({ dimension: "ROBUSTNESS", gates: ["G-ROB-MIN-N"] })}
        />,
      );
      expect(screen.getAllByText(/G-ROB-MIN-N/).length).toBe(1);
    });
  });
});
