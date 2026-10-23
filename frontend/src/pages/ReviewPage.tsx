import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
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
import ErrorNotice from "../components/ErrorNotice";
import ModeDisclosureBanner from "../components/ModeDisclosure";
import Spinner from "../components/Spinner";
import { fmtNumber, fmtOsd, parseOsdInput } from "../lib/format";
import "./ReviewPage.css";

// Raw field text, not parsed numbers: a value like "11" or "2.5" must stay
// visible (and be flagged) rather than silently collapsing to "missing".
type OsdDraft = Record<FriesDimension, { O: string; S: string; D: string }>;

const KEYS = ["O", "S", "D"] as const;
type OsdKey = (typeof KEYS)[number];

/** Non-empty text that is not a whole number 0-10. Empty is legitimately "missing". */
function isInvalidOsd(raw: string): boolean {
  return raw.trim() !== "" && parseOsdInput(raw) === null;
}

function isDeterministicSuggestion(
  suggestion: EvaluationRead["osd_agent"] | null | undefined,
): boolean {
  const ai = suggestion?.ai_suggestion;
  return (
    ai?.assessment_engine === "deterministic" ||
    ai?.methodology_status === "DETERMINISTIC_OSD_V1"
  );
}

/** "O / S / D" with each value an unbreakable unit, so a narrow column wraps
 * between values instead of stranding a lone slash. Null stays "Unavailable". */
