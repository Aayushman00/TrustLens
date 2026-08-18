import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import type {
  EvaluationCreate,
  EvaluationList,
  EvaluationMode,
  EvaluationRead,
  ModelRead,
} from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import StatusBadge from "../components/StatusBadge";
import { modeLabel } from "../components/ModeDisclosure";
import { fmtDateTime } from "../lib/format";

export default function ModelDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [model, setModel] = useState<ModelRead | null>(null);
  const [history, setHistory] = useState<EvaluationRead[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const [mode, setMode] = useState<EvaluationMode>("AI_AUTONOMOUS");
  const [task, setTask] = useState("");
  const [dataset, setDataset] = useState("");
  const [createError, setCreateError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [row, evals] = await Promise.all([
          apiFetch<ModelRead>(`/v1/models/${id}`),
          apiFetch<EvaluationList>("/v1/evaluations?limit=200"),
        ]);
        if (!cancelled) {
          setModel(row);
          setHistory(evals.items.filter((e) => e.model_id === row.id));
        }
      } catch (err) {
        if (!cancelled) setError(err);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!model) return;
    setCreateError(null);
    setCreating(true);
    const body: EvaluationCreate = { model_id: model.id, evaluation_mode: mode };
    if (task.trim()) body.task = task.trim();
    if (dataset.trim()) body.dataset = dataset.trim();
    try {
      const created = await apiFetch<EvaluationRead>("/v1/evaluations", {
        method: "POST",
        body,
      });
      navigate(`/evaluations/${created.id}`);
    } catch (err) {
      setCreateError(err);
      setCreating(false);
    }
  }

  if (error != null) return <ErrorNotice error={error} />;
  if (model == null) return <Spinner label="Loading model…" />;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{model.hf_repo_id}</h1>
          <p className="muted">Model #{model.id}</p>
        </div>
      </div>
      <div className="grid-2">
        <div>
          <div className="card">
            <h2>Details</h2>
            <dl className="kv">
              <dt>Repo</dt>
              <dd>
                <a
                  href={`https://huggingface.co/${model.hf_repo_id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {model.hf_repo_id}
                </a>
              </dd>
              <dt>Revision</dt>
              <dd className="mono">{model.revision ?? "—"}</dd>
              <dt>Checksum</dt>
              <dd className="mono">{model.checksum ?? "—"}</dd>
              <dt>Imported</dt>
              <dd>{fmtDateTime(model.created_at)}</dd>
            </dl>
          </div>
          <div className="card">
            <h2>Evaluations of this model</h2>
            {history == null ? <Spinner label="Loading…" /> : null}
            {history != null && history.length === 0 ? (
              <p className="empty">None yet — start one on the right.</p>
            ) : null}
            {history != null && history.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Evaluation</th>
                      <th>Mode</th>
                      <th>Status</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((evaluation) => (
                      <tr key={evaluation.id}>
                        <td>
                          <Link to={`/evaluations/${evaluation.id}`} className="mono">
                            {evaluation.id.slice(0, 8)}…
                          </Link>
                        </td>
                        <td>{modeLabel(evaluation.evaluation_mode)}</td>
                        <td>
                          <StatusBadge status={evaluation.status} />
                        </td>
                        <td className="muted">{fmtDateTime(evaluation.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </div>
        <div className="card">
          <h2>New evaluation</h2>
          <form className="form" onSubmit={handleCreate}>
            <div className="field">
              Mode
              <label className="radio-row">
                <input
                  type="radio"
                  name="mode"
                  checked={mode === "AI_AUTONOMOUS"}
                  onChange={() => setMode("AI_AUTONOMOUS")}
                />
                <span>
                  AI-Autonomous — finalizes automatically from agent O/S/D; results are
                  marked <em>not human-reviewed</em>.
                </span>
              </label>
              <label className="radio-row">
                <input
                  type="radio"
                  name="mode"
                  checked={mode === "AI_ASSISTED"}
                  onChange={() => setMode("AI_ASSISTED")}
                />
                <span>
                  AI-Assisted — pauses at <em>awaiting review</em>; a reviewer accepts or
                  edits the agent O/S/D before finalize.
                </span>
              </label>
            </div>
            <label>
              Task (optional)
              <input
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="e.g. sentiment-classification"
              />
              <span className="field-hint">
                Used by the leaderboard comparability filter.
              </span>
            </label>
            <label>
              Dataset (optional)
              <input
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
                placeholder="e.g. sst2"
              />
            </label>
            <ErrorNotice error={createError} />
            <button type="submit" className="btn" disabled={creating}>
              {creating ? "Creating…" : "Create evaluation"}
            </button>
            <span className="field-hint">
              Probe config uses server defaults; all five FRIES probes run.
            </span>
          </form>
        </div>
      </div>
    </>
  );
}
