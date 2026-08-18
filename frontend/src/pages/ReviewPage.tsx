import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import type {
  AspectOSDEdit,
  EvaluationRead,
  FriesDimension,
  HumanReviewRead,
  HumanReviewRequest,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ErrorNotice from "../components/ErrorNotice";
import ModeDisclosureBanner from "../components/ModeDisclosure";
import Spinner from "../components/Spinner";
import { fmtNumber } from "../lib/format";

type OsdDraft = Record<FriesDimension, { O: number; S: number; D: number }>;

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
            aspects.map((a) => [a.aspect, { O: a.O, S: a.S, D: a.D }]),
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

  function setValue(aspect: FriesDimension, key: "O" | "S" | "D", raw: string) {
    const value = Math.max(0, Math.min(10, Math.round(Number(raw) || 0)));
    setDraft((prev) =>
      prev ? { ...prev, [aspect]: { ...prev[aspect], [key]: value } } : prev,
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setSubmitError(null);
    setPhase("review");
    const body: HumanReviewRequest = acceptAll
      ? { accept_all: true }
      : {
          accept_all: false,
          aspects: (
            Object.entries(draft) as [FriesDimension, OsdDraft[FriesDimension]][]
          ).map(([aspect, values]): AspectOSDEdit => ({ aspect, ...values })),
        };
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
        Reviewing agent O/S/D requires the reviewer or admin role.{" "}
        <Link to={`/evaluations/${id}`}>Back to the evaluation</Link>.
      </div>
    );
  }
  if (error != null) return <ErrorNotice error={error} />;
  if (evaluation == null || draft == null) return <Spinner label="Loading review…" />;

  if (finalized?.final_score) {
    return (
      <div className="card">
        <h2>Finalized</h2>
        {finalized.mode_disclosure ? (
          <ModeDisclosureBanner disclosure={finalized.mode_disclosure} />
        ) : null}
        <div className="fries-hero">
          <span className="fries-value">{finalized.final_score.fries_score.toFixed(2)}</span>
          <span className="fries-label">original FRIES from your approved O/S/D</span>
        </div>
        <div className="btn-row" style={{ marginTop: "1rem" }}>
          <Link to={`/evaluations/${id}`} className="btn">
            Back to evaluation
          </Link>
          <Link to={`/reports/${id}`} className="btn btn-secondary">
            View report
          </Link>
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
        No agent O/S/D suggestion found for this evaluation.
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Review agent O/S/D</h1>
          <p className="muted mono">Evaluation {evaluation.id}</p>
        </div>
      </div>
      {evaluation.mode_disclosure ? (
        <ModeDisclosureBanner disclosure={evaluation.mode_disclosure} />
      ) : null}
      <div className="card">
        <div className="notice notice-warning">
          The agent values are <strong>PROPOSED — not ground truth</strong>. Your approved
          O/S/D becomes the finalized basis for the FRIES score.
        </div>
        <form className="form" onSubmit={handleSubmit}>
          <label className="radio-row">
            <input
              type="checkbox"
              checked={acceptAll}
              onChange={(e) => setAcceptAll(e.target.checked)}
            />
            <span>
              <strong>Accept all</strong> — take the agent suggestion as-is (uncheck to
              edit values).
            </span>
          </label>
          <div className="table-wrap review-grid">
            <table>
              <thead>
                <tr>
                  <th>Aspect</th>
                  <th className="num">Agent O/S/D</th>
                  <th className="num">Confidence</th>
                  <th>O</th>
                  <th>S</th>
                  <th>D</th>
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
                    </td>
                    <td className="num muted">
                      {aspect.O} / {aspect.S} / {aspect.D}
                    </td>
                    <td className="num muted">{fmtNumber(aspect.confidence)}</td>
                    {(["O", "S", "D"] as const).map((key) => (
                      <td key={key}>
                        <input
                          type="number"
                          min={0}
                          max={10}
                          step={1}
                          value={draft[aspect.aspect][key]}
                          disabled={acceptAll}
                          onChange={(e) => setValue(aspect.aspect, key, e.target.value)}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
