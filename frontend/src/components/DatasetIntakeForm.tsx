/**
 * Dataset intake: paste a URL, fetch it (backend: SSRF-safe streaming fetch +
 * CSV schema sniff via POST /v1/dataset-fetches), and show the resulting
 * column preview. Scope is intake + preview only — column-to-role mapping
 * (text/target/sensitive column selection) is a separate step (Task 3.5).
 */
import { useState, type FormEvent } from "react";

import { apiFetch } from "../api/client";
import type { DatasetContentRead } from "../api/types";
import ErrorNotice from "./ErrorNotice";

export default function DatasetIntakeForm({
  onContentReady,
}: {
  onContentReady: (content: DatasetContentRead) => void;
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
