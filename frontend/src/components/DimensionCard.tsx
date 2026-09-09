/**
 * One FRIES dimension result card (Results page).
 *
 * Renders directly off ProbeEvidenceRead + its raw metric_values — every
 * number shown here is REAL (already computed and persisted by the probe).
 * There is no dimension for which this component invents a value; a field
 * with no backend source renders "Unavailable" (see UNAVAILABLE contract).
 */
import type { FriesDimension, ProbeEvidenceRead } from "../api/types";
import StatusPill, { normalizeStatus, type DisplayStatus } from "./StatusPill";

function num(value: unknown, digits = 3): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value.toFixed(digits);
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function ciRange(uncertainty: unknown, key: string): string | null {
  if (!uncertainty || typeof uncertainty !== "object") return null;
  const entry = (uncertainty as Record<string, unknown>)[key];
  if (!entry || typeof entry !== "object") return null;
  const lower = (entry as Record<string, unknown>).ci_lower;
  const upper = (entry as Record<string, unknown>).ci_upper;
  if (typeof lower !== "number" || typeof upper !== "number") return null;
  return `${lower.toFixed(3)} — ${upper.toFixed(3)}`;
}

function checksList(metrics: Record<string, unknown> | null): { name: string; detail: string }[] {
  const checks = metrics?.checks;
  if (!checks || typeof checks !== "object") return [];
  return Object.entries(checks as Record<string, Record<string, unknown>>).map(([name, v]) => {
    const detail = str(v.detail) ?? str(v.status) ?? JSON.stringify(v).slice(0, 120);
    return { name: name.replaceAll("_", " "), detail };
  });
}

const DIMENSION_LABEL: Record<FriesDimension, string> = {
  FAIRNESS: "Fairness",
  ROBUSTNESS: "Robustness",
  INTEGRITY: "Integrity",
  EXPLAINABILITY: "Explainability",
  SAFETY: "Safety",
};

function displayStatusFor(probe: ProbeEvidenceRead | undefined): DisplayStatus {
  if (!probe) return "NOT_APPLICABLE";
  return normalizeStatus(probe.status);
}

function FairnessBody({ probe }: { probe: ProbeEvidenceRead }) {
  const m = probe.metric_values ?? {};
  const status = normalizeStatus(probe.status);
  if (status === "NOT_APPLICABLE") {
    return (
      <div className="dimension-note">
        No compatible Fairness contract was selected for this evaluation.
        <br />
        <strong>This is not a fairness score of zero.</strong>
      </div>
    );
  }
  if (status === "PROXY") {
    return (
      <>
        <div className="dimension-note">
          Proxy evaluation — predictions come from a separate sklearn model on
          tabular features, <strong>not the imported model</strong>. Proxy is
          never equivalent to model-faithful.
        </div>
        <Row label="Demographic parity difference" value={num(m.demographic_parity_difference)} />
        <Row label="Equalized odds difference" value={num(m.equalized_odds_difference)} />
      </>
    );
  }
  const gap = num(m.subgroup_worst_group_acc_gap ?? m.demographic_parity_difference);
  const gapLabel = m.subgroup_worst_group_acc_gap != null
    ? "Worst-group accuracy gap"
    : "Demographic parity difference";
  const ci = ciRange(m.uncertainty, "subgroup_worst_group_acc_gap");
  const isUserDataset = probe.fairness_mode === "user_defined_local";
  const fairnessModeLabel =
    probe.fairness_mode === "model_faithful"
      ? "Model-faithful"
      : isUserDataset
        ? "User-defined local evaluation"
        : str(probe.fairness_mode);
  return (
    <>
      {isUserDataset ? (
        <div className="dimension-note">
          Evaluated against your own local dataset — not an approved/certified benchmark.
        </div>
      ) : null}
      <Row label={gapLabel} value={gap} />
      {ci ? <Row label="95% CI" value={ci} /> : null}
      <Row label="Risk interpretation" value={str(m.scored_risk_id) ?? (probe.risks_triggered?.length ? probe.risks_triggered.join(", ") : "No material risk detected")} />
      <Row label="Fairness mode" value={fairnessModeLabel} />
    </>
  );
}

