import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationList, EvaluationRead, EvaluationStatus } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Skeleton from "../components/Skeleton";
import StatusBadge from "../components/StatusBadge";
import { contractFamilyLabel, getEvaluationContract, shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";
import "./EvaluationsHistoryPage.css";

const STATUS_OPTIONS: EvaluationStatus[] = [
  "PENDING",
  "RUNNING",
  "PROBES_COMPLETED",
  "AGENT_COMPLETED",
  "AWAITING_REVIEW",
  "FINALIZED",
  "FAILED",
];

const PAGE_SIZE = 50;

type Family =
  | ""
  | "Fairness"
  | "Robustness"
  | "Fairness + Robustness"
  | "Documentation & Governance";

export default function EvaluationsHistoryPage() {
  const [items, setItems] = useState<EvaluationRead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const [statusFilter, setStatusFilter] = useState<EvaluationStatus | "">("");
  const [modelFilter, setModelFilter] = useState("");
  const [familyFilter, setFamilyFilter] = useState<Family>("");

  // Only the newest request may write state: a slow response for an old
  // status filter must not overwrite the list for the current one.
  const requestId = useRef(0);
  const failedCursor = useRef<string | null>(null);

  const loadPage = useCallback(
    async (cursor: string | null) => {
      const id = ++requestId.current;
      setLoading(true);
      setError(null);
      if (!cursor) {
        setItems([]);
        setNextCursor(null);
      }
      try {
        const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
        if (statusFilter) query.set("status", statusFilter);
        if (cursor) query.set("cursor", cursor);
        const page = await apiFetch<EvaluationList>(`/v1/evaluations?${query.toString()}`);
        if (id !== requestId.current) return;
        setItems((prev) => (cursor ? [...prev, ...page.items] : page.items));
        setNextCursor(page.next_cursor);
      } catch (err) {
        if (id !== requestId.current) return;
        failedCursor.current = cursor;
        setError(err);
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [statusFilter],
  );

  useEffect(() => {
    void loadPage(null);
  }, [loadPage]);

  const filtered = useMemo(() => {
    return items.filter((e) => {
      if (modelFilter && !String(e.model_id).includes(modelFilter.trim())) return false;
      if (familyFilter) {
        const label = contractFamilyLabel(getEvaluationContract(e));
        if (label !== familyFilter) return false;
      }
      return true;
    });
  }, [items, modelFilter, familyFilter]);

  const anyFilter = statusFilter !== "" || modelFilter !== "" || familyFilter !== "";
  const clientFilter = modelFilter !== "" || familyFilter !== "";
  const clearFilters = () => {
    setStatusFilter("");
    setModelFilter("");
    setFamilyFilter("");
  };

  const summary = loading && items.length === 0
    ? "Loading evaluations…"
    : clientFilter
      ? `${filtered.length} of ${items.length} loaded evaluations match${nextCursor ? "; older evaluations are not loaded yet" : ""}.`
      : `${items.length} evaluation${items.length === 1 ? "" : "s"} loaded${nextCursor ? "; more available" : " (all)"}.`;

  const initialLoad = loading && items.length === 0;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Evaluations</h1>
          <p className="muted">Audit history of every evaluation run locally, newest first.</p>
        </div>
        <Link to="/evaluations/new" className="btn">
          New evaluation
        </Link>
      </div>

      <form className="filter-bar eh-filters" onSubmit={(e) => e.preventDefault()} aria-label="Filter evaluations">
        <label>
          Status
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as EvaluationStatus | "")}
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          Model ID contains
          <input
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
            placeholder="e.g. 12"
            inputMode="numeric"
          />
        </label>
        <label>
          Contract family
          <select value={familyFilter} onChange={(e) => setFamilyFilter(e.target.value as Family)}>
            <option value="">All</option>
            <option value="Fairness">Fairness</option>
            <option value="Robustness">Robustness</option>
            <option value="Fairness + Robustness">Fairness + Robustness</option>
            <option value="Documentation & Governance">Documentation &amp; Governance</option>
          </select>
        </label>
        {anyFilter ? (
          <button type="button" className="btn btn-secondary" onClick={clearFilters}>
            Clear filters
          </button>
        ) : null}
        <p className="eh-hint">
          Status is applied by the server. Model and contract family narrow the rows already loaded.
        </p>
      </form>

      <ErrorNotice error={error} />
      {error != null ? (
        <p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void loadPage(failedCursor.current)}
          >
            Retry
          </button>
        </p>
      ) : null}

      <div className="card">
        <p className="eh-summary" role="status">
          {summary}
        </p>
        {initialLoad ? <Skeleton rows={5} height="2.2rem" /> : null}
        {!initialLoad && filtered.length === 0 && error == null ? (
          <p className="empty">
            {items.length === 0 && !anyFilter ? (
              <>
                No evaluations yet — <Link to="/evaluations/new">start a new evaluation</Link>.
              </>
            ) : (
              <>
                No evaluations match these filters
                {clientFilter && nextCursor ? " among those loaded; load more to search older runs" : ""}.{" "}
                <button type="button" className="eh-link" onClick={clearFilters}>
                  Clear filters
                </button>
              </>
            )}
          </p>
        ) : null}
        {filtered.length > 0 ? (
          <div className="table-wrap">
            <table className="eh-table">
              <caption className="tl-sr-only">Evaluations, newest first</caption>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Model</th>
                  <th scope="col">Revision</th>
                  <th scope="col">Contract</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((evaluation) => {
                  const contract = getEvaluationContract(evaluation);
                  return (
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
                      <td>
                        <Link
                          to={`/models/${evaluation.model_id}`}
                          aria-label={`Model ${evaluation.model_id}`}
                        >
                          #{evaluation.model_id}
                        </Link>
                      </td>
                      <td className="mono">{shortRevision(evaluation.model_revision)}</td>
                      <td>{contractFamilyLabel(contract)}</td>
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
        {loading && items.length > 0 ? <Skeleton rows={2} height="2.2rem" /> : null}
        {nextCursor && !loading ? (
          <p className="eh-more">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void loadPage(nextCursor)}
            >
              Load {PAGE_SIZE} older evaluations
            </button>
          </p>
        ) : null}
      </div>
    </>
  );
}
