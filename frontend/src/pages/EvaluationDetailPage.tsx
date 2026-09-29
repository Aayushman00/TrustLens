import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import {
  ACTIVE_STATUSES,
  FRIES_DIMENSIONS,
  type EvaluationEventList,
  type EvaluationEventRead,
  type EvaluationRead,
  type FriesDimension,
} from "../api/types";
import DimensionCard from "../components/DimensionCard";
import DimensionProgressChip from "../components/DimensionProgressChip";
import ErrorNotice from "../components/ErrorNotice";
import EvaluationTimeline from "../components/EvaluationTimeline";
import EvidenceDossier from "../components/EvidenceDossier";
import { MockBanner } from "../components/MockTag";
import ModeDisclosureBanner, { engineLabel } from "../components/ModeDisclosure";
import ScoreBars from "../components/ScoreBars";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { contractFamilyLabel, getEvaluationContract, shortRevision } from "../lib/contract";
import { fmtDateTime, fmtNumber, fmtOsd } from "../lib/format";
import { mockExecutionTelemetry } from "../mocks/telemetry";

// Short enough to actually catch a fast local run mid-flight: 5 probes on a
// small model + tiny dataset can finish in a couple of seconds end-to-end
// (confirmed by measurement), so a slower interval polls through the whole
// run without ever landing between two probe commits. Polling only happens
// while the evaluation is in an ACTIVE_STATUSES state (see below), so this
// only costs extra requests during an actual run on this single-user local
// instance, never once it's finished.
const POLL_MS = 500;

// Plain-language gist of what each probe checks — for someone with no ML
// background watching the progress strip, not a technical spec.
const PROBE_GIST: Record<FriesDimension, string> = {
  FAIRNESS: "Checking whether the model treats different groups in your data evenly",
  ROBUSTNESS: "Testing whether small wording changes trick the model",
  INTEGRITY: "Checking the model's identity and files for signs of tampering",
  EXPLAINABILITY: "Checking how well the model's documentation explains its own decisions",
  SAFETY: "Checking the model's documentation for safety warnings and known risks",
};

function currentStageGist(
  status: EvaluationRead["status"],
  currentDim: FriesDimension | undefined,
): string {
  if (status === "PENDING") return "Getting ready to check the model…";
  if (status === "RUNNING") {
    return currentDim ? PROBE_GIST[currentDim] : "Running checks on the model…";
  }
  if (status === "PROBES_COMPLETED") return "Checks finished — putting the findings into a draft assessment";
  if (status === "AGENT_COMPLETED") return "Draft assessment ready — preparing it for review";
  return "";
}

