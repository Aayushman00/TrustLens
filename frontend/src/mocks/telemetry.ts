/**
 * PLACEHOLDER execution telemetry — TrustLens does not currently record
 * per-batch timing. Rendered only inside a collapsible panel with a MockTag,
 * never as the primary progress indicator (that's the real
 * probe_progress.completed/total from the API).
 *
 * `device` is intentionally NOT part of this mock — the real execution
 * device now comes from `EvaluationRead.execution_metadata` (persisted from
 * an actual probe's inference run). Never fabricate it here.
 */
export interface MockExecutionTelemetry {
  currentBatch: number;
  totalBatches: number;
  samplesPerBatch: number;
  msPerSample: number;
}

export const mockExecutionTelemetry: MockExecutionTelemetry = {
  currentBatch: 34,
  totalBatches: 50,
  samplesPerBatch: 10,
  msPerSample: 18.4,
};
