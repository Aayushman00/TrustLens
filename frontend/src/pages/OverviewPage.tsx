import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationList, ModelList } from "../api/types";
import { ACTIVE_STATUSES } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { modeLabel } from "../components/ModeDisclosure";
import { getEvaluationContract, contractFamilyLabel, shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";

export default function OverviewPage() {
  const [models, setModels] = useState<ModelList | null>(null);
  const [evaluations, setEvaluations] = useState<EvaluationList | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [modelPage, evalPage] = await Promise.all([
          apiFetch<ModelList>("/v1/models?limit=50"),
          apiFetch<EvaluationList>("/v1/evaluations?limit=50"),
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

  const loading = models == null && evaluations == null && error == null;
  const runningCount =
    evaluations?.items.filter((e) => ACTIVE_STATUSES.includes(e.status)).length ?? null;
  const finalizedCount =
    evaluations?.items.filter((e) => e.status === "FINALIZED").length ?? null;
  const recent = evaluations?.items.slice(0, 6) ?? [];

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Overview</h1>
          <p className="muted">
            TrustLens Local Engine — evaluations run and store evidence on this machine.
          </p>
        </div>
        <Link to="/models/import" className="btn">
          Import HF model
        </Link>
      </div>
      <ErrorNotice error={error} />
      {loading ? <Spinner label="Loading…" /> : null}

      {!loading ? (
        <div className="stat-grid">
          <div className="stat-tile">
            <div className="stat-tile-label">Registered models</div>
            <div className="stat-tile-value">{models?.items.length ?? "—"}</div>
            <div className="stat-tile-sub">
              {models?.next_cursor ? "more available" : "all shown"}
            </div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile-label">Evaluations</div>
            <div className="stat-tile-value">{evaluations?.items.length ?? "—"}</div>
            <div className="stat-tile-sub">
              {evaluations?.next_cursor ? "more available" : "all shown"}
            </div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile-label">In progress</div>
            <div className="stat-tile-value">{runningCount ?? "—"}</div>
            <div className="stat-tile-sub">running or awaiting review</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile-label">Finalized</div>
            <div className="stat-tile-value">{finalizedCount ?? "—"}</div>
            <div className="stat-tile-sub">FRIES may still be withheld</div>
          </div>
        </div>
      ) : null}

      <div className="grid-2">
        <div className="card">
          <h2>Models</h2>
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
                    <th>Revision</th>
                    <th>Imported</th>
                  </tr>
                </thead>
                <tbody>
                  {models.items.slice(0, 8).map((model) => (
                    <tr key={model.id}>
                      <td>
                        <Link to={`/models/${model.id}`}>{model.hf_repo_id}</Link>
                      </td>
                      <td className="mono">{shortRevision(model.revision)}</td>
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
          {evaluations != null && evaluations.items.length === 0 ? (
            <p className="empty">No evaluations yet — open a model to start one.</p>
          ) : null}
          {recent.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Evaluation</th>
                    <th>Contract</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((evaluation) => {
                    const contract = getEvaluationContract(evaluation);
                    return (
                      <tr key={evaluation.id}>
                        <td>
                          <Link to={`/evaluations/${evaluation.id}`} className="mono">
                            {evaluation.id.slice(0, 8)}…
                          </Link>
                        </td>
                        <td>{contract ? contractFamilyLabel(contract) : modeLabel(evaluation.evaluation_mode)}</td>
                        <td>
                          <StatusBadge status={evaluation.status} />
                        </td>
                        <td className="muted">{fmtDateTime(evaluation.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
          <p>
            <Link to="/evaluations">Evaluation history →</Link>
          </p>
        </div>
      </div>
    </>
  );
}
