import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationList, ModelList } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { modeLabel } from "../components/ModeDisclosure";
import { fmtDateTime } from "../lib/format";

export default function DashboardPage() {
  const [models, setModels] = useState<ModelList | null>(null);
  const [evaluations, setEvaluations] = useState<EvaluationList | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [modelPage, evalPage] = await Promise.all([
          apiFetch<ModelList>("/v1/models?limit=8"),
          apiFetch<EvaluationList>("/v1/evaluations?limit=10"),
        ]);
        if (!cancelled) {
          setModels(modelPage);
          setEvaluations(evalPage);
        }
      } catch (err) {
        if (!cancelled) setError(err);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">
            Import a model, run an evaluation, review, report, publish.
          </p>
        </div>
        <Link to="/models/import" className="btn">
          Import HF model
        </Link>
      </div>
      <ErrorNotice error={error} />
      <div className="grid-2">
        <div className="card">
          <h2>Models</h2>
          {models == null && error == null ? <Spinner label="Loading…" /> : null}
          {models != null && models.items.length === 0 ? (
            <p className="empty">
              No models yet — <Link to="/models/import">import one from Hugging Face</Link>.
            </p>
          ) : null}
          {models != null && models.items.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Repo</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {models.items.map((model) => (
                    <tr key={model.id}>
                      <td>
                        <Link to={`/models/${model.id}`}>{model.hf_repo_id}</Link>
                      </td>
                      <td className="muted">{fmtDateTime(model.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <p>
            <Link to="/models">All models →</Link>
          </p>
        </div>
        <div className="card">
          <h2>Recent evaluations</h2>
          {evaluations == null && error == null ? <Spinner label="Loading…" /> : null}
          {evaluations != null && evaluations.items.length === 0 ? (
            <p className="empty">No evaluations yet — open a model to start one.</p>
          ) : null}
          {evaluations != null && evaluations.items.length > 0 ? (
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
                  {evaluations.items.map((evaluation) => (
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
      </div>
    </>
  );
}
