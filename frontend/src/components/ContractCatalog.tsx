/**
 * Renders the REAL, already-approved evaluation contracts for one model
 * (GET /v1/models/{id}/evaluation-options) — never an invented or
 * auto-substituted dataset. Shared by ModelDetailPage (read-only display)
 * and CreateEvaluationPage (selectable).
 */
import type { EvaluationOptionsRead } from "../api/types";

export interface ContractSelection {
  family: "fairness" | "robustness" | "documentation";
  pairing_id?: string;
  dataset_key?: string;
  contract_kind?: "proxy_lr";
  /** User-defined local Fairness dataset (kind="user_dataset"). */
  user_dataset_id?: string;
  target_column?: string;
  group_column?: string;
  text_column?: string;
  included_group_values?: string[];
  label: string;
  sublabel: string;
}

export default function ContractCatalog({
  options,
  selectable = false,
  selected,
  onSelect,
}: {
  options: EvaluationOptionsRead;
  selectable?: boolean;
  selected?: ContractSelection | null;
  onSelect?: (choice: ContractSelection) => void;
}) {
  const hasFairness = options.fairness.length > 0;
  const hasRobustness = options.robustness.length > 0;

  const CardTag = selectable ? "button" : "div";

  return (
    <>
      <div className="contract-group">
        <div className="contract-group-title">Fairness</div>
        {hasFairness ? (
          <div className="contract-card-grid">
            {options.fairness.map((f) => {
              const isSelected =
                selected?.family === "fairness" && selected.pairing_id === f.pairing_id;
              return (
                <CardTag
                  key={f.pairing_id}
                  type={selectable ? "button" : undefined}
                  className={`contract-card${!selectable ? " static" : ""}${isSelected ? " selected" : ""}`}
                  onClick={
                    selectable
                      ? () =>
                          onSelect?.({
                            family: "fairness",
                            pairing_id: f.pairing_id,
                            label: f.dataset_key,
                            sublabel: "Model-faithful",
                          })
                      : undefined
                  }
                >
                  <span className="contract-card-title">{f.dataset_key}</span>
                  <span className="contract-card-sub">
                    {f.task_type.replaceAll("_", " ")} · {f.modality}
                  </span>
                  <span className="contract-card-chips">
                    <span className="chip chip-accent">Model-faithful</span>
                    <span className="chip">Local inference</span>
                  </span>
                  {f.notes ? <span className="contract-card-sub">{f.notes}</span> : null}
                </CardTag>
              );
            })}
          </div>
        ) : (
          <p className="empty-contract-note">
            No approved Fairness pairing exists for this exact model + revision.
          </p>
        )}
      </div>

      <div className="contract-group">
        <div className="contract-group-title">Robustness</div>
        {hasRobustness ? (
          <div className="contract-card-grid">
            {options.robustness.map((r) => {
              const isSelected =
                selected?.family === "robustness" && selected.dataset_key === r.dataset_key;
              return (
                <CardTag
                  key={r.dataset_key}
                  type={selectable ? "button" : undefined}
                  className={`contract-card${!selectable ? " static" : ""}${isSelected ? " selected" : ""}`}
                  onClick={
                    selectable
                      ? () =>
                          onSelect?.({
                            family: "robustness",
                            dataset_key: r.dataset_key,
                            label: r.dataset_key,
                            sublabel: "Model-faithful",
                          })
                      : undefined
                  }
                >
                  <span className="contract-card-title">{r.dataset_key.replaceAll("_", " ")}</span>
                  <span className="contract-card-sub">Char-swap · {r.evaluation_domain}</span>
                  <span className="contract-card-chips">
                    <span className="chip chip-accent">Model-faithful</span>
                    <span className="chip">Local inference</span>
                  </span>
                  {r.notes ? <span className="contract-card-sub">{r.notes}</span> : null}
                </CardTag>
              );
            })}
          </div>
        ) : (
          <p className="empty-contract-note">
            No approved Robustness contract exists for this exact model + revision.
          </p>
        )}
      </div>

      <div className="contract-group">
        <div className="contract-group-title">Documentation &amp; Governance</div>
        <div className="contract-card-grid">
          <CardTag
            type={selectable ? "button" : undefined}
            className={`contract-card${!selectable ? " static" : ""}${
              selected?.family === "documentation" ? " selected" : ""
            }`}
            onClick={
              selectable
                ? () =>
                    onSelect?.({
                      family: "documentation",
                      label: "Documentation & governance",
                      sublabel: "Always available",
                    })
                : undefined
            }
          >
            <span className="contract-card-title">Integrity · Explainability · Safety</span>
            <span className="contract-card-sub">
              Documentation and provenance checks — no dataset or local inference required.
            </span>
            <span className="contract-card-chips">
              <span className="chip">Always available</span>
            </span>
          </CardTag>
        </div>
      </div>
    </>
  );
}
