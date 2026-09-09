import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import type {
  AspectOSDEdit,
  EvaluationRead,
  FriesDimension,
  HumanReviewRead,
  HumanReviewRequest,
  OsdAspectSuggestion,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ErrorNotice from "../components/ErrorNotice";
import ModeDisclosureBanner from "../components/ModeDisclosure";
import Spinner from "../components/Spinner";
import { fmtNumber, fmtOsd, parseOsdInput } from "../lib/format";

type OsdDraft = Record<FriesDimension, { O: number | null; S: number | null; D: number | null }>;

function isDeterministicSuggestion(
  suggestion: EvaluationRead["osd_agent"] | null | undefined,
): boolean {
  const ai = suggestion?.ai_suggestion;
  return (
    ai?.assessment_engine === "deterministic" ||
    ai?.methodology_status === "DETERMINISTIC_OSD_V1"
  );
}

function formatAgentTriple(aspect: OsdAspectSuggestion): string {
  return `${fmtOsd(aspect.O)} / ${fmtOsd(aspect.S)} / ${fmtOsd(aspect.D)}`;
}

/** A short summary of the MACHINE-MEASURED evidence behind this aspect —
 * distinct from, and never a substitute for, the human O/S/D entered below.
 * Picks whichever known metric keys the probe actually persisted; never
 * invents a value for a metric that isn't present. */
const EVIDENCE_METRIC_LABELS: Record<string, string> = {
  accuracy_drop: "accuracy drop",
  demographic_parity_difference: "demographic parity diff",
  subgroup_worst_group_acc_gap: "worst-group acc gap",
  equalized_odds_difference: "equalized odds diff",
  coverage_ratio: "documentation coverage",
};

function evidenceSummary(metadata: Record<string, unknown> | undefined): string | null {
  if (!metadata) return null;
  const parts: string[] = [];
  for (const [key, label] of Object.entries(EVIDENCE_METRIC_LABELS)) {
    const value = metadata[key];
    if (typeof value === "number") parts.push(`${label}: ${value.toFixed(3)}`);
  }
  const status = metadata.probe_status ?? metadata.status;
  if (typeof status === "string") parts.push(`status: ${status}`);
  return parts.length ? parts.join(" · ") : null;
}

export default function ReviewPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [evaluation, setEvaluation] = useState<EvaluationRead | null>(null);
  const [error, setError] = useState<unknown>(null);

  const [acceptAll, setAcceptAll] = useState(true);
  const [draft, setDraft] = useState<OsdDraft | null>(null);
  const [notes, setNotes] = useState("");
  const [rationale, setRationale] = useState("");
  const [phase, setPhase] = useState<"idle" | "review" | "finalize">("idle");
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [finalized, setFinalized] = useState<EvaluationRead | null>(null);

  const isReviewerRole = user?.role === "reviewer" || user?.role === "admin";

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const row = await apiFetch<EvaluationRead>(`/v1/evaluations/${id}`);
        if (cancelled) return;
        setEvaluation(row);
        const aspects = row.osd_agent?.ai_suggestion.aspects ?? [];
        setDraft(
          Object.fromEntries(
            aspects.map((a) => [
              a.aspect,
              { O: a.O ?? null, S: a.S ?? null, D: a.D ?? null },
            ]),
          ) as OsdDraft,
        );
      } catch (err) {
        if (!cancelled) setError(err);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const aspects = useMemo(
    () => evaluation?.osd_agent?.ai_suggestion.aspects ?? [],
    [evaluation],
  );
  const deterministic = useMemo(
    () => isDeterministicSuggestion(evaluation?.osd_agent),
    [evaluation],
  );

  function setValue(
    aspect: FriesDimension,
    key: "O" | "S" | "D",
    raw: string,
  ) {
    // O, S, and D are each independently human-enterable — no field is ever
    // locked, on either the deterministic or legacy-heuristic path.
    const value = parseOsdInput(raw);
    setDraft((prev) =>
      prev ? { ...prev, [aspect]: { ...prev[aspect], [key]: value } } : prev,
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setSubmitError(null);
    setPhase("review");
    let body: HumanReviewRequest;
    if (acceptAll) {
      body = { accept_all: true };
    } else if (deterministic) {
      const edits: AspectOSDEdit[] = [];
      for (const [aspect, values] of Object.entries(draft) as [
        FriesDimension,
        OsdDraft[FriesDimension],
      ][]) {
        // O, S, D are each independently optional — an aspect with none of
        // the three entered is simply omitted (not sent as an empty edit).
        if (values.O === null && values.S === null && values.D === null) continue;
        edits.push({
          aspect,
          O: values.O ?? undefined,
          S: values.S ?? undefined,
          D: values.D ?? undefined,
        });
      }
      if (edits.length === 0) {
        setSubmitError(new Error("Provide at least one O, S, or D value, or use accept all."));
        setPhase("idle");
        return;
      }
      body = { accept_all: false, aspects: edits };
    } else {
      body = {
        accept_all: false,
        aspects: (
          Object.entries(draft) as [FriesDimension, OsdDraft[FriesDimension]][]
        ).map(([aspect, values]): AspectOSDEdit => ({
          aspect,
          O: values.O ?? undefined,
          S: values.S ?? undefined,
          D: values.D ?? undefined,
        })),
      };
    }
    if (notes.trim()) body.notes = notes.trim();
    if (rationale.trim()) body.review_rationale = rationale.trim();
    try {
      await apiFetch<HumanReviewRead>(`/v1/evaluations/${id}/human-review`, {
        method: "POST",
        body,
      });
      setPhase("finalize");
      setFinalized(
        await apiFetch<EvaluationRead>(`/v1/evaluations/${id}/finalize`, {
          method: "POST",
        }),
      );
    } catch (err) {
      setSubmitError(err);
    } finally {
      setPhase("idle");
    }
  }

  if (!isReviewerRole) {
    return (
      <div className="notice notice-warning">
        Reviewing O/S/D requires the reviewer or admin role.{" "}
        <Link to={`/evaluations/${id}`}>Back to the evaluation</Link>.
      </div>
    );
  }
  if (error != null) return <ErrorNotice error={error} />;
  if (evaluation == null || draft == null) return <Spinner label="Loading review…" />;

  if (finalized?.status === "FINALIZED") {
    const withheld = finalized.final_score == null;
    return (
      <div className="card">
        <h2>Finalized</h2>
        {finalized.mode_disclosure ? (
          <ModeDisclosureBanner disclosure={finalized.mode_disclosure} />
        ) : null}
        {withheld ? (
          <div className="notice notice-info">
            Review recorded. FRIES scoring is withheld because at least one required
            aspect does not have a complete human O/S/D triple yet.
          </div>
        ) : (
          <div className="fries-hero">
            <span className="fries-value">
              {finalized.final_score!.fries_score.toFixed(2)}
            </span>
            <span className="fries-label">original FRIES from your approved O/S/D</span>
          </div>
        )}
        <div className="btn-row" style={{ marginTop: "1rem" }}>
          <Link to={`/evaluations/${id}`} className="btn">
            Back to evaluation
          </Link>
          {!withheld ? (
            <Link to={`/reports/${id}`} className="btn btn-secondary">
              View report
            </Link>
          ) : null}
        </div>
      </div>
    );
  }

  if (evaluation.evaluation_mode !== "AI_ASSISTED") {
    return (
      <div className="notice notice-info">
        Only AI-Assisted evaluations have a human-review step.{" "}
        <Link to={`/evaluations/${id}`}>Back to the evaluation</Link>.
      </div>
    );
  }
  if (evaluation.status !== "AWAITING_REVIEW") {
    return (
      <div className="notice notice-info">
        This evaluation is {evaluation.status.replaceAll("_", " ").toLowerCase()} — nothing
        to review. <Link to={`/evaluations/${id}`}>Back to the evaluation</Link>.
      </div>
    );
  }
  if (aspects.length === 0) {
    return (
      <div className="notice notice-error">
        No O/S/D representation found for this evaluation.
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Review probe evidence</h1>
          <p className="muted mono">Evaluation {evaluation.id}</p>
        </div>
      </div>
      {evaluation.mode_disclosure ? (
        <ModeDisclosureBanner disclosure={evaluation.mode_disclosure} />
      ) : null}
      <div className="card">
        <div className="notice notice-warning">
          {deterministic ? (
            <>
              <strong>Deterministic OSD v1</strong> — TrustLens has no approved automatic
              mapping from evidence to O, S, or D. All three below are{" "}
              <strong>human assessment you enter</strong>, not a measured model property.
              Each is optional and independent; FRIES is withheld until every required
              aspect has a complete O/S/D triple.
            </>
          ) : (
            <>
              The heuristic values are <strong>PROPOSED — not ground truth</strong> and
              are not an LLM assessment. Your approved O/S/D becomes the finalized
              basis for the FRIES score.
            </>
          )}
        </div>
        <form className="form" onSubmit={handleSubmit}>
          <label className="radio-row">
            <input
              type="checkbox"
              checked={acceptAll}
              onChange={(e) => setAcceptAll(e.target.checked)}
            />
            <span>
              <strong>Accept all</strong> —{" "}
              {deterministic
                ? "accept the probe evidence representation as-is (no O/S/D fabricated)."
                : "take the agent suggestion as-is (uncheck to edit values)."}
            </span>
          </label>
          <p className="field-hint" style={{ marginTop: "1rem" }}>
            The "Machine-measured evidence" column is read-only, from the probes. The O/S/D
            columns are <strong>human assessment</strong> you enter — recorded with
            source&nbsp;=&nbsp;"human", never generated by a probe.
          </p>
          <div className="table-wrap review-grid">
            <table>
              <thead>
                <tr>
                  <th>Aspect</th>
                  <th>Machine-measured evidence</th>
                  <th className="num">Recorded O/S/D</th>
                  <th className="num">Confidence</th>
                  <th>O (human)</th>
                  <th>S (human)</th>
                  <th>D (human)</th>
                </tr>
              </thead>
              <tbody>
                {aspects.map((aspect) => (
                  <tr key={aspect.aspect}>
                    <td>
                      {aspect.aspect.toLowerCase()}
                      {aspect.rationale ? (
                        <div className="field-hint">{aspect.rationale}</div>
                      ) : null}
                      {aspect.osd_metadata?.scored_risk_id ? (
                        <div className="field-hint">
                          Named risk: {String(aspect.osd_metadata.scored_risk_id)}
                        </div>
                      ) : null}
                    </td>
                    <td className="muted" style={{ fontSize: "0.82rem" }}>
                      {evidenceSummary(aspect.osd_metadata) ?? "No measured evidence recorded"}
                    </td>
                    <td className="num muted">{formatAgentTriple(aspect)}</td>
                    <td className="num muted">{fmtNumber(aspect.confidence)}</td>
                    {(["O", "S", "D"] as const).map((key) => {
                      const value = draft[aspect.aspect][key];
                      return (
                        <td key={key}>
                          <input
                            type="number"
                            min={0}
                            max={10}
                            step={1}
                            value={value ?? ""}
                            placeholder="optional"
                            disabled={acceptAll}
                            onChange={(e) =>
                              setValue(aspect.aspect, key, e.target.value)
                            }
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="field-hint">
            Leaving a field blank keeps it missing — TrustLens never assigns a default O,
            S, or D value. An aspect stays incomplete (and FRIES stays withheld) until all
            three are entered for it.
          </p>
          <label>
            Notes (optional)
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <label>
            Review rationale (optional)
            <input value={rationale} onChange={(e) => setRationale(e.target.value)} />
          </label>
          <ErrorNotice error={submitError} />
          <div className="btn-row">
            <button type="submit" className="btn" disabled={phase !== "idle"}>
              {phase === "review"
                ? "Submitting review…"
                : phase === "finalize"
                  ? "Finalizing…"
                  : "Submit review + finalize"}
            </button>
            <Link to={`/evaluations/${id}`} className="btn btn-secondary">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </>
  );
}
