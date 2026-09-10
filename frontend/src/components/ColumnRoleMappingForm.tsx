/**
 * Column-role mapping: pick text/target/(sensitive) columns for a dimension
 * and submit them via PUT /v1/evaluation-drafts/{draftId}/{dimension} for
 * server-side validation. Once a target column is chosen, distinct observed
 * dataset values are fetched via GET .../target-values and rendered as one
 * mapping row per value, each defaulting to "unmapped" (model_label_index:
 * -1) — per the "never auto-apply without confirm" Global Constraint, no
 * row is ever pre-selected, even when a dataset value's spelling looks like
 * an obvious match to a model label. The server's "missing entries" check
 * (_validate_label_mapping) rejects any row left at -1, which is what
 * actually enforces this — there is no client-side default guess, ever.
 */
import { useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type { DatasetContentRead, DimensionValidationRead, LabelMappingEntry } from "../api/types";
import ErrorNotice from "./ErrorNotice";

export default function ColumnRoleMappingForm({
  draftId,
  dimension,
  content,
  onValidated,
}: {
  draftId: string;
  dimension: "FAIRNESS" | "ROBUSTNESS";
  content: DatasetContentRead;
  onValidated: (result: DimensionValidationRead) => void;
}) {
  const [textColumn, setTextColumn] = useState("");
  const [targetColumn, setTargetColumn] = useState("");
  const [sensitiveColumn, setSensitiveColumn] = useState("");
  const [labelMapping, setLabelMapping] = useState<LabelMappingEntry[]>([]);
  const [targetValues, setTargetValues] = useState<string[]>([]);
  // TODO(Task 4.x): replace with the real id2label once EvaluationDraftRead
  // exposes model_label_snapshot to the frontend.
  const modelLabels = ["NEGATIVE", "POSITIVE"];
  const [minGroupN, setMinGroupN] = useState(30);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!targetColumn) return;
    // Ignore-flag guard: if the target column changes again before this
    // fetch resolves, a stale (out-of-order) response must never overwrite
    // state for the column the user has since moved on to.
    let ignore = false;
    async function fetchTargetValues() {
      try {
        const res = await apiFetch<{ values: string[] }>(
          `/v1/evaluation-drafts/${draftId}/${dimension}/target-values?dataset_content_id=${encodeURIComponent(content.id)}&target_column=${encodeURIComponent(targetColumn)}`
        );
        if (ignore) return;
        setTargetValues(res.values);
        // Every row starts unmapped (-1) — never auto-applied, never a
        // pre-selected guess, no matter how confident a normalized-string
        // match would look.
        setLabelMapping(res.values.map((v) => ({ dataset_value: v, model_label_index: -1 })));
      } catch (err) {
        if (!ignore) setError(err);
      }
    }
    void fetchTargetValues();
    return () => {
      ignore = true;
    };
  }, [targetColumn, draftId, dimension, content.id]);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const result = await apiFetch<DimensionValidationRead>(
        `/v1/evaluation-drafts/${draftId}/${dimension}`,
        {
          method: "PUT",
          body: {
            dataset_content_id: content.id,
            text_column: textColumn,
            target_column: targetColumn,
            sensitive_column: dimension === "FAIRNESS" ? sensitiveColumn : undefined,
            label_mapping: labelMapping,
            min_group_n: dimension === "FAIRNESS" ? minGroupN : undefined,
          },
        }
      );
      onValidated(result);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <ErrorNotice error={error} />
      <label>
        Text column
        <select value={textColumn} onChange={(e) => setTextColumn(e.target.value)}>
          <option value="">Select…</option>
          {content.columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Target column
        <select value={targetColumn} onChange={(e) => setTargetColumn(e.target.value)}>
          <option value="">Select…</option>
          {content.columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      {dimension === "FAIRNESS" ? (
        <>
          <label>
            Sensitive column
            <select value={sensitiveColumn} onChange={(e) => setSensitiveColumn(e.target.value)}>
              <option value="">Select…</option>
              {content.columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Minimum group size
            <input
              type="number"
              min={1}
              value={minGroupN}
              onChange={(e) => setMinGroupN(Number(e.target.value))}
            />
          </label>
        </>
      ) : null}
      {targetValues.length > 0 ? (
        <fieldset>
          <legend>Map dataset labels to model labels</legend>
          {targetValues.map((value, idx) => (
            <label key={value}>
              {value} {"→"}
              <select
                value={labelMapping[idx]?.model_label_index ?? -1}
                onChange={(e) => {
                  const next = [...labelMapping];
                  next[idx] = { dataset_value: value, model_label_index: Number(e.target.value) };
                  setLabelMapping(next);
                }}
              >
                <option value={-1}>Select model label…</option>
                {modelLabels.map((label, i) => (
                  <option key={label} value={i}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>
      ) : null}
      <button type="button" onClick={() => void submit()} disabled={submitting}>
        {submitting ? "Validating…" : "Save & validate"}
      </button>
    </div>
  );
}
