import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import type { ImportHfRequest, ModelRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import { fmtDateTime } from "../lib/format";
import "./ImportModelPage.css";

export default function ImportModelPage() {
  const [reference, setReference] = useState("");
  const [revision, setRevision] = useState("");
  const [imported, setImported] = useState<ModelRead | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const resultRef = useRef<HTMLHeadingElement>(null);

  // Land keyboard / screen-reader focus on the result once an import succeeds.
  useEffect(() => {
    if (imported) resultRef.current?.focus();
  }, [imported]);

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
        <form className="form im-form" onSubmit={handleSubmit} aria-busy={submitting}>
          <label>
            Repo ID or URL
            <input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="distilbert-base-uncased or https://huggingface.co/…"
              required
              inputMode="url"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              aria-describedby="im-ref-hint"
            />
            <span className="field-hint" id="im-ref-hint">
              Example: distilbert-base-uncased-finetuned-sst-2-english
            </span>
          </label>
          <label>
            Revision (optional)
            <input
              value={revision}
              onChange={(e) => setRevision(e.target.value)}
              placeholder="branch / tag / commit"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              aria-describedby="im-rev-hint"
            />
            <span className="field-hint" id="im-rev-hint">
              Leave blank for the default branch; the Hub&rsquo;s resolved commit is recorded as
              the pinned revision. Only pinned models can be evaluated.
            </span>
          </label>
          <div role="alert">
            <ErrorNotice error={error} />
          </div>
          <div className="btn-row im-actions">
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
        <div className="card im-result">
          <h2 ref={resultRef} tabIndex={-1}>
            Imported {imported.hf_repo_id}
          </h2>
          {!imported.revision ? (
            <div className="notice notice-warning">
              No revision was pinned, so this model cannot be evaluated reproducibly. Re-import
              it with an explicit revision before starting an evaluation.
            </div>
          ) : null}
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
          <p className="btn-row im-actions">
            <Link to={`/models/${imported.id}`} className="btn">
              {imported.revision ? "Open model — start an evaluation" : "Open model"}
            </Link>
            <Link to="/models" className="btn btn-secondary">
              All models
            </Link>
          </p>
        </div>
      ) : null}
    </>
  );
}
