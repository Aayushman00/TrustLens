import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { ModelList, ModelRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Skeleton from "../components/Skeleton";
import { shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";
import "./ModelsPage.css";

const PAGE_SIZE = 25;

export default function ModelsPage() {
  const [items, setItems] = useState<ModelRead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState("");
  const failedCursor = useRef<string | null>(null);

  const loadPage = useCallback(async (cursor: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const qs = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
      const page = await apiFetch<ModelList>(`/v1/models?limit=${PAGE_SIZE}${qs}`);
      setItems((prev) => (cursor ? [...prev, ...page.items] : page.items));
      setNextCursor(page.next_cursor);
    } catch (err) {
      failedCursor.current = cursor;
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPage(null);
  }, [loadPage]);

  const needle = query.trim().toLowerCase();
  const shown = useMemo(
    () => (needle ? items.filter((m) => m.hf_repo_id.toLowerCase().includes(needle)) : items),
    [items, needle],
  );

  const initialLoad = loading && items.length === 0;
  const summary = initialLoad
    ? "Loading models…"
    : needle
      ? `${shown.length} of ${items.length} loaded models match${nextCursor ? "; older models are not loaded yet" : ""}.`
      : `${items.length} model${items.length === 1 ? "" : "s"} loaded${nextCursor ? "; more available" : " (all)"}.`;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Models</h1>
          <p className="muted">Registered Hugging Face models — stored and evaluated locally.</p>
        </div>
        <Link to="/models/import" className="btn mp-btn">
          Import HF model
        </Link>
      </div>

      <ErrorNotice error={error} />
      {error != null ? (
        <p>
          <button
            type="button"
            className="btn btn-secondary mp-btn"
            onClick={() => void loadPage(failedCursor.current)}
          >
            Retry
          </button>
        </p>
      ) : null}

      {items.length > 0 ? (
        <form className="filter-bar mp-filter" onSubmit={(e) => e.preventDefault()} role="search">
          <label>
            Filter loaded models by repo
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. bert"
            />
          </label>
        </form>
      ) : null}

      <p className="mp-summary" role="status">
        {summary}
      </p>

      {initialLoad ? <Skeleton rows={3} height="6.5rem" /> : null}

      {!loading && error == null && items.length === 0 ? (
        <div className="card">
          <p className="empty">
            No models registered yet — <Link to="/models/import">import one first</Link>.
          </p>
        </div>
      ) : null}

      {items.length > 0 && shown.length === 0 ? (
        <div className="card">
          <p className="empty">
            No loaded model matches “{query.trim()}”
            {nextCursor ? "; load more to search older models" : ""}.{" "}
            <button type="button" className="mp-link" onClick={() => setQuery("")}>
              Clear filter
            </button>
          </p>
        </div>
      ) : null}

      {shown.length > 0 ? (
        <ul className="contract-card-grid mp-grid">
          {shown.map((model) => {
            const displayName = model.hf_repo_id.split("/").pop() ?? model.hf_repo_id;
            const isPinned = !!model.revision;
            return (
              <li key={model.id} className="contract-card static mp-card">
                <h2 className="contract-card-title mp-title">{displayName}</h2>
                <span className="contract-card-sub mono mp-repo">{model.hf_repo_id}</span>
                <span className="contract-card-chips">
                  <span className={`chip ${isPinned ? "chip-accent" : ""}`}>
                    Revision: {shortRevision(model.revision)}
                  </span>
                  {!isPinned ? <span className="chip">Not reproducible</span> : null}
                </span>
                <span className="contract-card-sub">Imported {fmtDateTime(model.created_at)}</span>
                {!isPinned ? (
                  <span className="contract-card-sub">
                    Evaluation needs a pinned revision — re-import with an explicit revision.
                  </span>
                ) : null}
                <div className="btn-row mp-actions">
                  <Link
                    to={`/models/${model.id}`}
                    className="btn btn-secondary"
                    aria-label={`View model ${model.hf_repo_id}`}
                  >
                    View model
                  </Link>
                  {isPinned ? (
                    <Link
                      to={`/evaluations/new?modelId=${model.id}`}
                      className="btn"
                      aria-label={`Evaluate ${model.hf_repo_id}`}
                    >
                      Evaluate
                    </Link>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}

      {loading && items.length > 0 ? <Skeleton rows={1} height="6.5rem" /> : null}
      {nextCursor && !loading ? (
        <p className="mp-more">
          <button
            type="button"
            className="btn btn-secondary mp-btn"
            onClick={() => void loadPage(nextCursor)}
          >
            Load {PAGE_SIZE} more models
          </button>
        </p>
      ) : null}
    </>
  );
}
