/**
 * Dataset intake: paste a URL, fetch it (backend: SSRF-safe streaming fetch +
 * CSV schema sniff via POST /v1/dataset-fetches), and show the resulting
 * column preview. Scope is intake + preview only — column-to-role mapping
 * (text/target/sensitive column selection) is a separate step (Task 3.5).
 */
import { useState, type ChangeEvent, type FormEvent } from "react";

import { apiFetch, apiUpload } from "../api/client";
import type { DatasetContentRead } from "../api/types";
import ErrorNotice from "./ErrorNotice";

export default function DatasetIntakeForm({
  onContentReady,
  onFetchStart,
}: {
  onContentReady: (content: DatasetContentRead) => void;
  /**
   * Called the instant a new fetch attempt begins, before the request
   * resolves either way. Lets the parent drop any dataset/column/label-
   * mapping state from a *previous* attempt immediately — a failed replace
   * must never leave stale content (or a stale ColumnRoleMappingForm)
   * visible, and it must not linger even while the new request is in flight.
   */
  onFetchStart?: () => void;
}) {
  const [url, setUrl] = useState("");
  const [content, setContent] = useState<DatasetContentRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function fetchDataset(e: FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    // Clear any previous preview/content up front -- a fetch that fails
    // (or is still in flight) must never leave a prior dataset's rows,
    // columns, or dropdown options visibly attached, whether that prior
    // fetch succeeded or was itself an already-rejected invalid dataset.
    setContent(null);
    onFetchStart?.();
    try {
      const result = await apiFetch<DatasetContentRead>("/v1/dataset-fetches", {
        method: "POST",
        body: { source_url: trimmed },
      });
      setContent(result);
      onContentReady(result);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function uploadDataset(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file after a failed upload
    if (!file) return;
    setLoading(true);
    setError(null);
    setContent(null);
    onFetchStart?.();
    try {
      const result = await apiUpload<DatasetContentRead>("/v1/dataset-uploads", file);
      setContent(result);
      onContentReady(result);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <ErrorNotice error={error} />
      <form onSubmit={(e) => void fetchDataset(e)} className="form-grid">
        <label>
          Dataset URL
          <input
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/dataset.csv"
          />
        </label>
        <button type="submit" className="btn" disabled={loading || !url.trim()}>
          {loading ? "Fetching…" : "Fetch dataset"}
        </button>
      </form>

      <div className="form-grid" style={{ marginTop: "0.75rem" }}>
        <label>
          Or upload a local CSV
          <input type="file" accept=".csv,text/csv" disabled={loading} onChange={(e) => void uploadDataset(e)} />
        </label>
      </div>

      {content ? (
        <div className="dimension-limitations" style={{ marginTop: "1rem" }}>
          <p>
            {content.row_count} rows, {content.byte_size} bytes, format={content.format}
          </p>
          <ul>
            {content.columns.map((c) => (
              <li key={c.name}>
                {c.name} ({c.inferred_type})
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
