/**
 * ReportPage — audit item 3. Protects the report's core honesty invariants:
 * FRIES withheld never renders as a fabricated number, scored FRIES renders
 * the real value, sections come from the actual ReportV1 shape, and the
 * "Documentation coverage" wording (never "Explainability/Safety score") is
 * used for Track 1 dimensions.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ReportRead, ReportV1 } from "../api/types";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: apiFetchMock };
});

import ReportPage from "./ReportPage";

const EVAL_ID = "11111111-1111-1111-1111-111111111111";

function baseReportJson(overrides: Partial<ReportV1> = {}): ReportV1 {
  return {
    schema_version: "report_v1",
    report_version: 1,
    generated_at: "2026-01-01T00:00:00Z",
    evaluation: {
      id: EVAL_ID,
      status: "FINALIZED",
      evaluation_mode: "AI_AUTONOMOUS",
      model_ref: "bert-base-uncased",
      model_id: 1,
      created_at: "2026-01-01T00:00:00Z",
      finalized_context: { task: "sst2", dataset: "sst2", config: "default" },
    },
    mode_disclosure: {
      evaluation_mode: "AI_AUTONOMOUS",
      human_reviewed: false,
      disclaimer: "Not human-reviewed.",
      methodology_status: "DETERMINISTIC_OSD_V1",
    },
    score: {
      score_type: "original_FRIES",
      fries_score: null,
      dimension_scores: {},
      finalized_osd: {},
      overall_confidence: null,
      scoring_withheld: true,
      note: "FRIES withheld — incomplete O/S/D.",
    },
    confidence_summary: null,
    probes: [
      {
        dimension: "EXPLAINABILITY",
        metric_values: { coverage_ratio: 0.8 },
        confidence: 0.9,
        flags: [],
        evidence_refs: [],
      },
    ],
    osd_agent: null,
    human_review: null,
    attack_flags: [],
    executive_summary: { headline: "Evaluation complete.", bullets: [] },
    evidence_traceability: [
      {
        dimension: "EXPLAINABILITY",
        status: "EVALUATED",
        status_reason: null,
        aspect_scoring: null,
        scored_risk_id: null,
        risks_triggered: null,
        gates: null,
        coverage_ratio: 0.8,
        confidence: 0.9,
        evidence_refs: [],
        limitations: null,
        human_osd: null,
        fries_dimension_score: null,
      },
    ],
    execution_environment: null,
    documentation_sources: [],
    reproducibility: {},
    limitations: [],
    ...overrides,
  };
}

function reportRead(reportJson: ReportV1): ReportRead {
  return {
    evaluation_id: EVAL_ID,
    version: reportJson.report_version,
    json_uri: "s3://trustlens/reports/x.json",
    json_hash: "sha256:abc",
    pdf_uri: null,
    pdf_hash: null,
    fries_score: reportJson.score.fries_score,
    mode_disclosure: reportJson.mode_disclosure,
    generated_at: reportJson.generated_at,
    report_json: reportJson,
  };
}

function renderReportPage() {
  render(
    <MemoryRouter initialEntries={[`/reports/${EVAL_ID}`]}>
      <Routes>
        <Route path="/reports/:evaluationId" element={<ReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ReportPage", () => {
  it("renders the withheld FRIES state explicitly, never as 0/blank/None", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    renderReportPage();

    await waitFor(() => expect(screen.getAllByText(/FRIES withheld/i).length).toBeGreaterThan(0));

    // Never a fabricated numeric FRIES score rendered — the hero score
    // element (".fries-value") must not exist at all when withheld.
    expect(document.querySelector(".fries-value")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Withheld/i).length).toBeGreaterThan(0);
  });

  it("renders the scored FRIES state with the real number", async () => {
    const scoredJson = baseReportJson({
      score: {
        score_type: "original_FRIES",
        fries_score: 7.42,
        dimension_scores: { EXPLAINABILITY: 6.5 },
        finalized_osd: {
          aspects: [{ aspect: "EXPLAINABILITY", O: 8, S: 7, D: 7, O_source: "human" }],
        },
        overall_confidence: 0.9,
        scoring_withheld: false,
        note: "Scored.",
      },
    });
    apiFetchMock.mockResolvedValueOnce(reportRead(scoredJson));
    renderReportPage();

    await waitFor(() => expect(screen.getByText("7.42")).toBeInTheDocument());
    expect(screen.queryByText(/FRIES withheld/i)).not.toBeInTheDocument();
  });

  it("renders sections from the actual ReportV1 shape (contract, model, dataset identity)", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    renderReportPage();

    await waitFor(() => expect(screen.getByText("Evaluation Contract")).toBeInTheDocument());
    expect(screen.getByText("Model Identity")).toBeInTheDocument();
    expect(screen.getByText("Dataset Identity")).toBeInTheDocument();
    expect(screen.getAllByText("sst2").length).toBeGreaterThan(0);
    expect(screen.getByText("bert-base-uncased")).toBeInTheDocument();
  });

  it("uses the Documentation coverage wording for Track 1 dimensions, never an unqualified explainability/safety score label", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    renderReportPage();

    await waitFor(() => expect(screen.getAllByText(/Documentation coverage/i).length).toBeGreaterThan(0));
    // The traceability panel explicitly disclaims "Never an 'Explainability
    // score'" (substring match would false-positive on that disclaimer) —
    // assert no element's *entire* text is the bare, unqualified label.
    expect(screen.queryByText("Explainability score", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Safety score", { exact: true })).not.toBeInTheDocument();
    expect(screen.getByText(/Never an/)).toBeInTheDocument();
  });

  it("does not generate unsupported trust/safety/explainability claims", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    renderReportPage();

    await waitFor(() => expect(screen.getByText("Evaluation Contract")).toBeInTheDocument());
    // No bare, unqualified claim anywhere on the page.
    expect(screen.queryByText(/^Safe$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Verified$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/is a safe model/i)).not.toBeInTheDocument();
  });
});
