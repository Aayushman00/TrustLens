import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { EvaluationMode, LeaderboardEntry, LeaderboardList } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import { modeLabel } from "../components/ModeDisclosure";
import { fmtDateTime, fmtNumber } from "../lib/format";

interface Filters {
  task: string;
  dataset: string;
  mode: EvaluationMode | "";
}

function buildQuery(filters: Filters, cursor: string | null): string {
  const params = new URLSearchParams();
  if (filters.task.trim()) params.set("task", filters.task.trim());
  if (filters.dataset.trim()) params.set("dataset", filters.dataset.trim());
  if (filters.mode) params.set("evaluation_mode", filters.mode);
  params.set("limit", "50");
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

export default function LeaderboardPage() {
  const [taskInput, setTaskInput] = useState("");
  const [datasetInput, setDatasetInput] = useState("");
  const [modeInput, setModeInput] = useState<EvaluationMode | "">("");
  const [applied, setApplied] = useState<Filters>({ task: "", dataset: "", mode: "" });

  const [items, setItems] = useState<LeaderboardEntry[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const loadPage = useCallback(async (filters: Filters, cursor: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await apiFetch<LeaderboardList>(
        `/v1/leaderboard?${buildQuery(filters, cursor)}`,
      );
      setItems((prev) => (cursor ? [...prev, ...page.items] : page.items));
      setNextCursor(page.next_cursor);
      setNote(page.note);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPage(applied, null);
  }, [applied, loadPage]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setApplied({ task: taskInput, dataset: datasetInput, mode: modeInput });
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Leaderboard</h1>
          <p className="muted">
            Only evaluations their owners explicitly published — finalized, with original
            FRIES scores.
          </p>
        </div>
      </div>

      <form className="filters" onSubmit={applyFilters}>
        <label>
          Task
          <input
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            placeholder="exact match"
          />
        </label>
        <label>
          Dataset
          <input
            value={datasetInput}
            onChange={(e) => setDatasetInput(e.target.value)}
            placeholder="exact match"
          />
        </label>
        <label>
          Mode
          <select
            value={modeInput}
            onChange={(e) => setModeInput(e.target.value as EvaluationMode | "")}
          >
            <option value="">All modes</option>
            <option value="AI_ASSISTED">AI-Assisted</option>
            <option value="AI_AUTONOMOUS">AI-Autonomous</option>
          </select>
        </label>
        <button type="submit" className="btn btn-secondary">
          Apply filters
        </button>
      </form>

      {note ? <div className="notice notice-warning">{note}</div> : null}
      <ErrorNotice error={error} />

      <div className="card">
        {items.length === 0 && !loading ? (
          <p className="empty">
            No published evaluations match — publish a finalized evaluation from its
            detail page to list it here.
          </p>
        ) : null}
        {items.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Model</th>
                  <th className="num">FRIES</th>
                  <th>Mode</th>
                  <th>Reviewed</th>
                  <th>Task</th>
                  <th>Dataset</th>
                  <th className="num">Confidence</th>
                  <th>Published</th>
                  <th>Report</th>
                </tr>
              </thead>
              <tbody>
                {items.map((entry, index) => (
                  <tr key={entry.evaluation_id}>
                    <td className="num muted">{index + 1}</td>
                    <td>
                      <Link to={`/evaluations/${entry.evaluation_id}`}>
                        {entry.hf_repo_id}
                      </Link>
                      {entry.model_revision ? (
                        <div className="field-hint mono">{entry.model_revision}</div>
                      ) : null}
                    </td>
                    <td className="num">
                      <strong>{entry.fries_score.toFixed(2)}</strong>
                    </td>
                    <td>{modeLabel(entry.evaluation_mode)}</td>
                    <td>
                      <span className={`badge ${entry.human_reviewed ? "badge-yes" : "badge-no"}`}>
                        {entry.human_reviewed ? "human" : "auto"}
                      </span>
                    </td>
                    <td>{entry.task ?? "—"}</td>
                    <td>{entry.dataset ?? "—"}</td>
                    <td className="num">{fmtNumber(entry.overall_confidence)}</td>
                    <td className="muted">{fmtDateTime(entry.published_at)}</td>
                    <td>
                      {entry.report ? (
                        <Link to={`/reports/${entry.evaluation_id}`}>
                          v{entry.report.version}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {loading ? <Spinner label="Loading…" /> : null}
        {nextCursor && !loading ? (
          <p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void loadPage(applied, nextCursor)}
            >
              Load more
            </button>
          </p>
        ) : null}
      </div>
    </>
  );
}
