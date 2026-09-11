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
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  DatasetContentRead,
  DimensionValidationRead,
  LabelMappingEntry,
  ModelLabelSnapshot,
} from "../api/types";
import ErrorNotice from "./ErrorNotice";

export default function ColumnRoleMappingForm({
  draftId,
  dimension,
  content,
  modelLabelSnapshot,
  onValidated,
}: {
  draftId: string;
  dimension: "FAIRNESS" | "ROBUSTNESS";
  content: DatasetContentRead;
  /** The draft's frozen model config snapshot -- the ONLY source of model
   * label options for the mapping dropdown below. Never a hardcoded/invented
   * list: a generic id2label (LABEL_0/LABEL_1/...) is shown exactly as-is,
   * never renamed or guessed at. */
  modelLabelSnapshot: ModelLabelSnapshot | null;
  onValidated: (result: DimensionValidationRead) => void;
}) {
  const [textColumn, setTextColumn] = useState("");
  const [targetColumn, setTargetColumn] = useState("");
  const [sensitiveColumn, setSensitiveColumn] = useState("");
  const [labelMapping, setLabelMapping] = useState<LabelMappingEntry[]>([]);
  const [targetValues, setTargetValues] = useState<string[]>([]);
  // Real (index, label) pairs from the model's actual config snapshot --
  // sorted by index so a 3-class model always shows exactly 3 choices, a
  // 2-class model exactly 2, in a stable order.
  const modelLabelOptions = useMemo(
    () =>
      modelLabelSnapshot
        ? Object.entries(modelLabelSnapshot.id2label)
            .map(([idx, label]) => ({ index: Number(idx), label }))
            .sort((a, b) => a.index - b.index)
        : [],
    [modelLabelSnapshot]
  );
  const [minGroupN, setMinGroupN] = useState(30);
  // Fairness-only: which model_label_index DP/EO/F1-spread treat as the
  // "positive"/favorable outcome. Pre-filled to 1 (the field's own default)
  // so the form isn't empty, but it is a VISIBLE, editable control the user
  // must look at and confirm/change -- never applied silently. A mapping
  // that never points any dataset value at index 1 makes that pre-fill
  // meaningless (DP/EO/F1 would be computed against a class ground truth
  // can never attain); the backend rejects that case explicitly.
  const [positiveLabelIndex, setPositiveLabelIndex] = useState(1);
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
            positive_label_index: dimension === "FAIRNESS" ? positiveLabelIndex : undefined,
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

  if (!modelLabelSnapshot) {
    // A model with unusable/missing classification metadata (or a snapshot
    // that hasn't loaded) must block configuration here rather than fall
    // back to an invented label list -- there is nothing safe to map to.
    return (
      <div>
        <ErrorNotice error={error} />
        <p className="dimension-limitations">
          Model label metadata is not available for this draft -- column/label mapping cannot be
          configured until the model's real classification labels are known.
        </p>
      </div>
    );
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
          <label>
            Favorable outcome for fairness metrics
            <select
              value={positiveLabelIndex}
              onChange={(e) => setPositiveLabelIndex(Number(e.target.value))}
            >
              {modelLabelOptions.map(({ index, label }) => (
                <option key={index} value={index}>
                  {label}
                </option>
              ))}
            </select>
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
                {modelLabelOptions.map(({ index, label }) => (
                  <option key={index} value={index}>
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
