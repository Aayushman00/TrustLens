import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationList, ModelList } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Skeleton from "../components/Skeleton";
import StatusBadge from "../components/StatusBadge";
import { modeLabel } from "../components/ModeDisclosure";
import { getEvaluationContract, contractFamilyLabel, shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";
import { countStatuses } from "../lib/overview";
import "./OverviewPage.css";

export default function OverviewPage() {
  const [models, setModels] = useState<ModelList | null>(null);
  const [evaluations, setEvaluations] = useState<EvaluationList | null>(null);
  const [modelsError, setModelsError] = useState<unknown>(null);
  const [evaluationsError, setEvaluationsError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<ModelList>("/v1/models?limit=50")
      .then((page) => {
        if (!cancelled) setModels(page);
      })
      .catch((err) => {
        if (!cancelled) setModelsError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiFetch<EvaluationList>("/v1/evaluations?limit=50")
      .then((page) => {
        if (!cancelled) setEvaluations(page);
      })
      .catch((err) => {
        if (!cancelled) setEvaluationsError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const modelsLoading = models == null && modelsError == null;
  const evaluationsLoading = evaluations == null && evaluationsError == null;
  const counts = evaluations ? countStatuses(evaluations.items) : null;
  const recent = evaluations?.items.slice(0, 6) ?? [];
  const awaitingItems = evaluations?.items.filter((e) => e.status === "AWAITING_REVIEW") ?? [];
  const modelNames = new Map(models?.items.map((m) => [m.id, m.hf_repo_id]) ?? []);
  const truncated = evaluations?.next_cursor != null;
  const val = (n: number | null | undefined) => (n == null ? "—" : n);
  const evalVal = (n: number | undefined) => (evaluationsLoading ? "…" : val(n));

  const segs = counts
    ? [
        { key: "awaiting", label: "Awaiting review", n: counts.awaiting },
        { key: "active", label: "In progress", n: counts.active },
        { key: "final", label: "Finalized", n: counts.finalized },
        { key: "failed", label: "Failed", n: counts.failed },
        ...(counts.other > 0
          ? [{ key: "other", label: "Other / unrecognised", n: counts.other }]
          : []),
      ]
    : [];

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Overview</h1>
          <p className="muted">
            TrustLens Local Engine — evaluations run and store evidence on this machine.
          </p>
        </div>
        <div className="ov-actions">
          <Link to="/evaluations/new" className="btn">
            New evaluation
          </Link>
          <Link to="/models/import" className="btn">
            Import HF model
          </Link>
        </div>
      </div>
      <ErrorNotice error={modelsError} />
      <ErrorNotice error={evaluationsError} />
      {evaluationsLoading && modelsLoading ? <Skeleton rows={4} height="4.6rem" /> : null}

      {evaluations && counts ? (
        <p className="ov-scope">
          Counts cover the {evaluations.items.length} most recent evaluations returned by the API
          {truncated ? " — older evaluations exist and are not counted here." : " (all evaluations)."}
        </p>
      ) : null}

      <section aria-label="Key figures" className="stat-grid ov-kpis">
        <div className="stat-tile">
          <div className="stat-tile-label">Registered models</div>
          <div className="stat-tile-value">{modelsLoading ? "…" : val(models?.items.length)}</div>
          <div className="stat-tile-sub">
            {models?.next_cursor ? "first 50 shown; more exist" : models ? "all shown" : "unavailable"}
          </div>
        </div>
        <div className="stat-tile">
          <div className="stat-tile-label">Evaluations loaded</div>
          <div className="stat-tile-value">{evalVal(counts?.total)}</div>
          <div className="stat-tile-sub">
            {truncated ? "first 50 shown; more exist" : evaluations ? "all shown" : "unavailable"}
          </div>
        </div>
        <Link to="/evaluations" className="stat-tile ov-tile ov-tile--attention">
          <div className="stat-tile-label">Awaiting review</div>
          <div className="stat-tile-value">{evalVal(counts?.awaiting)}</div>
          <div className="stat-tile-sub">human review pending</div>
        </Link>
        <div className="stat-tile">
          <div className="stat-tile-label">In progress</div>
          <div className="stat-tile-value">{evalVal(counts?.active)}</div>
          <div className="stat-tile-sub">pending, running or processing</div>
        </div>
        <div className="stat-tile">
          <div className="stat-tile-label">Finalized</div>
          <div className="stat-tile-value">{evalVal(counts?.finalized)}</div>
          <div className="stat-tile-sub">FRIES may still be withheld</div>
        </div>
        <div className="stat-tile ov-tile--failed">
          <div className="stat-tile-label">Failed</div>
          <div className="stat-tile-value">{evalVal(counts?.failed)}</div>
          <div className="stat-tile-sub">run did not complete</div>
        </div>
      </section>

      {counts && counts.total > 0 ? (
        <div className="card ov-section">
          <h2 id="ov-dist-h">Evaluation status</h2>
          <div className="ov-dist">
            <div
              className="ov-dist-bar"
              role="img"
              aria-labelledby="ov-dist-h"
              aria-describedby="ov-dist-legend"
            >
              {segs
                .filter((g) => g.n > 0)
                .map((g) => (
                  <div
                    key={g.key}
                    className={`ov-dist-seg ov-seg-${g.key}`}
                    style={{ flexGrow: g.n }}
                    title={`${g.label}: ${g.n}`}
                  />
                ))}
            </div>
            <ul className="ov-legend" id="ov-dist-legend">
              {segs.map((g) => (
                <li key={g.key}>
                  <span className={`ov-swatch ov-seg-${g.key}`} aria-hidden="true" />
                  {g.label}
                  <b>
                    {g.n} of {counts.total}
                  </b>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {awaitingItems.length > 0 ? (
        <div className="card ov-section">
          <h2>Needs your review</h2>
          <ul className="ov-attention">
            {awaitingItems.slice(0, 5).map((e) => (
              <li key={e.id}>
                <span>
                  <span className="mono">{e.id.slice(0, 8)}…</span> ·{" "}
                  {modelNames.get(e.model_id) ?? `model #${e.model_id}`}
                  <span className="muted"> · {fmtDateTime(e.created_at)}</span>
                </span>
                <Link
                  to={`/evaluations/${e.id}/review`}
                  aria-label={`Review evaluation ${e.id.slice(0, 8)}`}
                >
                  Review →
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="grid-2 ov-grid">
        <div className="card">
          <h2>Models</h2>
          {modelsLoading ? <Skeleton rows={3} height="1.6rem" /> : null}
          {modelsError != null ? <p className="empty">Models could not be loaded.</p> : null}
          {models != null && models.items.length === 0 ? (
            <p className="empty">
              No models yet — <Link to="/models/import">import one from Hugging Face</Link>.
            </p>
          ) : null}
          {models != null && models.items.length > 0 ? (
            <div className="table-wrap">
              <table>
                <caption className="tl-sr-only">Most recently registered models</caption>
                <thead>
                  <tr>
                    <th scope="col">Repo</th>
                    <th scope="col">Revision</th>
                    <th scope="col">Imported</th>
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
          <p className="ov-card-foot">
            <Link to="/models">All models →</Link>
          </p>
        </div>
        <div className="card">
          <h2>Recent evaluations</h2>
          {evaluationsLoading ? <Skeleton rows={3} height="1.6rem" /> : null}
          {evaluationsError != null ? (
            <p className="empty">Evaluations could not be loaded.</p>
          ) : null}
          {evaluations != null && evaluations.items.length === 0 ? (
            <p className="empty">
              No evaluations yet — <Link to="/evaluations/new">start a new evaluation</Link>.
            </p>
          ) : null}
          {recent.length > 0 ? (
            <div className="table-wrap">
              <table className="ov-recent-table">
                <caption className="tl-sr-only">Most recently created evaluations</caption>
                <thead>
                  <tr>
                    <th scope="col">Evaluation</th>
                    <th scope="col">Model</th>
                    <th scope="col">Contract</th>
                    <th scope="col">Status</th>
                    <th scope="col">Created</th>
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
                        <td>{modelNames.get(evaluation.model_id) ?? `#${evaluation.model_id}`}</td>
                        <td>
                          {contract
                            ? contractFamilyLabel(contract)
                            : modeLabel(evaluation.evaluation_mode)}
                        </td>
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
          <p className="ov-card-foot">
            <Link to="/evaluations">Evaluation history →</Link>
          </p>
        </div>
      </div>
    </>
  );
}
