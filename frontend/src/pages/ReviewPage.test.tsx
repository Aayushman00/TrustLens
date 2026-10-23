/**
 * ReviewPage — audit item 3. Protects the O/S/D independence invariant:
 * each of O, S, D is separately editable, leaving one blank never
 * auto-populates it, and no frontend default value is ever inserted.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
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

beforeEach(() => {
  apiFetchMock.mockReset();
});

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

// ---- migration regressions: validation, submit flow, partial failure, states ----

const FINALIZED_WITHHELD = {
  ...evaluationFixture(),
  status: "FINALIZED" as const,
  final_score: null,
};

const FINALIZED_SCORED = {
  ...evaluationFixture(),
  status: "FINALIZED" as const,
  final_score: {
    fries_score: 6.25,
    dimension_scores: {},
    overall_confidence: null,
    evaluation_mode: "AI_ASSISTED" as const,
    human_reviewed: true,
    disclaimer: null,
  },
};

async function openForm() {
  renderReviewPage();
  await screen.findByText("Review probe evidence");
  return userEvent.setup();
}

describe("ReviewPage — validation and submit flow", () => {
  it("gives every O/S/D input an accessible name", async () => {
    apiFetchMock.mockResolvedValueOnce(evaluationFixture());
    await openForm();
    expect(screen.getByRole("spinbutton", { name: /fairness O \(human/i })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /explainability D \(human/i })).toBeInTheDocument();
  });

  it("keeps an out-of-range value visible and blocks submit instead of silently dropping it", async () => {
    apiFetchMock.mockResolvedValueOnce(evaluationFixture());
    const user = await openForm();
    await user.click(screen.getByRole("checkbox"));
    const fairnessO = screen.getByRole("spinbutton", { name: /fairness O \(human/i }) as HTMLInputElement;
    await user.type(fairnessO, "11");
    expect(fairnessO.value).toBe("11"); // not collapsed to blank
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/whole numbers from 0 to 10.*fairness O/i),
    );
    expect(fairnessO).toHaveAttribute("aria-invalid", "true");
    expect(fairnessO).toHaveFocus();
    expect(apiFetchMock).toHaveBeenCalledTimes(1); // only the initial GET, nothing was posted
  });

  it("accept all posts accept_all then finalizes, and withheld scoring shows no FRIES number", async () => {
    apiFetchMock
      .mockResolvedValueOnce(evaluationFixture())
      .mockResolvedValueOnce({ id: 1 })
      .mockResolvedValueOnce(FINALIZED_WITHHELD);
    const user = await openForm();
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    const heading = await screen.findByRole("heading", { name: "Finalized" });
    expect(heading).toHaveFocus();
    expect(apiFetchMock.mock.calls[1]).toEqual([
      `/v1/evaluations/${EVAL_ID}/human-review`,
      { method: "POST", body: { accept_all: true } },
    ]);
    expect(apiFetchMock.mock.calls[2][0]).toBe(`/v1/evaluations/${EVAL_ID}/finalize`);
    expect(screen.getByText(/FRIES scoring is withheld/)).toBeInTheDocument();
    expect(screen.queryByText("original FRIES from your approved O/S/D")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View report" })).not.toBeInTheDocument();
  });

  it("a scored result shows the FRIES value and links to the report", async () => {
    apiFetchMock
      .mockResolvedValueOnce(evaluationFixture())
      .mockResolvedValueOnce({ id: 1 })
      .mockResolvedValueOnce(FINALIZED_SCORED);
    const user = await openForm();
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    expect(await screen.findByText("6.25")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View report" })).toHaveAttribute("href", `/reports/${EVAL_ID}`);
  });

  it("sends only aspects with a human value, and only the entered letters", async () => {
    apiFetchMock
      .mockResolvedValueOnce(evaluationFixture())
      .mockResolvedValueOnce({ id: 1 })
      .mockResolvedValueOnce(FINALIZED_WITHHELD);
    const user = await openForm();
    await user.click(screen.getByRole("checkbox"));
    await user.type(screen.getByRole("spinbutton", { name: /fairness O \(human/i }), "8");
    expect(screen.getByText("Complete O/S/D triples entered: 0 of 2 listed aspects.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    await screen.findByRole("heading", { name: "Finalized" });
    const body = apiFetchMock.mock.calls[1][1].body;
    expect(JSON.parse(JSON.stringify(body))).toEqual({
      accept_all: false,
      aspects: [{ aspect: "FAIRNESS", O: 8 }],
    });
  });

  it("if finalize fails after the review was recorded, retry only finalizes", async () => {
    apiFetchMock
      .mockResolvedValueOnce(evaluationFixture())
      .mockResolvedValueOnce({ id: 1 }) // human-review ok
      .mockRejectedValueOnce(new ApiError(500, { code: "INTERNAL", message: "finalize down", details: {} }))
      .mockResolvedValueOnce(FINALIZED_WITHHELD); // retry of finalize
    const user = await openForm();
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("finalize down"));
    expect(screen.getByText(/review was recorded/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry finalize" }));
    await screen.findByRole("heading", { name: "Finalized" });
    const paths = apiFetchMock.mock.calls.map((c) => String(c[0]));
    expect(paths.filter((p) => p.endsWith("/human-review"))).toHaveLength(1);
    expect(paths.filter((p) => p.endsWith("/finalize"))).toHaveLength(2);
  });
});

describe("ReviewPage — load states", () => {
  it("shows a labelled loading state", () => {
    apiFetchMock.mockReturnValue(new Promise(() => {}));
    renderReviewPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading review…");
  });

  it("a load error is an alert with Retry and a way back, and Retry recovers", async () => {
    apiFetchMock
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(evaluationFixture());
    renderReviewPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("link", { name: "Back to the evaluation" })).toHaveAttribute(
      "href", `/evaluations/${EVAL_ID}`,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Review probe evidence")).toBeInTheDocument();
    expect(screen.queryByText("boom")).not.toBeInTheDocument();
  });

  it("an evaluation that is not awaiting review says so and links back", async () => {
    apiFetchMock.mockResolvedValueOnce({ ...evaluationFixture(), status: "RUNNING" });
    renderReviewPage();
    const note = await screen.findByText(/nothing to review/);
    expect(within(note.closest(".notice") as HTMLElement).getByRole("link")).toHaveAttribute(
      "href", `/evaluations/${EVAL_ID}`,
    );
  });

  it("an evaluation with no O/S/D aspects offers a way back", async () => {
    const empty = evaluationFixture();
    empty.osd_agent!.ai_suggestion.aspects = [];
    apiFetchMock.mockResolvedValueOnce(empty);
    renderReviewPage();
    expect(await screen.findByText(/No O\/S\/D representation found/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the evaluation" })).toBeInTheDocument();
  });
});

describe("ReviewPage — legacy-heuristic path", () => {
  function legacyFixture(): EvaluationRead {
    const e = evaluationFixture();
    e.mode_disclosure = {
      evaluation_mode: "AI_ASSISTED",
      human_reviewed: false,
      disclaimer: "Not yet human-reviewed.",
      methodology_status: "HEURISTIC_PROPOSED",
    };
    const suggestion = e.osd_agent!.ai_suggestion;
    suggestion.assessment_engine = "legacy_heuristic";
    suggestion.methodology_status = "HEURISTIC_PROPOSED";
    e.osd_agent!.methodology_status = "HEURISTIC_PROPOSED";
    suggestion.aspects = [
      // Agent proposed only O for FAIRNESS; S and D are genuinely missing.
      { aspect: "FAIRNESS", O: 7, S: null, D: null, confidence: 0.4, rationale: null },
      { aspect: "EXPLAINABILITY", O: null, S: null, D: null, confidence: 0.2, rationale: null },
    ];
    return e;
  }

  it("is not treated as deterministic: shows the PROPOSED notice and prefills the agent suggestion", async () => {
    apiFetchMock.mockResolvedValueOnce(legacyFixture());
    const user = await openForm();
    expect(screen.getByText(/PROPOSED — not ground truth/)).toBeInTheDocument();
    expect(screen.queryByText(/Deterministic OSD v1/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("spinbutton", { name: /fairness O \(human/i })).toHaveValue(7);
    expect(screen.getByRole("spinbutton", { name: /fairness S \(human/i })).toHaveValue(null);
  });

  it("posts every aspect (exact body); blank O/S/D stay absent, an explicit 0 is sent as 0", async () => {
    apiFetchMock
      .mockResolvedValueOnce(legacyFixture())
      .mockResolvedValueOnce({ id: 1 })
      .mockResolvedValueOnce(FINALIZED_WITHHELD);
    const user = await openForm();
    await user.click(screen.getByRole("checkbox"));
    await user.type(screen.getByRole("spinbutton", { name: /fairness S \(human/i }), "4");
    await user.type(screen.getByRole("spinbutton", { name: /explainability D \(human/i }), "0");
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    await screen.findByRole("heading", { name: "Finalized" });

    const [path, options] = apiFetchMock.mock.calls[1];
    expect(path).toBe(`/v1/evaluations/${EVAL_ID}/human-review`);
    expect(options.method).toBe("POST");
    // Both aspects are sent (unlike the deterministic path, which omits empty ones);
    // blank fields are absent from the JSON, never 0 and never null.
    expect(JSON.stringify(options.body)).toBe(
      '{"accept_all":false,"aspects":[' +
        '{"aspect":"FAIRNESS","O":7,"S":4},' +
        '{"aspect":"EXPLAINABILITY","D":0}]}',
    );
    // Order is preserved: GET, human-review, then finalize.
    expect(apiFetchMock.mock.calls.map((c) => String(c[0]).split("/").pop())).toEqual([
      EVAL_ID, "human-review", "finalize",
    ]);
  });

  it("an aspect with nothing entered is still sent (empty), not dropped or zero-filled", async () => {
    apiFetchMock
      .mockResolvedValueOnce(legacyFixture())
      .mockResolvedValueOnce({ id: 1 })
      .mockResolvedValueOnce(FINALIZED_WITHHELD);
    const user = await openForm();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    await screen.findByRole("heading", { name: "Finalized" });
    expect(JSON.stringify(apiFetchMock.mock.calls[1][1].body)).toBe(
      '{"accept_all":false,"aspects":[{"aspect":"FAIRNESS","O":7},{"aspect":"EXPLAINABILITY"}]}',
    );
  });

  it("accept all on the legacy path still posts only accept_all", async () => {
    apiFetchMock
      .mockResolvedValueOnce(legacyFixture())
      .mockResolvedValueOnce({ id: 1 })
      .mockResolvedValueOnce(FINALIZED_WITHHELD);
    const user = await openForm();
    await user.click(screen.getByRole("button", { name: "Submit review + finalize" }));
    await screen.findByRole("heading", { name: "Finalized" });
    expect(JSON.stringify(apiFetchMock.mock.calls[1][1].body)).toBe('{"accept_all":true}');
  });
});
