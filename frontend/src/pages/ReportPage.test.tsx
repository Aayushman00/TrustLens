/**
 * ReportPage — audit item 3. Protects the report's core honesty invariants:
 * FRIES withheld never renders as a fabricated number, scored FRIES renders
 * the real value, sections come from the actual ReportV1 shape, and the
 * "Documentation coverage" wording (never "Explainability/Safety score") is
 * used for Track 1 dimensions.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
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

  it("renders NOT_APPLICABLE dimension distinctly from INSUFFICIENT_EVIDENCE", async () => {
    const report = baseReportJson({
      evidence_traceability: [
        {
          dimension: "FAIRNESS",
          status: "NOT_APPLICABLE",
          status_reason: "No compatible Fairness contract was selected.",
          aspect_scoring: null,
          scored_risk_id: null,
          risks_triggered: null,
          gates: null,
          coverage_ratio: null,
          confidence: null,
          evidence_refs: [],
          limitations: null,
          human_osd: null,
          fries_dimension_score: null,
        },
        {
          dimension: "ROBUSTNESS",
          status: "INSUFFICIENT_EVIDENCE",
          status_reason: "Not enough perturbation samples were evaluated.",
          aspect_scoring: null,
          scored_risk_id: null,
          risks_triggered: null,
          gates: null,
          coverage_ratio: null,
          confidence: null,
          evidence_refs: [],
          limitations: null,
          human_osd: null,
          fries_dimension_score: null,
        },
      ],
    });
    apiFetchMock.mockResolvedValueOnce(reportRead(report));
    renderReportPage();

    await waitFor(() => expect(screen.getAllByText(/not configured/i).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/insufficient evidence/i).length).toBeGreaterThan(0);
  });
});

// ---- migration regressions: scored vs withheld, basis, errors, empty states ----

function scoredJson(humanReviewed: boolean, overrides: Partial<ReportV1> = {}): ReportV1 {
  return baseReportJson({
    mode_disclosure: {
      evaluation_mode: humanReviewed ? "AI_ASSISTED" : "AI_AUTONOMOUS",
      human_reviewed: humanReviewed,
      disclaimer: humanReviewed ? "Human-reviewed." : "Not human-reviewed.",
      methodology_status: "DETERMINISTIC_OSD_V1",
    },
    score: {
      score_type: "original_FRIES",
      fries_score: 7.42,
      dimension_scores: { FAIRNESS: 6.5, ROBUSTNESS: 8.25 },
      finalized_osd: {
        aspects: [{ aspect: "FAIRNESS", O: 8, S: 7, D: 0, O_source: "human" }],
      },
      overall_confidence: 0.9,
      scoring_withheld: false,
      note: "Scored.",
    },
    ...overrides,
  });
}

function readFor(json: ReportV1): ReportRead {
  const r = reportRead(json);
  r.mode_disclosure = json.mode_disclosure;
  return r;
}

describe("ReportPage — scored vs withheld", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("withheld: no number, no score bars, headline appears once, explicit withheld sections", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    renderReportPage();
    await screen.findByText("Executive Assessment");
    expect(document.querySelector(".fries-value")).not.toBeInTheDocument();
    expect(document.querySelector(".score-bars")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Basis:/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Evaluation complete.")).toHaveLength(1);
    const fries = screen.getByRole("heading", { name: "FRIES Assessment" }).closest(".card") as HTMLElement;
    expect(within(fries).getByText(/Withheld\./)).toBeInTheDocument();
    expect(screen.getByText(/No settled human O\/S\/D yet/)).toBeInTheDocument();
  });

  it("a payload with scoring_withheld false but a null score is still treated as withheld", async () => {
    const json = baseReportJson();
    json.score.scoring_withheld = false; // inconsistent payload: no number to show
    apiFetchMock.mockResolvedValueOnce(reportRead(json));
    renderReportPage();
    await screen.findByText("Executive Assessment");
    expect(document.querySelector(".fries-value")).not.toBeInTheDocument();
    expect(screen.getAllByText(/FRIES withheld/i).length).toBeGreaterThan(0);
  });

  it("scored and human-reviewed: shows the number, its basis, and labelled score bars", async () => {
    apiFetchMock.mockResolvedValueOnce(readFor(scoredJson(true)));
    renderReportPage();
    expect(await screen.findByText("7.42")).toBeInTheDocument();
    expect(screen.getByText("Basis: human-reviewed O/S/D.")).toBeInTheDocument();
    const group = screen.getByRole("group", { name: /FRIES dimension scores/ });
    expect(within(group).getByText("6.50")).toBeInTheDocument();
    expect(within(group).getByText("8.25")).toBeInTheDocument();
    // A real zero stays a zero in the O/S/D table; only null renders Unavailable.
    const osd = screen.getByRole("table", { name: "Finalized human O/S/D per aspect" });
    expect(within(osd).getAllByRole("cell").map((c) => c.textContent)).toContain("0");
  });

  it("scored but not human-reviewed never claims a human basis", async () => {
    apiFetchMock.mockResolvedValueOnce(readFor(scoredJson(false)));
    renderReportPage();
    expect(await screen.findByText("7.42")).toBeInTheDocument();
    expect(screen.getByText("Basis: O/S/D that were not human-reviewed.")).toBeInTheDocument();
    expect(screen.queryByText(/Basis: human-reviewed/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Not human-reviewed").length).toBeGreaterThan(0);
  });
});

describe("ReportPage — errors, empty states, actions", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("shows a labelled loading state", () => {
    apiFetchMock.mockReturnValue(new Promise(() => {}));
    renderReportPage();
    expect(screen.getByRole("status")).toHaveTextContent(/Fetching report/);
  });

  it("a load error is an alert with Retry and a way back, and Retry recovers", async () => {
    apiFetchMock
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(reportRead(baseReportJson()));
    renderReportPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("link", { name: "Back to the evaluation" })).toHaveAttribute(
      "href", `/evaluations/${EVAL_ID}`,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Executive Assessment")).toBeInTheDocument();
    expect(screen.queryByText("boom")).not.toBeInTheDocument();
  });

  it("NOT_FINALIZED explains itself with a link back and offers no Retry", async () => {
    apiFetchMock.mockRejectedValueOnce(
      new ApiError(409, { code: "NOT_FINALIZED", message: "not finalized", details: {} }),
    );
    renderReportPage();
    expect(await screen.findByText(/only after the evaluation reaches FINALIZED/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the evaluation" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("empty sections say so instead of rendering blank tables", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    renderReportPage();
    await screen.findByText("Executive Assessment");
    expect(screen.getByText(/Not recorded — no probe performed local model inference/)).toBeInTheDocument();
    expect(screen.getByText("No limitations recorded.")).toBeInTheDocument();
    expect(screen.getByText(/No documentation sources recorded/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /Documentation sources/ })).not.toBeInTheDocument();
  });

  it("Regenerate posts to /generate, swaps in the new version and announces it", async () => {
    const v2 = readFor(scoredJson(true));
    v2.version = 2;
    v2.report_json.report_version = 2;
    apiFetchMock
      .mockResolvedValueOnce(reportRead(baseReportJson()))
      .mockResolvedValueOnce(v2);
    renderReportPage();
    await screen.findByRole("heading", { name: "Report v1" });
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(await screen.findByRole("heading", { name: "Report v2" })).toBeInTheDocument();
    expect(apiFetchMock.mock.calls[1]).toEqual([
      `/v1/reports/${EVAL_ID}/generate`, { method: "POST" },
    ]);
    expect(screen.getByText("Report regenerated as version 2.")).toBeInTheDocument();
  });

  it("a failed Regenerate keeps the existing report and shows the error in an alert", async () => {
    apiFetchMock
      .mockResolvedValueOnce(reportRead(baseReportJson()))
      .mockRejectedValueOnce(new Error("generate down"));
    renderReportPage();
    await screen.findByRole("heading", { name: "Report v1" });
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("generate down"));
    expect(screen.getByRole("heading", { name: "Report v1" })).toBeInTheDocument();
  });

  it("Download JSON saves the report payload under a versioned filename", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    const create = vi.fn(() => "blob:mock");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const clicks: string[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });
    renderReportPage();
    await screen.findByRole("heading", { name: "Report v1" });
    await userEvent.click(screen.getByRole("button", { name: "Download JSON" }));
    expect(clicks).toEqual(["trustlens-report-11111111-v1.json"]);
    expect(create).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:mock"));
    click.mockRestore();
  });

  it("View evidence honours reduced motion", async () => {
    apiFetchMock.mockResolvedValueOnce(reportRead(baseReportJson()));
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    window.matchMedia = ((q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} })) as never;
    renderReportPage();
    await screen.findByText("Executive Assessment");
    const buttons = screen.getAllByRole("button", { name: "View evidence" }).filter((b) => !(b as HTMLButtonElement).disabled);
    await userEvent.click(buttons[0]);
    expect(scroll).toHaveBeenCalledWith({ behavior: "auto" });
  });
});
