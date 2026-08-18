import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import { ACTIVE_STATUSES, type EvaluationRead } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ErrorNotice from "../components/ErrorNotice";
import ModeDisclosureBanner, { modeLabel } from "../components/ModeDisclosure";
import ScoreBars from "../components/ScoreBars";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { fmtDateTime, fmtNumber } from "../lib/format";

const POLL_MS = 2500;

export default function EvaluationDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [evaluation, setEvaluation] = useState<EvaluationRead | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [acting, setActing] = useState(false);
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

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      const row = await load();
      if (!cancelled && row && ACTIVE_STATUSES.includes(row.status)) {
        timerRef.current = window.setTimeout(tick, POLL_MS);
      }
    }
    void tick();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [load]);

  async function publishAction(action: "publish" | "unpublish") {
    setActionError(null);
    setActing(true);
    try {
      const row = await apiFetch<EvaluationRead>(`/v1/evaluations/${id}/${action}`, {
        method: "POST",
      });
      // The action returns the detail read — but re-fetch to keep nested blocks fresh.
      setEvaluation(row);
      await load();
    } catch (err) {
      setActionError(err);
    } finally {
      setActing(false);
    }
  }

  if (error != null && evaluation == null) return <ErrorNotice error={error} />;
  if (evaluation == null) return <Spinner label="Loading evaluation…" />;

  const isActive = ACTIVE_STATUSES.includes(evaluation.status);
  const isReviewerRole = user?.role === "reviewer" || user?.role === "admin";
  const canPublish =
    user != null && (user.role === "admin" || evaluation.created_by === user.id);
  const awaitingAssistedReview =
    evaluation.evaluation_mode === "AI_ASSISTED" &&
    evaluation.status === "AWAITING_REVIEW";

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="mono">Evaluation {evaluation.id.slice(0, 8)}…</h1>
          <p className="muted">
            {modeLabel(evaluation.evaluation_mode)} ·{" "}
            <Link to={`/models/${evaluation.model_id}`}>Model #{evaluation.model_id}</Link>{" "}
            · created {fmtDateTime(evaluation.created_at)}
          </p>
        </div>
        <div className="btn-row">
          <StatusBadge status={evaluation.status} />
          <span className={`badge ${evaluation.is_published ? "badge-published" : "badge-private"}`}>
            {evaluation.is_published ? "Published" : "Private"}
          </span>
        </div>
      </div>

      {evaluation.mode_disclosure ? (
        <ModeDisclosureBanner disclosure={evaluation.mode_disclosure} />
      ) : null}

      {isActive ? (
        <div className="card">
          <div className="progress-line">
            <Spinner />
            <span>
              Running — probes {evaluation.probe_progress?.completed ?? 0}/
              {evaluation.probe_progress?.total ?? 5} complete. Refreshing every few
              seconds…
            </span>
          </div>
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
                The agent O/S/D suggestion below is <strong>PROPOSED</strong> — accept or
                edit it to finalize this evaluation.
              </p>
              <Link to={`/evaluations/${evaluation.id}/review`} className="btn">
                Review agent O/S/D
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

      {evaluation.final_score ? (
        <div className="card">
          <h2>Final FRIES score</h2>
          <div className="fries-hero">
            <span className="fries-value">
              {evaluation.final_score.fries_score.toFixed(2)}
            </span>
            <span className="fries-label">
              original FRIES (0–10) ·{" "}
              {evaluation.final_score.human_reviewed
                ? "human-reviewed"
                : "not human-reviewed"}{" "}
              · confidence {fmtNumber(evaluation.final_score.overall_confidence)}
            </span>
          </div>
          <ScoreBars scores={evaluation.final_score.dimension_scores} />
          {evaluation.final_score.disclaimer ? (
            <p className="muted">{evaluation.final_score.disclaimer}</p>
          ) : null}
          {evaluation.status === "FINALIZED" ? (
            <div className="btn-row" style={{ marginTop: "1rem" }}>
              <Link to={`/reports/${evaluation.id}`} className="btn btn-secondary">
                View report
              </Link>
              {canPublish ? (
                evaluation.is_published ? (
                  <button
                    type="button"
                    className="btn btn-danger"
                    disabled={acting}
                    onClick={() => void publishAction("unpublish")}
                  >
                    {acting ? "Working…" : "Unpublish"}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn"
                    disabled={acting}
                    onClick={() => void publishAction("publish")}
                  >
                    {acting ? "Working…" : "Publish to leaderboard"}
                  </button>
                )
              ) : (
                <span className="field-hint">
                  Only the evaluation owner or an admin can publish.
                </span>
              )}
              {evaluation.is_published ? (
                <Link to="/leaderboard">See it on the leaderboard →</Link>
              ) : null}
            </div>
          ) : null}
          <ErrorNotice error={actionError} />
          {evaluation.published_at ? (
            <p className="field-hint">Published {fmtDateTime(evaluation.published_at)}</p>
          ) : null}
        </div>
      ) : null}

      {evaluation.osd_agent ? (
        <div className="card">
          <h2>Agent O/S/D suggestion</h2>
          <div className="notice notice-warning">
            <strong>PROPOSED — not ground truth.</strong>{" "}
            {evaluation.osd_agent.ai_suggestion.note}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Aspect</th>
                  <th className="num">O</th>
                  <th className="num">S</th>
                  <th className="num">D</th>
                  <th className="num">Confidence</th>
                  <th>Rationale</th>
                </tr>
              </thead>
              <tbody>
                {evaluation.osd_agent.ai_suggestion.aspects.map((aspect) => (
                  <tr key={aspect.aspect}>
                    <td>{aspect.aspect.toLowerCase()}</td>
                    <td className="num">{aspect.O}</td>
                    <td className="num">{aspect.S}</td>
                    <td className="num">{aspect.D}</td>
                    <td className="num">{fmtNumber(aspect.confidence)}</td>
                    <td className="muted">{aspect.rationale ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="field-hint">
            Agent confidence: {fmtNumber(evaluation.osd_agent.ai_confidence)} · status:{" "}
            {evaluation.osd_agent.methodology_status}
          </p>
        </div>
      ) : null}

      {evaluation.confidence_summary ? (
        <div className="card">
          <h2>Evidence confidence</h2>
          <p>
            Overall <strong>{fmtNumber(evaluation.confidence_summary.overall)}</strong>{" "}
            <span className="muted">({evaluation.confidence_summary.method})</span>
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Dimension</th>
                  <th className="num">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(evaluation.confidence_summary.by_dimension).map(
                  ([dimension, value]) => (
                    <tr key={dimension}>
                      <td>{dimension.toLowerCase()}</td>
                      <td className="num">{fmtNumber(value)}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          <p className="field-hint">{evaluation.confidence_summary.note}</p>
        </div>
      ) : null}

      {evaluation.human_review ? (
        <div className="card">
          <h2>Human review</h2>
          <dl className="kv">
            <dt>Reviewer</dt>
            <dd>#{evaluation.human_review.reviewer_id}</dd>
            <dt>Decision</dt>
            <dd>
              {evaluation.human_review.accept_all
                ? "Accepted agent suggestion as-is"
                : "Edited agent suggestion"}
              {evaluation.human_review.human_changed ? " (values changed)" : ""}
            </dd>
            <dt>Notes</dt>
            <dd>{evaluation.human_review.notes ?? "—"}</dd>
            <dt>Rationale</dt>
            <dd>{evaluation.human_review.review_rationale ?? "—"}</dd>
            <dt>Reviewed at</dt>
            <dd>{fmtDateTime(evaluation.human_review.created_at)}</dd>
          </dl>
        </div>
      ) : null}

      <div className="card">
        <h2>Context</h2>
        <dl className="kv">
          <dt>Task</dt>
          <dd>{evaluation.task ?? "—"}</dd>
          <dt>Dataset</dt>
          <dd>{evaluation.dataset ?? "—"}</dd>
          <dt>Config</dt>
          <dd>{evaluation.config ?? "—"}</dd>
          <dt>Model revision</dt>
          <dd className="mono">{evaluation.model_revision ?? "—"}</dd>
          <dt>TrustLens version</dt>
          <dd>{evaluation.trustlens_version ?? "—"}</dd>
          <dt>Evaluation ID</dt>
          <dd className="mono">{evaluation.id}</dd>
        </dl>
      </div>
    </>
  );
}
