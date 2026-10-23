import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationList, EvaluationRead, ModelRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { modeLabel } from "../components/ModeDisclosure";
import { shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";
import "./ModelDetailPage.css";

type Tab = "overview" | "evaluations" | "card";

const TABS: Tab[] = ["overview", "evaluations", "card"];
const HISTORY_LIMIT = 200;

export default function ModelDetailPage() {
  const { id } = useParams();
  const [model, setModel] = useState<ModelRead | null>(null);
  const [evals, setEvals] = useState<EvaluationList | null>(null);
  const [modelError, setModelError] = useState<unknown>(null);
  const [evalsError, setEvalsError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [attempt, setAttempt] = useState(0);
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    overview: null,
    evaluations: null,
    card: null,
  });

  // Model and evaluation history load independently: a failed history request
  // must not hide a model that loaded fine. Both reset when the route id (or a
  // retry) changes so a previous model's data never lingers under a new URL.
  useEffect(() => {
    let cancelled = false;
    setModel(null);
    setEvals(null);
    setModelError(null);
    setEvalsError(null);
    apiFetch<ModelRead>(`/v1/models/${id}`)
      .then((row) => {
        if (!cancelled) setModel(row);
      })
      .catch((err) => {
        if (!cancelled) setModelError(err);
      });
    apiFetch<EvaluationList>(`/v1/evaluations?limit=${HISTORY_LIMIT}`)
      .then((page) => {
        if (!cancelled) setEvals(page);
      })
      .catch((err) => {
        if (!cancelled) setEvalsError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  const history: EvaluationRead[] | null = useMemo(
    () => (model && evals ? evals.items.filter((e) => e.model_id === model.id) : null),
    [model, evals],
  );
  // The API has no per-model filter, so history is read from the most recent
  // HISTORY_LIMIT evaluations; older runs of this model may not be in view.
  const truncated = evals?.next_cursor != null;

  if (modelError != null) {
    return (
      <>
        <div role="alert">
          <ErrorNotice error={modelError} />
        </div>
        <div className="btn-row md-actions">
          <button type="button" className="btn" onClick={() => setAttempt((n) => n + 1)}>
            Retry
          </button>
          <Link to="/models" className="btn btn-secondary">
            Back to models
          </Link>
        </div>
      </>
    );
  }
  if (model == null) return <Spinner label="Loading model…" />;

  const meta = model.model_metadata ?? {};
  const license = typeof meta.license === "string" ? meta.license : null;
  const cardText = typeof meta.card_text === "string" ? meta.card_text : null;
  const pipelineTag = typeof meta.pipeline_tag === "string" ? meta.pipeline_tag : null;
  const displayName = model.hf_repo_id.split("/").pop() ?? model.hf_repo_id;
  const isPinned = !!model.revision;

  const tabLabel: Record<Tab, string> = {
    overview: "Overview",
    evaluations: history
      ? `Evaluations (${history.length}${truncated ? "+" : ""})`
      : "Evaluations",
    card: "Model Card",
  };

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>, current: Tab) {
    const i = TABS.indexOf(current);
    const next =
      e.key === "ArrowRight"
        ? TABS[(i + 1) % TABS.length]
        : e.key === "ArrowLeft"
          ? TABS[(i + TABS.length - 1) % TABS.length]
          : e.key === "Home"
            ? TABS[0]
            : e.key === "End"
              ? TABS[TABS.length - 1]
              : null;
    if (!next) return;
    e.preventDefault();
    setTab(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <>
      <div className="identity-header">
        <div className="identity-title">
          <h1>{displayName}</h1>
          <span className={`badge ${isPinned ? "badge-yes" : "badge-no"}`}>
            {isPinned ? "Pinned revision" : "Not reproducible — unpinned"}
          </span>
        </div>
        {isPinned ? (
          <Link to={`/evaluations/new?modelId=${model.id}`} className="btn md-btn">
            Evaluate model
          </Link>
        ) : (
          <span className="field-hint">Re-import with a revision to evaluate this model.</span>
        )}
      </div>
      <div className="identity-meta">
        <span className="identity-meta-item md-repo">
          Repository:{" "}
          <a href={`https://huggingface.co/${model.hf_repo_id}`} target="_blank" rel="noreferrer">
            {model.hf_repo_id}
            <span className="tl-sr-only"> (opens in a new tab)</span>
          </a>
        </span>
        <span className="identity-meta-item">
          Revision: <strong className="mono">{shortRevision(model.revision)}</strong>
        </span>
        {pipelineTag ? (
          <span className="identity-meta-item">
            Task: <strong>{pipelineTag.replaceAll("-", " ")}</strong>
          </span>
        ) : null}
        <span className="identity-meta-item">Imported {fmtDateTime(model.created_at)}</span>
      </div>

      <div className="tabs" role="tablist" aria-label="Model sections">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            id={`md-tab-${t}`}
            aria-selected={tab === t}
            aria-controls={`md-panel-${t}`}
            tabIndex={tab === t ? 0 : -1}
            ref={(el) => {
              tabRefs.current[t] = el;
            }}
            className={`tab md-tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
            onKeyDown={(e) => onTabKey(e, t)}
          >
            {tabLabel[t]}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <div className="card" role="tabpanel" id="md-panel-overview" aria-labelledby="md-tab-overview">
          <h2>Details</h2>
          <dl className="kv md-kv">
            <dt>Model ID</dt>
            <dd>{model.id}</dd>
            <dt>Revision</dt>
            <dd className="mono">{model.revision ?? "Unavailable"}</dd>
            <dt>Checksum</dt>
            <dd className="mono">{model.checksum ?? "Not collected"}</dd>
            <dt>License</dt>
            <dd>{license ?? "Not disclosed"}</dd>
          </dl>
        </div>
      ) : null}

      {tab === "evaluations" ? (
        <div className="card" role="tabpanel" id="md-panel-evaluations" aria-labelledby="md-tab-evaluations">
          {evals == null && evalsError == null ? <Spinner label="Loading evaluations…" /> : null}
          {evalsError != null ? (
            <>
              <div role="alert">
                <ErrorNotice error={evalsError} />
              </div>
              <p>
                <button
                  type="button"
                  className="btn btn-secondary md-btn"
                  onClick={() => setAttempt((n) => n + 1)}
                >
                  Retry
                </button>
              </p>
            </>
          ) : null}
          {history != null ? (
            <p className="md-scope">
              {truncated
                ? `Searched the ${HISTORY_LIMIT} most recent evaluations; older runs of this model may not be listed.`
                : "Searched all evaluations."}
            </p>
          ) : null}
          {history != null && history.length === 0 ? (
            <p className="empty">
              {isPinned ? (
                <>
                  {truncated ? "None found yet" : "None yet"} —{" "}
                  <Link to={`/evaluations/new?modelId=${model.id}`}>start one</Link>.
                </>
              ) : (
                "None yet — re-import with a revision to evaluate this model."
              )}
            </p>
          ) : null}
          {history != null && history.length > 0 ? (
            <div className="table-wrap">
              <table className="md-table">
                <caption className="tl-sr-only">Evaluations of this model</caption>
                <thead>
                  <tr>
                    <th scope="col">Evaluation</th>
                    <th scope="col">Mode</th>
                    <th scope="col">Status</th>
                    <th scope="col">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((evaluation) => (
                    <tr key={evaluation.id}>
                      <td>
                        <Link
                          to={`/evaluations/${evaluation.id}`}
                          className="mono"
                          aria-label={`Evaluation ${evaluation.id.slice(0, 8)}`}
                        >
                          {evaluation.id.slice(0, 8)}…
                        </Link>
                      </td>
                      <td>{modeLabel(evaluation.evaluation_mode)}</td>
                      <td>
                        <StatusBadge status={evaluation.status} />
                      </td>
                      <td className="muted">{fmtDateTime(evaluation.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === "card" ? (
        <div className="card" role="tabpanel" id="md-panel-card" aria-labelledby="md-tab-card">
          <h2>Model card disclosures</h2>
          <dl className="kv md-kv">
            <dt>License</dt>
            <dd>{license ?? "Not disclosed"}</dd>
            <dt>Pipeline tag</dt>
            <dd>{pipelineTag ?? "Not disclosed"}</dd>
          </dl>
          <h2 className="md-card-text-h">Card text</h2>
          {cardText ? (
            <pre className="json-view md-card-text">{cardText}</pre>
          ) : (
            <p className="empty">Not collected for this model.</p>
          )}
          <p className="field-hint">
            This is the raw Hugging Face model-card text used by the Integrity, Explainability
            and Safety probes — TrustLens does not rewrite or summarize it.
          </p>
        </div>
      ) : null}
    </>
  );
}
