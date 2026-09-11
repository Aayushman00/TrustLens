import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { ModelList, ModelRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Skeleton from "../components/Skeleton";
import { shortRevision } from "../lib/contract";
import { fmtDateTime } from "../lib/format";

export default function ModelsPage() {
  const [items, setItems] = useState<ModelRead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const loadPage = useCallback(async (cursor: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const query = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
      const page = await apiFetch<ModelList>(`/v1/models?limit=25${query}`);
      setItems((prev) => (cursor ? [...prev, ...page.items] : page.items));
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPage(null);
  }, [loadPage]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Models</h1>
          <p className="muted">Registered Hugging Face models — stored and evaluated locally.</p>
        </div>
        <Link to="/models/import" className="btn">
          Import HF model
        </Link>
      </div>
      <ErrorNotice error={error} />
      {items.length === 0 && !loading ? (
        <div className="card">
          <p className="empty">
            Nothing registered yet — <Link to="/models/import">import a model</Link>.
          </p>
        </div>
      ) : (
        <div className="contract-card-grid">
          {items.map((model) => {
            const displayName = model.hf_repo_id.split("/").pop() ?? model.hf_repo_id;
            const isPinned = !!model.revision;
            return (
              <div key={model.id} className="contract-card static">
                <span className="contract-card-title">{displayName}</span>
                <span className="contract-card-sub mono">{model.hf_repo_id}</span>
                <span className="contract-card-chips">
                  <span className={`chip ${isPinned ? "chip-accent" : ""}`}>
                    Revision: {shortRevision(model.revision)}
                  </span>
                  {!isPinned ? <span className="chip">Not reproducible</span> : null}
                </span>
                <span className="contract-card-sub">
                  Imported {fmtDateTime(model.created_at)}
                </span>
                <div className="btn-row" style={{ marginTop: "0.4rem" }}>
                  <Link to={`/models/${model.id}`} className="btn btn-secondary">
                    View model
                  </Link>
                  {isPinned ? (
                    <Link to={`/evaluations/new?modelId=${model.id}`} className="btn">
                      Evaluate
                    </Link>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {loading ? <Skeleton rows={3} height="6.5rem" /> : null}
      {nextCursor && !loading ? (
        <p style={{ marginTop: "1rem" }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void loadPage(nextCursor)}
          >
            Load more
          </button>
        </p>
      ) : null}
    </>
  );
}
