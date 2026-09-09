import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationList, EvaluationOptionsRead, EvaluationRead, ModelRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import ContractCatalog from "../components/ContractCatalog";
import DocumentationSourceForm from "../components/DocumentationSourceForm";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { modeLabel } from "../components/ModeDisclosure";
import { shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";

type Tab = "overview" | "evaluations" | "card";

export default function ModelDetailPage() {
  const { id } = useParams();
  const [model, setModel] = useState<ModelRead | null>(null);
  const [history, setHistory] = useState<EvaluationRead[] | null>(null);
  const [options, setOptions] = useState<EvaluationOptionsRead | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [row, evals, opts] = await Promise.all([
          apiFetch<ModelRead>(`/v1/models/${id}`),
          apiFetch<EvaluationList>("/v1/evaluations?limit=200"),
          apiFetch<EvaluationOptionsRead>(`/v1/models/${id}/evaluation-options`),
        ]);
        if (!cancelled) {
          setModel(row);
          setHistory(evals.items.filter((e) => e.model_id === row.id));
          setOptions(opts);
        }
      } catch (err) {
        if (!cancelled) setError(err);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error != null) return <ErrorNotice error={error} />;
  if (model == null) return <Spinner label="Loading model…" />;

  const meta = model.model_metadata ?? {};
  const license = typeof meta.license === "string" ? meta.license : null;
  const cardText = typeof meta.card_text === "string" ? meta.card_text : null;
  const pipelineTag = typeof meta.pipeline_tag === "string" ? meta.pipeline_tag : null;
  const displayName = model.hf_repo_id.split("/").pop() ?? model.hf_repo_id;

  return (
    <>
      <div className="identity-header">
        <div className="identity-title">
          <h1>{displayName}</h1>
          <span className={`badge ${model.revision ? "badge-yes" : "badge-no"}`}>
            {model.revision ? "Available locally" : "No pinned revision"}
          </span>
        </div>
        <Link to={`/evaluations/new?modelId=${model.id}`} className="btn">
          Evaluate model
        </Link>
      </div>
      <div className="identity-meta">
        <span className="identity-meta-item">
          Repository:{" "}
          <a href={`https://huggingface.co/${model.hf_repo_id}`} target="_blank" rel="noreferrer">
            {model.hf_repo_id}
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

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "overview"}
          className={`tab ${tab === "overview" ? "active" : ""}`}
          onClick={() => setTab("overview")}
        >
          Overview
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "evaluations"}
          className={`tab ${tab === "evaluations" ? "active" : ""}`}
          onClick={() => setTab("evaluations")}
        >
          Evaluations ({history?.length ?? 0})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "card"}
          className={`tab ${tab === "card" ? "active" : ""}`}
          onClick={() => setTab("card")}
        >
          Model Card
        </button>
      </div>

      {tab === "overview" ? (
        <>
          <div className="card">
            <h2>Available evaluation contracts</h2>
            <p className="muted">
              These are the only evaluations TrustLens can run model-faithfully for this exact
              model + revision. Nothing here is inferred or substituted.
            </p>
            {options ? <ContractCatalog options={options} /> : <Spinner label="Loading contracts…" />}
          </div>
          <div className="card">
            <h2>Details</h2>
            <dl className="kv">
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
        </>
      ) : null}

      {tab === "evaluations" ? (
        <div className="card">
          {history == null ? <Spinner label="Loading…" /> : null}
          {history != null && history.length === 0 ? (
            <p className="empty">
              None yet — <Link to={`/evaluations/new?modelId=${model.id}`}>start one</Link>.
            </p>
          ) : null}
          {history != null && history.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Evaluation</th>
                    <th>Mode</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((evaluation) => (
                    <tr key={evaluation.id}>
                      <td>
                        <Link to={`/evaluations/${evaluation.id}`} className="mono">
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
        <div className="card">
          <h2>Model card disclosures</h2>
          <dl className="kv">
            <dt>License</dt>
            <dd>{license ?? "Not disclosed"}</dd>
            <dt>Pipeline tag</dt>
            <dd>{pipelineTag ?? "Not disclosed"}</dd>
          </dl>
          <h2 style={{ marginTop: "1.2rem" }}>Card text</h2>
          {cardText ? (
            <pre className="json-view">{cardText}</pre>
          ) : (
            <p className="empty">Not collected for this model.</p>
          )}
          <p className="field-hint">
            This is the raw Hugging Face model-card text used by the Integrity, Explainability
            and Safety probes — TrustLens does not rewrite or summarize it.
          </p>
        </div>
      ) : null}

      {tab === "card" ? (
        <div className="card">
          <h2>Documentation sources</h2>
          <p className="muted">
            The pinned-revision Hugging Face card evidence (auto-recorded at import) plus any
            documentation you attach — papers, safety cards, eval reports.
          </p>
          <DocumentationSourceForm modelId={model.id} />
        </div>
      ) : null}
    </>
  );
}