export default function EvaluationDetailPage() {
  const { id } = useParams();
  const [evaluation, setEvaluation] = useState<EvaluationRead | null>(null);
  const [events, setEvents] = useState<EvaluationEventRead[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const timerRef = useRef<number | undefined>(undefined);

  const load = useCallback(async (): Promise<EvaluationRead | null> => {
    try {
      const row = await apiFetch<EvaluationRead>(`/v1/evaluations/${id}`);
      setEvaluation(row);
      setError(null);
      return row;
    } catch (err) {
      setError(err);
      return null;
    }
  }, [id]);

  const loadEvents = useCallback(async (): Promise<void> => {
    try {
      const list = await apiFetch<EvaluationEventList>(`/v1/evaluations/${id}/events`);
      setEvents(list.items);
    } catch {
      // Non-critical: the timeline is supplementary audit evidence, not
      // required for the rest of the page to function.
      setEvents((prev) => prev ?? []);
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      const row = await load();
      await loadEvents();
      if (!cancelled && row && ACTIVE_STATUSES.includes(row.status)) {
        timerRef.current = window.setTimeout(tick, POLL_MS);
      }
    }
    void tick();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [load, loadEvents]);

  if (error != null && evaluation == null) return <ErrorNotice error={error} />;
  if (evaluation == null) return <Spinner label="Loading evaluation…" />;

  const isActive = ACTIVE_STATUSES.includes(evaluation.status);
  // Single-user local instance — no RBAC/ownership gate on review.
  const isReviewerRole = true;
  const awaitingAssistedReview =
    evaluation.evaluation_mode === "AI_ASSISTED" &&
    evaluation.status === "AWAITING_REVIEW";
  const contract = getEvaluationContract(evaluation);
  const probesByDim = new Map((evaluation.probes ?? []).map((p) => [p.dimension, p]));
  const finished = evaluation.status === "FINALIZED" || evaluation.status === "FAILED";
  const friesWithheld = evaluation.status === "FINALIZED" && evaluation.final_score == null;
  const t = mockExecutionTelemetry;
  const exec = evaluation.execution_metadata ?? null;
  // The only two probes that ever run local inference are Fairness and
  // Robustness (see _INFERENCE_CAPABLE_DIMENSIONS in evaluate_pipeline.py).
  // Until at least one of them has actually finished, a null
  // execution_metadata means "not decided yet", not "never happened" —
  // those are different facts and deserve different copy.
  const inferenceCapableProbeRan = probesByDim.has("FAIRNESS") || probesByDim.has("ROBUSTNESS");
  const gpuStatus = exec
    ? exec.execution_device === "cuda"
      ? `GPU (${exec.gpu_name ?? "CUDA device"})`
      : `CPU${exec.fallback_reason ? ` — ${exec.fallback_reason}` : ""}`
    : isActive && !inferenceCapableProbeRan
      ? "Not yet known — determined once the Fairness or Robustness check runs"
      : "Not recorded (no probe ran local inference in this run)";
  const pct = isActive
    ? Math.round(((evaluation.probe_progress?.completed ?? 0) / (evaluation.probe_progress?.total ?? 5)) * 100)
    : 100;
  // The probe currently executing, if any — only meaningful while RUNNING;
  // once PROBES_COMPLETED is reached every dimension has a row (even
  // NOT_APPLICABLE ones persist a row), so this is naturally undefined then.
  const currentDim =
    evaluation.status === "RUNNING"
      ? FRIES_DIMENSIONS.find((dim) => !probesByDim.has(dim))
      : undefined;
  const stageGist = currentStageGist(evaluation.status, currentDim);

  return (
    <>
      <div className="identity-header">
        <div className="identity-title">
          <h1>Evaluation</h1>
          <StatusBadge status={evaluation.status} />
          <span className={`badge ${evaluation.is_published ? "badge-published" : "badge-private"}`}>
            {evaluation.is_published ? "Published" : "Private"}
          </span>
        </div>
      </div>
      <div className="identity-meta">
        <span className="identity-meta-item">
          Model:{" "}
          <Link to={`/models/${evaluation.model_id}`}>
            <strong>{contract?.model_ref ?? `#${evaluation.model_id}`}</strong>
          </Link>
        </span>
        <span className="identity-meta-item">
          Evaluated locally · Revision:{" "}
          <strong className="mono">{shortRevision(evaluation.model_revision)}</strong>
        </span>
        {contract ? (
          <span className="identity-meta-item">
            Contract: <strong>{contractFamilyLabel(contract)}</strong>
          </span>
        ) : null}
        <span className="identity-meta-item">Created {fmtDateTime(evaluation.created_at)}</span>
      </div>

      {evaluation.mode_disclosure ? (
        <ModeDisclosureBanner disclosure={evaluation.mode_disclosure} />
      ) : null}

      {isActive ? (
        <div className="execution-card">
          <div className="progress-line">
            <Spinner />
            <strong>Running locally — {evaluation.probe_progress?.completed ?? 0}/{evaluation.probe_progress?.total ?? 5} dimensions complete</strong>
          </div>
          <p className="muted stage-gist" aria-live="polite" style={{ fontSize: "0.85rem", margin: "0.3rem 0 0" }}>
            {stageGist}
          </p>
          <div className="execution-progress-track" role="status" aria-live="polite">
            <div className="execution-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="dimension-status-strip">
            {FRIES_DIMENSIONS.map((dim) => {
              const p = probesByDim.get(dim);
              const state = p
                ? p.status === "NOT_APPLICABLE"
                  ? "not-applicable"
                  : "done"
                : dim === currentDim
                  ? "running"
                  : "pending";
              return (
                <DimensionProgressChip
                  key={dim}
                  label={dim.charAt(0) + dim.slice(1).toLowerCase()}
                  state={state}
                />
              );
            })}
          </div>
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.6rem" }}>
            Execution device: <strong>{gpuStatus}</strong>
          </p>
          <details style={{ marginTop: "0.9rem" }}>
            <summary style={{ cursor: "pointer", fontSize: "0.82rem", color: "var(--muted)" }}>
              Execution telemetry (technical detail)
            </summary>
            <div style={{ marginTop: "0.6rem" }}>
              <MockBanner>
                Sample batch/timing telemetry shown for layout only — TrustLens does not yet
                record per-batch timing. The execution device above is real.
              </MockBanner>
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                Batch {t.currentBatch}/{t.totalBatches} · {t.msPerSample} ms/sample
              </p>
            </div>
          </details>
        </div>
      ) : null}

      {evaluation.status === "FAILED" ? (
        <div className="notice notice-error">
          This evaluation failed. Create a new one from the model page.
        </div>
      ) : null}

      {awaitingAssistedReview ? (
        <div className="card">
          <h2>Human review required</h2>
          {isReviewerRole ? (
            <>
              <p>
                Probe evidence is ready for human review. O/S/D are a
                representation of that evidence, not LLM scores. Accept or edit
                to finalize.
              </p>
              <Link to={`/evaluations/${evaluation.id}/review`} className="btn">
                Review O/S/D
              </Link>
            </>
          ) : (
            <p className="muted">
              Waiting for a reviewer — accounts with the reviewer or admin role see a
              review button here.
            </p>
          )}
        </div>
      ) : null}

      {finished ? (
        <div className={`fries-overall-card ${friesWithheld ? "withheld" : ""}`}>
          <div className="fries-overall-title">Overall FRIES assessment</div>
          {friesWithheld ? (
            <>
              <div className="fries-withheld-rows">
                <div>
                  <div className="fries-withheld-row-label">Measured evidence</div>
                  <div className="fries-withheld-row-value">Available</div>
                </div>
                <div>
                  <div className="fries-withheld-row-label">O/S/D synthesis</div>
                  <div className="fries-withheld-row-value">Unavailable</div>
                </div>
                <div>
                  <div className="fries-withheld-row-label">Final FRIES</div>
                  <div className="fries-withheld-row-value">Withheld</div>
                </div>
              </div>
              <p>
                TrustLens has measured the available dimensions, but the required O/S/D inputs
                for a final FRIES synthesis are not available in this evaluation mode. This is
                not a low trust score — it means no synthesized score exists yet.
              </p>
            </>
          ) : evaluation.final_score ? (
            <>
              <div className="fries-hero">
                <span className="fries-value">{evaluation.final_score.fries_score.toFixed(2)}</span>
                <span className="fries-label">
                  original FRIES (0–10) ·{" "}
                  {evaluation.final_score.human_reviewed ? "human-reviewed" : "not human-reviewed"}
                </span>
              </div>
              <ScoreBars scores={evaluation.final_score.dimension_scores} />
              {evaluation.final_score.disclaimer ? (
                <p className="muted">{evaluation.final_score.disclaimer}</p>
              ) : null}
              <div className="btn-row" style={{ marginTop: "1rem" }}>
                <Link to={`/reports/${evaluation.id}`} className="btn btn-secondary">
                  View report
                </Link>
              </div>
            </>
          ) : (
            <p className="muted">Evaluation failed — no FRIES assessment is available.</p>
          )}
        </div>
      ) : null}

      <h2>Dimensions</h2>
      <div className="dimension-grid">
        {FRIES_DIMENSIONS.map((dim: FriesDimension) => (
          <DimensionCard
            key={dim}
            dimension={dim}
            probe={probesByDim.get(dim)}
            onViewEvidence={() => {
              document.getElementById(`dossier-${dim}`)?.setAttribute("open", "true");
              document.getElementById(`dossier-${dim}`)?.scrollIntoView({ behavior: "smooth" });
            }}
          />
        ))}
      </div>

      {evaluation.osd_agent ? (
        <div className="card">
          <h2>
            {evaluation.osd_agent.ai_suggestion.assessment_engine === "legacy_heuristic"
              ? "Legacy heuristic O/S/D (proposed)"
              : "Deterministic O/S/D representation"}
          </h2>
          <div className="notice notice-warning">{evaluation.osd_agent.ai_suggestion.note}</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Aspect</th>
                  <th className="num">O (Occurrence)</th>
                  <th className="num">S (Severity)</th>
                  <th className="num">D (Detection)</th>
                  <th className="num">Evidence strength</th>
                  <th>Rationale</th>
                </tr>
              </thead>
              <tbody>
                {evaluation.osd_agent.ai_suggestion.aspects.map((aspect) => (
                  <tr key={aspect.aspect}>
                    <td>{aspect.aspect.toLowerCase()}</td>
                    <td className="num">{fmtOsd(aspect.O)}</td>
                    <td className="num">{fmtOsd(aspect.S)}</td>
                    <td className="num">{fmtOsd(aspect.D)}</td>
                    <td className="num">{fmtNumber(aspect.confidence)}</td>
                    <td className="muted">{aspect.rationale ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="field-hint">
            Engine: {engineLabel(evaluation.osd_agent.ai_suggestion.assessment_engine)} · status:{" "}
            {evaluation.osd_agent.methodology_status}
            {evaluation.osd_agent.ai_suggestion.scoring_withheld ? " · FRIES withheld" : ""}
          </p>
        </div>
      ) : null}

      <h2>Evidence dossier</h2>
      <p className="muted">
        Full detail behind each dimension card — model/dataset identity, execution, raw evidence.
      </p>
      {FRIES_DIMENSIONS.map((dim) => (
        <EvidenceDossier key={dim} id={`dossier-${dim}`} dimension={dim} probe={probesByDim.get(dim)} />
      ))}

      {evaluation.human_review ? (
        <div className="card">
          <h2>Human review</h2>
          <dl className="kv">
            <dt>Decision</dt>
            <dd>
              {evaluation.human_review.accept_all ? "Accepted recorded O/S/D as-is" : "Edited recorded O/S/D"}
              {evaluation.human_review.human_changed ? " (values changed)" : ""}
            </dd>
            <dt>Notes</dt>
            <dd>{evaluation.human_review.notes ?? "—"}</dd>
            <dt>Reviewed at</dt>
            <dd>{fmtDateTime(evaluation.human_review.created_at)}</dd>
          </dl>
        </div>
      ) : null}

      <div className="card">
        <h2>Context</h2>
        <dl className="kv">
          <dt>Evaluation contract</dt>
          <dd>{contractFamilyLabel(contract)}</dd>
          <dt>Dataset</dt>
          <dd>{evaluation.dataset ?? "—"}</dd>
          <dt>Model revision</dt>
          <dd className="mono">{evaluation.model_revision ?? "—"}</dd>
          <dt>Local execution device</dt>
          <dd>
            {gpuStatus}
            {exec?.inference_backend ? ` · backend: ${exec.inference_backend}` : ""}
          </dd>
          <dt>TrustLens version</dt>
          <dd>{evaluation.trustlens_version ?? "—"}</dd>
          <dt>Evaluation ID</dt>
          <dd className="mono">{evaluation.id}</dd>
        </dl>
      </div>

      <div className="card">
        <h2>Evaluation timeline</h2>
        <p className="muted">
          Append-only audit trail of when each already-decided lifecycle step happened.
          This is evidence of what occurred — not a separate status; the evaluation's
          own status, probes, O/S/D, and FRIES above remain authoritative.
        </p>
        <EvaluationTimeline events={events} live={isActive} />
      </div>
    </>
  );
}

