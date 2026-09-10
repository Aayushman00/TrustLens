/**
 * Column-role mapping: pick text/target/(sensitive) columns for a dimension
 * and submit them via PUT /v1/evaluation-drafts/{draftId}/{dimension} for
 * server-side validation. Label-mapping rows (per-observed-value dropdowns,
 * populated via a GET-based values discovery call) are deferred to Task 3.4
 * — every row there must start unmapped, per the "never auto-apply without
 * confirm" rule; this task only wires the column-role selects and the
 * save/validate submit flow.
 */
import { useState } from "react";

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
  const [labelMapping] = useState<LabelMappingEntry[]>([]);
  const [minGroupN, setMinGroupN] = useState(30);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

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
      {/* Label-mapping rows: populated from an explicit "discover values" step
          not yet wired here — deferred to Task 3.4, which adds a
          GET-based values discovery call and renders one mapping row per
          observed dataset value, each defaulting to unmapped. */}
      <button type="button" onClick={() => void submit()} disabled={submitting}>
        {submitting ? "Validating…" : "Save & validate"}
      </button>
    </div>
  );
}
