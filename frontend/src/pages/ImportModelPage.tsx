import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { ImportHfRequest, ModelRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import { fmtDateTime } from "../lib/format";

export default function ImportModelPage() {
  const [reference, setReference] = useState("");
  const [revision, setRevision] = useState("");
  const [imported, setImported] = useState<ModelRead | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setImported(null);
    setSubmitting(true);
    const trimmed = reference.trim();
    // Backend wants exactly one of repo_id / url — detect from the input.
    const body: ImportHfRequest = trimmed.startsWith("http")
      ? { url: trimmed }
      : { repo_id: trimmed };
    if (revision.trim()) body.revision = revision.trim();
    try {
      setImported(
        await apiFetch<ModelRead>("/v1/models/import-hf", { method: "POST", body }),
      );
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Import from Hugging Face</h1>
          <p className="muted">
            Resolves the repo via the Hub metadata API and registers (or updates) it.
          </p>
        </div>
      </div>
      <div className="card">
        <form className="form" onSubmit={handleSubmit}>
          <label>
            Repo ID or URL
            <input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="distilbert-base-uncased or https://huggingface.co/…"
              required
            />
            <span className="field-hint">
              Example: distilbert-base-uncased-finetuned-sst-2-english
            </span>
          </label>
          <label>
            Revision (optional)
            <input
              value={revision}
              onChange={(e) => setRevision(e.target.value)}
              placeholder="branch / tag / commit"
            />
          </label>
          <ErrorNotice error={error} />
          <div className="btn-row">
            <button type="submit" className="btn" disabled={submitting || !reference.trim()}>
              {submitting ? "Importing…" : "Import"}
            </button>
            <Link to="/models" className="btn btn-secondary">
              Back to models
            </Link>
          </div>
        </form>
      </div>
      {imported ? (
        <div className="card">
          <h2>Imported</h2>
          <dl className="kv">
            <dt>Model ID</dt>
            <dd>{imported.id}</dd>
            <dt>Repo</dt>
            <dd>{imported.hf_repo_id}</dd>
            <dt>Revision</dt>
            <dd className="mono">{imported.revision ?? "—"}</dd>
            <dt>Created</dt>
            <dd>{fmtDateTime(imported.created_at)}</dd>
          </dl>
          <p className="btn-row">
            <Link to={`/models/${imported.id}`} className="btn">
              Open model — start an evaluation
            </Link>
          </p>
        </div>
      ) : null}
    </>
  );
}
