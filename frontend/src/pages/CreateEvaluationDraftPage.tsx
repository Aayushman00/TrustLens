/**
 * Draft-based evaluation creation wizard (Phase 3, Task 3.5; made the
 * default entry point at /evaluations/new in Phase 6). The old flat-contract
 * wizard (CreateEvaluationPage.tsx) is still reachable at
 * /evaluations/new-legacy, unchanged, pending Phase 7 removal.
 *
 * Flow: pick a model -> create an EvaluationDraft -> optionally configure
 * Fairness and/or Robustness (DatasetIntakeForm -> ColumnRoleMappingForm ->
 * confirm) -> "Continue" enables once every *enabled* dimension is confirmed.
 *
 * Model-picker reuse note: the model-selection step below is copied,
 * deliberately near-verbatim in behavior (fetch `/v1/models?limit=100`,
 * render a card grid, select-to-continue), from CreateEvaluationPage.tsx's
 * "model" step rather than extracted into a shared hook/component. Extracting
 * would require editing CreateEvaluationPage.tsx, which this task must leave
 * completely untouched; the reusable slice is also small enough (one fetch +
 * one render block) that duplicating it is cheaper and safer than threading a
 * shared abstraction through a component this task must not modify.
 */
import { useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  DatasetContentRead,
  DimensionValidationRead,
  EvaluationDraftRead,
  ModelList,
  ModelRead,
} from "../api/types";
import ColumnRoleMappingForm from "../components/ColumnRoleMappingForm";
import DatasetIntakeForm from "../components/DatasetIntakeForm";
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
  // --- Model step (duplicated from CreateEvaluationPage.tsx's "model" step) ---
  const [modelId, setModelId] = useState<number | null>(null);
  const [models, setModels] = useState<ModelRead[] | null>(null);
  const [model, setModel] = useState<ModelRead | null>(null);
  const [modelError, setModelError] = useState<unknown>(null);

  useEffect(() => {
    if (modelId != null) return;
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
  }, [modelId]);

  // --- Draft creation ---
  const [draft, setDraft] = useState<EvaluationDraftRead | null>(null);
  const [creatingDraft, setCreatingDraft] = useState(false);
  const [draftError, setDraftError] = useState<unknown>(null);

  async function startDraft() {
    if (modelId === null || model === null) return;
    setCreatingDraft(true);
    setDraftError(null);
    try {
      const created = await apiFetch<EvaluationDraftRead>("/v1/evaluation-drafts", {
        method: "POST",
        body: { model_id: modelId },
      });
      setDraft(created);
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
            <DatasetIntakeForm onContentReady={(content) => handleContentReady(dim, content)} />

            {state.content && draft ? (
              <ColumnRoleMappingForm
                key={state.content.id}
                draftId={draft.id}
                dimension={dim}
                content={state.content}
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
          <h1>New evaluation (draft wizard)</h1>
          <p className="muted">
            Model selection, then a per-dimension dataset intake and column-role mapping flow.
          </p>
        </div>
      </div>

      <ErrorNotice error={modelError} />

      {!model ? (
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

      {model && !draft ? (
        <div className="card">
          <h2>Create draft</h2>
          <p className="muted">
            {model.hf_repo_id} · revision <span className="mono">{shortRevision(model.revision)}</span>
          </p>
          <ErrorNotice error={draftError} />
          <div className="btn-row">
            <button type="button" className="btn" disabled={creatingDraft} onClick={() => void startDraft()}>
              {creatingDraft ? "Creating…" : "Start draft"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setModel(null);
                setModelId(null);
              }}
            >
              Back
            </button>
          </div>
        </div>
      ) : null}

      {draft ? (
        <>
          {renderDimension("FAIRNESS")}
          {renderDimension("ROBUSTNESS")}

          <div className="btn-row" style={{ marginTop: "1rem" }}>
            <button type="button" className="btn" disabled={!readyToContinue}>
              Continue to review
            </button>
          </div>
        </>
      ) : null}
    </>
  );
}
