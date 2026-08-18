import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { ModelList, ModelRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
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
          <p className="muted">Registered Hugging Face models.</p>
        </div>
        <Link to="/models/import" className="btn">
          Import HF model
        </Link>
      </div>
      <ErrorNotice error={error} />
      <div className="card">
        {items.length === 0 && !loading ? (
          <p className="empty">
            Nothing registered yet — <Link to="/models/import">import a model</Link>.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Repo</th>
                  <th>Revision</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {items.map((model) => (
                  <tr key={model.id}>
                    <td className="muted">{model.id}</td>
                    <td>
                      <Link to={`/models/${model.id}`}>{model.hf_repo_id}</Link>
                    </td>
                    <td className="mono">{model.revision ?? "—"}</td>
                    <td className="muted">{fmtDateTime(model.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {loading ? <Spinner label="Loading…" /> : null}
        {nextCursor && !loading ? (
          <p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void loadPage(nextCursor)}
            >
              Load more
            </button>
          </p>
        ) : null}
      </div>
    </>
  );
}
