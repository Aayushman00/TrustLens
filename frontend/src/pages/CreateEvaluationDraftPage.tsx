/**
 * Draft-based evaluation creation wizard (Phase 3, Task 3.5; made the
 * default entry point at /evaluations/new in Phase 6). The old flat-contract
 * wizard was deleted in Phase 7.
 *
 * Flow: model (preselected via ?modelId=, or picked here if reached
 * directly) -> create an EvaluationDraft -> optionally configure Fairness
 * and/or Robustness (DatasetIntakeForm -> ColumnRoleMappingForm -> confirm)
 * -> optionally attach documentation sources for this model -> "Continue"
 * enables once every *enabled* dimension is confirmed.
 *
 * A model reached via ?modelId= (the normal path — every in-app link to
 * this page already carries it) is fixed for the rest of the flow: its
 * revision is what gets frozen into the evaluation, and it is never
 * re-selectable here. Reaching this page with no ?modelId= at all (a bare
 * /evaluations/new) falls back to picking a model from the full list.
 */
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import type {
  DatasetContentRead,
  DimensionValidationRead,
  EvaluationDraftRead,
  EvaluationRead,
  ModelList,
  ModelRead,
} from "../api/types";
import ColumnRoleMappingForm from "../components/ColumnRoleMappingForm";
import DatasetIntakeForm from "../components/DatasetIntakeForm";
import DocumentationSourceForm from "../components/DocumentationSourceForm";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import { shortRevision } from "../lib/contract";

type Dimension = "FAIRNESS" | "ROBUSTNESS";

interface DimensionState {
  enabled: boolean;
  content: DatasetContentRead | null;
  validation: DimensionValidationRead | null;
  confirmed: boolean;
  confirming: boolean;
  confirmError: unknown;
}

function initialDimensionState(): DimensionState {
  return {
    enabled: false,
    content: null,
    validation: null,
    confirmed: false,
    confirming: false,
    confirmError: null,
  };
}

const DIMENSION_LABEL: Record<Dimension, string> = {
  FAIRNESS: "Fairness",
  ROBUSTNESS: "Robustness",
};

