/**
 * Report-page helpers. All pure reshaping of already-persisted report_v1
 * fields — never a recomputation of any metric, score, or O/S/D value.
 */
import type { ProbeEvidenceRead, ReportProbe, ReportTraceabilityEntry } from "../api/types";

function str(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function bool(v: unknown): boolean | null {
  return typeof v === "boolean" ? v : null;
}

/**
 * Reshapes a report's ReportTraceabilityEntry + matching ReportProbe into
 * the same ProbeEvidenceRead shape EvaluationDetailPage's DimensionCard
 * already renders — so the Report page can reuse that exact component
 * instead of a second, parallel rendering of the same evidence.
 */
export function traceabilityEntryToProbeEvidence(
  entry: ReportTraceabilityEntry,
  probe: ReportProbe | undefined,
): ProbeEvidenceRead {
  const metrics = probe?.metric_values ?? null;
  return {
    dimension: entry.dimension,
    status: entry.status,
    status_reason: entry.status_reason,
    methodology_version: str(metrics?.methodology_version),
    gates: entry.gates,
    risks_triggered: entry.risks_triggered,
    aspect_scoring: entry.aspect_scoring,
    scored_risk_id: entry.scored_risk_id,
    claim_boundary:
      metrics?.claim_boundary && typeof metrics.claim_boundary === "object"
        ? (metrics.claim_boundary as Record<string, unknown>)
        : null,
    limitations: entry.limitations,
    flags: probe?.flags ?? null,
    coverage_ratio: entry.coverage_ratio,
    n_evaluated: num(metrics?.n_evaluated),
    fairness_mode: str(metrics?.fairness_mode),
    pairing_id: str(metrics?.pairing_id),
    confidence: entry.confidence,
    evidence_refs: entry.evidence_refs,
    model_ref: str(metrics?.model_ref),
    model_revision: str(metrics?.model_revision),
    dataset_key: str(metrics?.dataset_key),
    dataset_revision: str(metrics?.dataset_revision),
    evaluation_class: str(metrics?.evaluation_class),
    inference_executed: bool(metrics?.inference_executed),
    metric_values: metrics,
  };
}