function RobustnessBody({ probe }: { probe: ProbeEvidenceRead }) {
  const m = probe.metric_values ?? {};
  const status = normalizeStatus(probe.status);
  if (status === "NOT_APPLICABLE") {
    return (
      <div className="dimension-note">
        No compatible Robustness contract was selected for this evaluation.
        <br />
        <strong>This is not a robustness score of zero.</strong>
      </div>
    );
  }
  return (
    <>
      <Row label="Attack" value={str(m.attack) ?? "char_swap"} />
      <Row label="Clean accuracy" value={num(m.clean_accuracy)} />
      <Row label="Robust accuracy" value={num(m.robust_accuracy)} />
      <Row label="Accuracy drop" value={num(m.accuracy_drop)} />
      <Row label="Risk interpretation" value={str(m.scored_risk_id) ?? (probe.risks_triggered?.length ? probe.risks_triggered.join(", ") : "No material risk detected")} />
    </>
  );
}

function ChecksBody({ probe }: { probe: ProbeEvidenceRead }) {
  const checks = checksList(probe.metric_values);
  if (checks.length === 0) {
    return <div className="dimension-note">No documentation checks were recorded for this run.</div>;
  }
  return (
    <div className="dimension-limitations">
      {checks.map((c) => (
        <div key={c.name} className="dimension-row">
          <span className="dimension-row-label">{c.name}</span>
          <span className="dimension-row-value">{c.detail}</span>
        </div>
      ))}
    </div>
  );
}

/** Explainability/Safety are Track 1 documentation/governance checks only —
 * `coverage_ratio` is section/checklist completeness, never a normative
 * "explainable" or "safe" verdict. Always labeled "Documentation coverage". */
function DocumentationCoverageRow({ probe }: { probe: ProbeEvidenceRead }) {
  const m = probe.metric_values ?? {};
  const coverage = num(m.coverage_ratio, 2);
  const source = m.documentation_source as Record<string, unknown> | null | undefined;
  return (
    <>
      <Row label="Documentation coverage" value={coverage} />
      {source ? (
        <Row
          label="Documentation source"
          value={`${str(source.documentation_source_type) ?? "model_card"} · revision ${
            str(source.documentation_revision)?.slice(0, 8) ?? "unknown"
          } · ${str(source.retrieval_status) ?? "unknown"}`}
        />
      ) : (
        <Row label="Documentation source" value={null} />
      )}
    </>
  );
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="dimension-row">
      <span className="dimension-row-label">{label}</span>
      <span className="dimension-row-value">
        {value ?? <span className="unavailable-value">Unavailable</span>}
      </span>
    </div>
  );
}

export default function DimensionCard({
  dimension,
  probe,
  onViewEvidence,
}: {
  dimension: FriesDimension;
  probe: ProbeEvidenceRead | undefined;
  onViewEvidence?: () => void;
}) {
  const status = displayStatusFor(probe);
  return (
    <div className="dimension-card">
      <div className="dimension-card-head">
        <span className="dimension-card-title">{DIMENSION_LABEL[dimension]}</span>
        <StatusPill status={status} title={probe?.status_reason ?? undefined} />
      </div>

      {!probe ? (
        <div className="dimension-note">Not run for this evaluation.</div>
      ) : (
        <>
          {dimension === "FAIRNESS" ? <FairnessBody probe={probe} /> : null}
          {dimension === "ROBUSTNESS" ? <RobustnessBody probe={probe} /> : null}
          {(dimension === "INTEGRITY" ||
            dimension === "EXPLAINABILITY" ||
            dimension === "SAFETY") && status !== "NOT_APPLICABLE" ? (
            <ChecksBody probe={probe} />
          ) : null}
          {(dimension === "EXPLAINABILITY" || dimension === "SAFETY") &&
          status !== "NOT_APPLICABLE" ? (
            <DocumentationCoverageRow probe={probe} />
          ) : null}
          {dimension === "EXPLAINABILITY" ? (
            <div className="dimension-note">
              Documentation coverage is not equivalent to explanation quality.
            </div>
          ) : null}
          {dimension === "SAFETY" ? (
            <div className="dimension-note">
              This is a governance/documentation disclosure checklist, not a runtime safety
              evaluation — it does not establish that the model is safe.
            </div>
          ) : null}

          {probe.confidence != null ? (
            <Row label="Evidence strength" value={probe.confidence.toFixed(2)} />
          ) : null}
          {probe.status_reason ? (
            <div className="dimension-note">{probe.status_reason}</div>
          ) : null}
          {probe.limitations?.length ? (
            <div className="dimension-limitations">
              <strong>Limitations:</strong> {probe.limitations.join("; ")}
            </div>
          ) : null}
        </>
      )}

      <div className="dimension-card-footer">
        <button
          type="button"
          className="btn btn-secondary"
          disabled={!probe || !onViewEvidence}
          onClick={onViewEvidence}
        >
          View evidence
        </button>
      </div>
    </div>
  );
}