export default function CreateEvaluationDraftPage() {
  const navigate = useNavigate();

  // --- Model step ---
  const [searchParams] = useSearchParams();
  const preselectedModelId = searchParams.get("modelId");

  const [modelId, setModelId] = useState<number | null>(null);
  const [models, setModels] = useState<ModelRead[] | null>(null);
  const [model, setModel] = useState<ModelRead | null>(null);
  const [modelError, setModelError] = useState<unknown>(null);
  const [loadingPreselected, setLoadingPreselected] = useState(preselectedModelId != null);

  useEffect(() => {
    if (preselectedModelId == null) return;
    let cancelled = false;
    apiFetch<ModelRead>(`/v1/models/${preselectedModelId}`)
      .then((row) => {
        if (cancelled) return;
        setModel(row);
        setModelId(row.id);
      })
      .catch((err) => {
        if (!cancelled) setModelError(err);
      })
      .finally(() => {
        if (!cancelled) setLoadingPreselected(false);
      });
    return () => {
      cancelled = true;
    };
    // Only the id from the URL should ever re-trigger this — it identifies
    // a fixed starting point for the flow, not a value to keep re-reading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preselectedModelId]);

  useEffect(() => {
    if (preselectedModelId != null || modelId != null) return;
    let cancelled = false;
    apiFetch<ModelList>("/v1/models?limit=100")
      .then((page) => {
        if (!cancelled) setModels(page.items);
      })
      .catch((err) => {
        if (!cancelled) setModelError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [preselectedModelId, modelId]);

  const isPinned = model != null && !!model.revision;

  // --- Draft creation ---
  const [draft, setDraft] = useState<EvaluationDraftRead | null>(null);
  const [creatingDraft, setCreatingDraft] = useState(false);
  const [draftError, setDraftError] = useState<unknown>(null);

  async function startDraft() {
    if (modelId === null || model === null || !isPinned) return;
    setCreatingDraft(true);
    setDraftError(null);
    try {
      const created = await apiFetch<EvaluationDraftRead>("/v1/evaluation-drafts", {
        method: "POST",
        body: { model_id: modelId },
      });
      // A follow-up GET triggers the backend's model-config inspection right
      // away (see EvaluationDraftService.get -> _ensure_model_snapshot), so
      // model_label_snapshot is populated before the user ever opens a
      // dimension's mapping UI -- not only after their first Save & validate.
      const withSnapshot = await apiFetch<EvaluationDraftRead>(`/v1/evaluation-drafts/${created.id}`);
      setDraft(withSnapshot);
    } catch (err) {
      setDraftError(err);
    } finally {
      setCreatingDraft(false);
    }
  }

  // --- Per-dimension state ---
  const [fairness, setFairness] = useState<DimensionState>(initialDimensionState);
  const [robustness, setRobustness] = useState<DimensionState>(initialDimensionState);

  function stateFor(dim: Dimension) {
    return dim === "FAIRNESS" ? fairness : robustness;
  }
  function setStateFor(dim: Dimension, updater: (prev: DimensionState) => DimensionState) {
    if (dim === "FAIRNESS") setFairness(updater);
    else setRobustness(updater);
  }

  function toggleDimension(dim: Dimension, checked: boolean) {
    if (checked) {
      setStateFor(dim, (prev) => ({ ...prev, enabled: true }));
    } else {
      // Unchecking resets everything for this dimension, including its
      // confirmed flag — a re-check must start from a fresh intake/mapping
      // pass rather than silently keeping a stale confirmation around (the
      // draft's own fairness_confirmed/robustness_confirmed only ever moves
      // forward via the confirm endpoint, so the "un-confirm" has to happen
      // here, client-side, on the UI's own local copy of that flag).
      setStateFor(dim, () => initialDimensionState());
    }
  }

  function handleFetchStart(dim: Dimension) {
    // A (re-)fetch attempt starting -- whatever dataset/validation/
    // confirmation this dimension had before is no longer current. Clearing
    // content here (not just on success) unmounts ColumnRoleMappingForm
    // immediately, so a failed replacement fetch can never leave a stale
    // dataset's column/label-mapping UI visibly attached.
    setStateFor(dim, (prev) => ({ ...prev, content: null, validation: null, confirmed: false }));
  }

  function handleContentReady(dim: Dimension, content: DatasetContentRead) {
    setStateFor(dim, (prev) => ({ ...prev, content, validation: null, confirmed: false }));
  }

  function handleValidated(dim: Dimension, result: DimensionValidationRead) {
    // A fresh (or re-)validation always clears any prior confirmation for
    // this dimension, mirroring the backend's own rule that editing a
    // dimension's config clears its confirmed_at.
    setStateFor(dim, (prev) => ({ ...prev, validation: result, confirmed: false }));
  }

  async function confirmDimension(dim: Dimension) {
    if (!draft) return;
    setStateFor(dim, (prev) => ({ ...prev, confirming: true, confirmError: null }));
    try {
      const updated = await apiFetch<EvaluationDraftRead>(
        `/v1/evaluation-drafts/${draft.id}/${dim}/confirm`,
        { method: "POST" },
      );
      setDraft(updated);
      setStateFor(dim, (prev) => ({ ...prev, confirming: false, confirmed: true }));
    } catch (err) {
      setStateFor(dim, (prev) => ({ ...prev, confirming: false, confirmError: err }));
    }
  }

  const anyEnabled = fairness.enabled || robustness.enabled;
  const readyToContinue =
    draft !== null &&
    anyEnabled &&
    (!fairness.enabled || fairness.confirmed) &&
    (!robustness.enabled || robustness.confirmed);

  // --- Create the real Evaluation from the confirmed draft ---
  const [creatingEvaluation, setCreatingEvaluation] = useState(false);
  const [continueError, setContinueError] = useState<unknown>(null);

  async function continueToReview() {
    if (!draft || !readyToContinue) return;
    setCreatingEvaluation(true);
    setContinueError(null);
    try {
      const created = await apiFetch<EvaluationRead>("/v1/evaluations-v2", {
        method: "POST",
        body: { draft_id: draft.id, evaluation_mode: "AI_ASSISTED" },
      });
      navigate(`/evaluations/${created.id}`);
    } catch (err) {
      setContinueError(err);
    } finally {
      setCreatingEvaluation(false);
    }
  }

  function renderDimension(dim: Dimension) {
    const state = stateFor(dim);
    const inputId = `configure-${dim.toLowerCase()}`;
    return (
      <div className="card" key={dim}>
        <label htmlFor={inputId}>
          <input
            id={inputId}
            type="checkbox"
            checked={state.enabled}
            onChange={(e) => toggleDimension(dim, e.target.checked)}
          />{" "}
          Configure {DIMENSION_LABEL[dim]}
        </label>

        {state.enabled ? (
          <div style={{ marginTop: "0.8rem" }}>
            <DatasetIntakeForm
              onContentReady={(content) => handleContentReady(dim, content)}
              onFetchStart={() => handleFetchStart(dim)}
            />

            {state.content && draft ? (
              <ColumnRoleMappingForm
                key={state.content.id}
                draftId={draft.id}
                dimension={dim}
                content={state.content}
                modelLabelSnapshot={draft.model_label_snapshot}
                onValidated={(result) => handleValidated(dim, result)}
              />
            ) : null}

            {state.validation && !state.validation.ok ? (
              <div className="dimension-limitations">
                <p>Validation failed:</p>
                <ul>
                  {state.validation.errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {state.validation?.ok ? (
              <>
                <ErrorNotice error={state.confirmError} />
                <button
                  type="button"
                  className="btn"
                  disabled={state.confirming || state.confirmed}
                  onClick={() => void confirmDimension(dim)}
                >
                  {state.confirmed
                    ? `${DIMENSION_LABEL[dim]} confirmed`
                    : state.confirming
                      ? "Confirming…"
                      : `Confirm ${DIMENSION_LABEL[dim]}`}
                </button>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>New evaluation</h1>
          <p className="muted">
            {model
              ? "Configure Fairness, Robustness, and documentation for this model."
              : "Choose a model, then configure Fairness, Robustness, and documentation."}
          </p>
        </div>
      </div>

      <ErrorNotice error={modelError} />

      {loadingPreselected ? <Spinner label="Loading model…" /> : null}

      {!model && !loadingPreselected && preselectedModelId == null ? (
        <div className="card">
          <h2>Choose a model</h2>
          {models == null ? <Spinner label="Loading models…" /> : null}
          {models != null && models.length === 0 ? (
            <p className="empty">No models yet — import one first.</p>
          ) : null}
          {models != null && models.length > 0 ? (
            <div className="contract-card-grid">
              {models.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className="contract-card"
                  onClick={() => {
                    setModelId(m.id);
                    setModel(m);
                  }}
                >
                  <span className="contract-card-title">{m.hf_repo_id}</span>
                  <span className="contract-card-sub mono">
                    Revision: {shortRevision(m.revision)}
                  </span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {model && !isPinned ? (
        <div className="card">
          <h2>{model.hf_repo_id}</h2>
          <div className="notice notice-error">
            This model has no pinned revision, so an evaluation of it could not be reproduced
            later. Re-import it with an explicit revision before evaluating.
          </div>
        </div>
      ) : null}

      {model && isPinned && !draft ? (
        <div className="card">
          <h2>{model.hf_repo_id}</h2>
          <p className="muted">
            Revision <span className="mono">{shortRevision(model.revision)}</span> — fixed for
            this evaluation.
          </p>
          <ErrorNotice error={draftError} />
          <div className="btn-row">
            <button type="button" className="btn" disabled={creatingDraft} onClick={() => void startDraft()}>
              {creatingDraft ? "Starting…" : "Start evaluation"}
            </button>
            {preselectedModelId == null ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setModel(null);
                  setModelId(null);
                }}
              >
                Choose a different model
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {draft ? (
        <>
          {renderDimension("FAIRNESS")}
          {renderDimension("ROBUSTNESS")}

          <div className="card">
            <h2>Documentation</h2>
            <p className="muted">
              The pinned model card is included automatically. Add papers, safety cards, or
              other documentation for the Integrity, Explainability, and Safety probes.
            </p>
            <DocumentationSourceForm modelId={draft.model_id} />
          </div>

          <ErrorNotice error={continueError} />
          <div className="btn-row" style={{ marginTop: "1rem" }}>
            <button
              type="button"
              className="btn"
              disabled={!readyToContinue || creatingEvaluation}
              onClick={() => void continueToReview()}
            >
              {creatingEvaluation ? "Creating…" : "Continue to review"}
            </button>
          </div>
        </>
      ) : null}
    </>
  );
}