function AgentTriple({ aspect }: { aspect: OsdAspectSuggestion }) {
  const values = [fmtOsd(aspect.O), fmtOsd(aspect.S), fmtOsd(aspect.D)];
  return (
    <span className="rv-triple">
      {values.map((v, i) => (
        <span key={i}>
          {i > 0 ? " / " : ""}
          {v}
          {i < values.length - 1 ? " " : ""}
        </span>
      ))}
    </span>
  );
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
  const [evaluation, setEvaluation] = useState<EvaluationRead | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);

  const [acceptAll, setAcceptAll] = useState(true);
  const [draft, setDraft] = useState<OsdDraft | null>(null);
  const [notes, setNotes] = useState("");
  const [rationale, setRationale] = useState("");
  const [phase, setPhase] = useState<"idle" | "review" | "finalize">("idle");
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [finalized, setFinalized] = useState<EvaluationRead | null>(null);
  // The human-review POST can succeed while finalize fails. Remember that, so
  // a retry only repeats finalize instead of submitting a second review.
  const [reviewSaved, setReviewSaved] = useState(false);
  const [showInvalid, setShowInvalid] = useState(false);
  const finalizedHeadingRef = useRef<HTMLHeadingElement>(null);
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => {
    let cancelled = false;
    // A new route id (or a retry) starts clean: nothing from a previous
    // evaluation may linger under the new URL.
    setEvaluation(null);
    setError(null);
    setDraft(null);
    setFinalized(null);
    setReviewSaved(false);
    setSubmitError(null);
    setShowInvalid(false);
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
              {
                O: a.O == null ? "" : String(a.O),
                S: a.S == null ? "" : String(a.S),
                D: a.D == null ? "" : String(a.D),
              },
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
  }, [id, attempt]);

  useEffect(() => {
    if (finalized?.status === "FINALIZED") finalizedHeadingRef.current?.focus();
  }, [finalized]);

  const aspects = useMemo(
    () => evaluation?.osd_agent?.ai_suggestion.aspects ?? [],
    [evaluation],
  );
  const deterministic = useMemo(
    () => isDeterministicSuggestion(evaluation?.osd_agent),
    [evaluation],
  );

  function setValue(aspect: FriesDimension, key: OsdKey, raw: string) {
    // O, S, and D are each independently human-enterable — no field is ever
    // locked, on either the deterministic or legacy-heuristic path.
    setDraft((prev) =>
      prev ? { ...prev, [aspect]: { ...prev[aspect], [key]: raw } } : prev,
    );
  }

  async function finalizeOnly() {
    setPhase("finalize");
    setFinalized(
      await apiFetch<EvaluationRead>(`/v1/evaluations/${id}/finalize`, {
        method: "POST",
      }),
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setSubmitError(null);

    if (reviewSaved) {
      // Review already recorded — only finalize remains.
      try {
        await finalizeOnly();
      } catch (err) {
        setSubmitError(err);
      } finally {
        setPhase("idle");
      }
      return;
    }

    // Invalid text is never silently dropped or coerced: block and point at it.
    if (!acceptAll) {
      const bad: string[] = [];
      for (const [aspect, values] of Object.entries(draft) as [
        FriesDimension,
        OsdDraft[FriesDimension],
      ][]) {
        for (const key of KEYS) {
          if (isInvalidOsd(values[key])) bad.push(`${aspect.toLowerCase()} ${key}`);
        }
      }
      if (bad.length > 0) {
        setShowInvalid(true);
        setSubmitError(
          new Error(
            `O, S and D must be whole numbers from 0 to 10. Fix: ${bad.join(", ")}.`,
          ),
        );
        const first = Object.entries(draft)
          .flatMap(([aspect, values]) =>
            KEYS.filter((k) => isInvalidOsd(values[k])).map((k) => `${aspect}-${k}`),
          )[0];
        inputRefs.current[first]?.focus();
        return;
      }
    }

    setPhase("review");
    let body: HumanReviewRequest;
    const parsed = (raw: string) => parseOsdInput(raw);
    if (acceptAll) {
      body = { accept_all: true };
    } else if (deterministic) {
      const edits: AspectOSDEdit[] = [];
      for (const [aspect, values] of Object.entries(draft) as [
        FriesDimension,
        OsdDraft[FriesDimension],
      ][]) {
        const O = parsed(values.O);
        const S = parsed(values.S);
        const D = parsed(values.D);
        // O, S, D are each independently optional — an aspect with none of
        // the three entered is simply omitted (not sent as an empty edit).
        if (O === null && S === null && D === null) continue;
        edits.push({ aspect, O: O ?? undefined, S: S ?? undefined, D: D ?? undefined });
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
        ).map(
          ([aspect, values]): AspectOSDEdit => ({
            aspect,
            O: parsed(values.O) ?? undefined,
            S: parsed(values.S) ?? undefined,
            D: parsed(values.D) ?? undefined,
          }),
        ),
      };
    }
    if (notes.trim()) body.notes = notes.trim();
    if (rationale.trim()) body.review_rationale = rationale.trim();
    try {
      await apiFetch<HumanReviewRead>(`/v1/evaluations/${id}/human-review`, {
        method: "POST",
        body,
      });
      setReviewSaved(true);
      await finalizeOnly();
    } catch (err) {
      setSubmitError(err);
    } finally {
      setPhase("idle");
    }
  }

  if (error != null) {
    return (
      <>
        <div role="alert">
          <ErrorNotice error={error} />
        </div>
        <div className="btn-row rv-actions">
          <button type="button" className="btn" onClick={() => setAttempt((n) => n + 1)}>
            Retry
          </button>
          <Link to={`/evaluations/${id}`} className="btn btn-secondary">
            Back to the evaluation
          </Link>
        </div>
      </>
    );
  }
  if (evaluation == null || draft == null) return <Spinner label="Loading review…" />;

  if (finalized?.status === "FINALIZED") {
    const withheld = finalized.final_score == null;
    return (
      <div className="card">
        <h2 ref={finalizedHeadingRef} tabIndex={-1} className="rv-finalized-h">
          Finalized
        </h2>
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
        <div className="btn-row rv-actions" style={{ marginTop: "1rem" }}>
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
        No O/S/D representation found for this evaluation.{" "}
        <Link to={`/evaluations/${id}`}>Back to the evaluation</Link>.
      </div>
    );
  }

  const completeTriples = aspects.filter((a) =>
    KEYS.every((k) => parseOsdInput(draft[a.aspect][k]) !== null),
  ).length;
  const locked = acceptAll || reviewSaved;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Review probe evidence</h1>
          <p className="muted mono rv-id">Evaluation {evaluation.id}</p>
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
        {/* noValidate: native min/max/step bubbles are unreliable for assistive tech
            and unstyled; handleSubmit validates O/S/D itself and names the fields. */}
        <form className="form" onSubmit={handleSubmit} aria-busy={phase !== "idle"} noValidate>
          <label className="radio-row rv-accept">
            <input
              type="checkbox"
              checked={acceptAll}
              disabled={reviewSaved}
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
            <table className="rv-table">
              <caption className="tl-sr-only">
                Probe evidence and human O/S/D entry per aspect
              </caption>
              <thead>
                <tr>
                  <th scope="col">Aspect</th>
                  <th scope="col">Machine-measured evidence</th>
                  <th scope="col" className="num">
                    Recorded O/S/D
                  </th>
                  <th scope="col" className="num">
                    Confidence
                  </th>
                  <th scope="col">O (human)</th>
                  <th scope="col">S (human)</th>
                  <th scope="col">D (human)</th>
                </tr>
              </thead>
              <tbody>
                {aspects.map((aspect) => (
                  <tr key={aspect.aspect}>
                    <th scope="row" className="rv-aspect">
                      {aspect.aspect.toLowerCase()}
                      {aspect.rationale ? (
                        <div className="field-hint">{aspect.rationale}</div>
                      ) : null}
                      {aspect.osd_metadata?.scored_risk_id ? (
                        <div className="field-hint">
                          Named risk: {String(aspect.osd_metadata.scored_risk_id)}
                        </div>
                      ) : null}
                    </th>
                    <td className="muted rv-evidence">
                      {evidenceSummary(aspect.osd_metadata) ?? "No measured evidence recorded"}
                    </td>
                    <td className="num muted">
                      <AgentTriple aspect={aspect} />
                    </td>
                    <td className="num muted">{fmtNumber(aspect.confidence)}</td>
                    {KEYS.map((key) => {
                      const raw = draft[aspect.aspect][key];
                      const invalid = showInvalid && !acceptAll && isInvalidOsd(raw);
                      const errId = `rv-err-${aspect.aspect}-${key}`;
                      return (
                        <td key={key}>
                          <input
                            ref={(el) => {
                              inputRefs.current[`${aspect.aspect}-${key}`] = el;
                            }}
                            type="number"
                            min={0}
                            max={10}
                            step={1}
                            value={raw}
                            placeholder="optional"
                            disabled={locked}
                            aria-label={`${aspect.aspect.toLowerCase()} ${key} (human, 0 to 10, optional)`}
                            aria-invalid={invalid || undefined}
                            aria-describedby={invalid ? errId : undefined}
                            onChange={(e) => setValue(aspect.aspect, key, e.target.value)}
                          />
                          {invalid ? (
                            <span id={errId} className="rv-err">
                              Whole number 0–10
                            </span>
                          ) : null}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!acceptAll ? (
            <p className="rv-progress">
              Complete O/S/D triples entered: {completeTriples} of {aspects.length} listed
              aspects.
            </p>
          ) : null}
          <p className="field-hint">
            Leaving a field blank keeps it missing — TrustLens never assigns a default O,
            S, or D value. An aspect stays incomplete (and FRIES stays withheld) until all
            three are entered for it.
          </p>
          <label>
            Notes (optional)
            <textarea
              rows={2}
              value={notes}
              disabled={reviewSaved}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <label>
            Review rationale (optional)
            <textarea
              rows={3}
              value={rationale}
              disabled={reviewSaved}
              onChange={(e) => setRationale(e.target.value)}
            />
          </label>
          {reviewSaved ? (
            <div className="notice notice-info" role="status">
              Your review was recorded, but finalizing did not complete. Retry finalize — your
              review will not be submitted again.
            </div>
          ) : null}
          <div role="alert">
            <ErrorNotice error={submitError} />
          </div>
          <div className="btn-row rv-actions">
            <button type="submit" className="btn" disabled={phase !== "idle"}>
              {phase === "review"
                ? "Submitting review…"
                : phase === "finalize"
                  ? "Finalizing…"
                  : reviewSaved
                    ? "Retry finalize"
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
