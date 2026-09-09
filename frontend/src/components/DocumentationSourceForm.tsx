/**
 * Documentation sources panel for a model: lists the auto-recorded
 * pinned-revision Hugging Face card evidence plus any user-supplied
 * documentation pointers, and lets any authenticated user attach one.
 *
 * User-supplied URLs are never fetched/hashed server-side (no SSRF guard for
 * arbitrary hosts, unlike the allowlisted HF Hub host) — retrieval_status is
 * always "not_applicable" for these rows, shown as such, never faked.
 */
import { useEffect, useState, type FormEvent } from "react";

import { apiFetch } from "../api/client";
import type { DocumentationSourceList, DocumentationSourceRead, DocumentationType } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ErrorNotice from "./ErrorNotice";

const DOC_TYPES: { value: DocumentationType; label: string }[] = [
  { value: "model_card", label: "Model card" },
  { value: "readme", label: "README" },
  { value: "technical_report", label: "Technical report" },
  { value: "safety_system_card", label: "Safety / system card" },
  { value: "evaluation_report", label: "Evaluation report" },
  { value: "research_paper", label: "Research paper" },
  { value: "other", label: "Other" },
];

function SourceRow({
  source,
  canDelete,
  onDelete,
}: {
  source: DocumentationSourceRead;
  canDelete: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="dimension-row" style={{ alignItems: "flex-start" }}>
      <span className="dimension-row-label">
        {source.source_kind === "huggingface_hub" ? "Hugging Face card (pinned)" : source.documentation_type.replaceAll("_", " ")}
      </span>
      <span className="dimension-row-value">
        {source.url ? (
          <a href={source.url} target="_blank" rel="noreferrer" className="mono">
            {source.title ?? source.url}
          </a>
        ) : (
          source.title ?? "—"
        )}
        {source.documentation_revision ? (
          <>
            {" "}
            · revision <span className="mono">{source.documentation_revision.slice(0, 8)}</span>
          </>
        ) : null}
        {" "}
        · {source.retrieval_status}
        {source.description ? <div className="muted">{source.description}</div> : null}
        {canDelete ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onDelete}
            style={{ marginLeft: "0.5rem", padding: "0.15rem 0.5rem", fontSize: "0.8rem" }}
          >
            Remove
          </button>
        ) : null}
      </span>
    </div>
  );
}

export default function DocumentationSourceForm({ modelId }: { modelId: number }) {
  const { user } = useAuth();
  const [sources, setSources] = useState<DocumentationSourceRead[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [url, setUrl] = useState("");
  const [docType, setDocType] = useState<DocumentationType>("research_paper");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    try {
      const list = await apiFetch<DocumentationSourceList>(`/v1/models/${modelId}/documentation`);
      setSources(list.items);
    } catch (err) {
      setError(err);
    }
  }

  useEffect(() => {
    void load();
  }, [modelId]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch(`/v1/models/${modelId}/documentation`, {
        method: "POST",
        body: {
          url: url.trim(),
          documentation_type: docType,
          title: title.trim() || null,
          description: description.trim() || null,
        },
      });
      setUrl("");
      setTitle("");
      setDescription("");
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(sourceId: number) {
    setError(null);
    try {
      await apiFetch(`/v1/models/${modelId}/documentation/${sourceId}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div>
      <ErrorNotice error={error} />
      {sources == null ? (
        <p className="muted">Loading documentation sources…</p>
      ) : sources.length === 0 ? (
        <p className="empty">No documentation sources recorded yet.</p>
      ) : (
        <div className="dimension-limitations" style={{ marginBottom: "1rem" }}>
          {sources.map((s) => (
            <SourceRow
              key={s.id}
              source={s}
              canDelete={s.source_kind === "user_supplied" && (user?.role === "admin" || user?.id === s.created_by)}
              onDelete={() => void remove(s.id)}
            />
          ))}
        </div>
      )}

      <form onSubmit={(e) => void submit(e)} className="form-grid">
        <label>
          Documentation URL
          <input
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://arxiv.org/abs/..."
          />
        </label>
        <label>
          Type
          <select value={docType} onChange={(e) => setDocType(e.target.value as DocumentationType)}>
            {DOC_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Title (optional)
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Description (optional)
          <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <button type="submit" className="btn" disabled={submitting}>
          {submitting ? "Adding…" : "Add documentation source"}
        </button>
      </form>
      <p className="field-hint">
        TrustLens does not fetch or hash this URL's content — it is recorded as a declared
        pointer for a human reviewer to follow, not verified evidence.
      </p>
    </div>
  );
}
