import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationList, EvaluationRead, EvaluationStatus } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { contractFamilyLabel, getEvaluationContract, shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";

const STATUS_OPTIONS: EvaluationStatus[] = [
  "PENDING",
  "RUNNING",
  "PROBES_COMPLETED",
  "AGENT_COMPLETED",
  "AWAITING_REVIEW",
  "FINALIZED",
  "FAILED",
];

export default function EvaluationsHistoryPage() {
  const [items, setItems] = useState<EvaluationRead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const [statusFilter, setStatusFilter] = useState<EvaluationStatus | "">("");
  const [modelFilter, setModelFilter] = useState("");
  const [familyFilter, setFamilyFilter] = useState<
    "" | "Fairness" | "Robustness" | "Fairness + Robustness" | "Documentation & Governance"
  >("");

  const loadPage = useCallback(
    async (cursor: string | null) => {
      setLoading(true);
      setError(null);
      try {
        const query = new URLSearchParams({ limit: "50" });
        if (statusFilter) query.set("status", statusFilter);
        if (cursor) query.set("cursor", cursor);
        const page = await apiFetch<EvaluationList>(`/v1/evaluations?${query.toString()}`);
        setItems((prev) => (cursor ? [...prev, ...page.items] : page.items));
        setNextCursor(page.next_cursor);
      } catch (err) {
        setError(err);
      } finally {
        setLoading(false);
      }
    },
    [statusFilter],
  );

  useEffect(() => {
    void loadPage(null);
  }, [loadPage]);

  const filtered = useMemo(() => {
    return items.filter((e) => {
      if (modelFilter && !String(e.model_id).includes(modelFilter)) return false;
      if (familyFilter) {
        const contract = getEvaluationContract(e);
        const label = contractFamilyLabel(contract);
        if (label !== familyFilter) return false;
      }
      return true;
    });
  }, [items, modelFilter, familyFilter]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Evaluations</h1>
          <p className="muted">Audit history of every evaluation run locally.</p>
        </div>
      </div>

      <div className="filter-bar">
        <label>
          Status
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as EvaluationStatus | "")}>
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
          <input value={modelFilter} onChange={(e) => setModelFilter(e.target.value)} placeholder="e.g. 12" />
        </label>
        <label>
          Contract family
          <select value={familyFilter} onChange={(e) => setFamilyFilter(e.target.value as typeof familyFilter)}>
            <option value="">All</option>
            <option value="Fairness">Fairness</option>
            <option value="Robustness">Robustness</option>
            <option value="Fairness + Robustness">Fairness + Robustness</option>
            <option value="Documentation & Governance">Documentation &amp; Governance</option>
          </select>
        </label>
      </div>

      <ErrorNotice error={error} />

      <div className="card">
        {filtered.length === 0 && !loading ? (
          <p className="empty">No evaluations match these filters.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Model</th>
                  <th>Revision</th>
                  <th>Contract</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((evaluation) => {
                  const contract = getEvaluationContract(evaluation);
                  return (
                    <tr key={evaluation.id}>
                      <td>
                        <Link to={`/evaluations/${evaluation.id}`} className="mono">
                          {evaluation.id.slice(0, 8)}…
                        </Link>
                      </td>
                      <td>
                        <Link to={`/models/${evaluation.model_id}`}>#{evaluation.model_id}</Link>
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
        )}
        {loading ? <Spinner label="Loading…" /> : null}
        {nextCursor && !loading ? (
          <p>
            <button type="button" className="btn btn-secondary" onClick={() => void loadPage(nextCursor)}>
              Load more
            </button>
          </p>
        ) : null}
      </div>
    </>
  );
}
