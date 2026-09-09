/**
 * ReviewPage — audit item 3. Protects the O/S/D independence invariant:
 * each of O, S, D is separately editable, leaving one blank never
 * auto-populates it, and no frontend default value is ever inserted.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { EvaluationRead } from "../api/types";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: apiFetchMock };
});

import ReviewPage from "./ReviewPage";

const EVAL_ID = "22222222-2222-2222-2222-222222222222";

function evaluationFixture(): EvaluationRead {
  return {
    id: EVAL_ID,
    model_id: 1,
    status: "AWAITING_REVIEW",
    evaluation_mode: "AI_ASSISTED",
    probe_config: {},
    task: "sst2",
    dataset: "sst2",
    config: "default",
    model_revision: "abc123",
    trustlens_version: "0.23.0",
    is_published: false,
    published_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    mode_disclosure: {
      evaluation_mode: "AI_ASSISTED",
      human_reviewed: false,
      disclaimer: "Not yet human-reviewed.",
      methodology_status: "DETERMINISTIC_OSD_V1",
    },
    osd_agent: {
      ai_confidence: null,
      methodology_status: "DETERMINISTIC_OSD_V1",
      rationale: null,
      ai_suggestion: {
        schema_version: "osd-agent-v1",
        methodology_status: "DETERMINISTIC_OSD_V1",
        assessment_engine: "deterministic",
        model_ref: "bert-base-uncased",
        overall_confidence: null,
        note: "Deterministic — no O/S/D inferred.",
        aspects: [
          { aspect: "FAIRNESS", O: null, S: null, D: null, confidence: 0, rationale: null },
          { aspect: "EXPLAINABILITY", O: null, S: null, D: null, confidence: 0, rationale: null },
        ],
      },
    },
  };
}

function renderReviewPage() {
  render(
    <MemoryRouter initialEntries={[`/evaluations/${EVAL_ID}/review`]}>
      <Routes>
        <Route path="/evaluations/:id/review" element={<ReviewPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ReviewPage — O/S/D independence", () => {
  it("lets O, S, and D be edited independently, with no auto-populated values", async () => {
    apiFetchMock.mockResolvedValueOnce(evaluationFixture());
    renderReviewPage();

    await waitFor(() => expect(screen.getByText("Review probe evidence")).toBeInTheDocument());

    const user = userEvent.setup();
    // Inputs start disabled under "Accept all" — uncheck it to edit.
    const acceptAll = screen.getByRole("checkbox");
    await user.click(acceptAll);

    const spinbuttons = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    // Two aspects (FAIRNESS, EXPLAINABILITY) x O/S/D = 6 inputs, in that order.
    expect(spinbuttons).toHaveLength(6);
    const [fairnessO, fairnessS, fairnessD, explainO] = spinbuttons;

    // All start blank — no frontend default value inserted.
    for (const input of spinbuttons) expect(input.value).toBe("");

    await user.type(fairnessO, "8");
    expect(fairnessO.value).toBe("8");
    // Editing O did not auto-populate S or D for the same aspect.
    expect(fairnessS.value).toBe("");
    expect(fairnessD.value).toBe("");
    // Editing one aspect did not touch the other aspect's fields.
    expect(explainO.value).toBe("");

    await user.type(fairnessS, "6");
    expect(fairnessS.value).toBe("6");
    expect(fairnessO.value).toBe("8"); // unaffected by editing a sibling field
    expect(fairnessD.value).toBe(""); // D still untouched/blank

    await user.type(explainO, "9");
    expect(explainO.value).toBe("9");
    // Unrelated aspect's values remain exactly as the user left them.
    expect(fairnessO.value).toBe("8");
    expect(fairnessS.value).toBe("6");
    expect(fairnessD.value).toBe("");
  });

  it("does not lock O/S/D fields for the deterministic engine (all independently enterable)", async () => {
    apiFetchMock.mockResolvedValueOnce(evaluationFixture());
    renderReviewPage();
    await waitFor(() => expect(screen.getByText("Review probe evidence")).toBeInTheDocument());

    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox"));

    for (const input of screen.getAllByRole("spinbutton")) {
      expect(input).not.toBeDisabled();
    }
  });
});
