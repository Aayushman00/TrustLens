/** Hand-written TS mirror of the backend Pydantic schemas (TrustLens 0.20.1). */

export type EvaluationMode = "AI_ASSISTED" | "AI_AUTONOMOUS";

export type EvaluationStatus =
  | "PENDING"
  | "RUNNING"
  | "PROBES_COMPLETED"
  | "AGENT_COMPLETED"
  | "AWAITING_REVIEW"
  | "FINALIZED"
  | "FAILED";

export type FriesDimension =
  | "FAIRNESS"
  | "ROBUSTNESS"
  | "INTEGRITY"
  | "EXPLAINABILITY"
  | "SAFETY";

export const FRIES_DIMENSIONS: FriesDimension[] = [
  "FAIRNESS",
  "ROBUSTNESS",
  "INTEGRITY",
  "EXPLAINABILITY",
  "SAFETY",
];

/** Statuses that keep changing on their own — keep polling while in one of these. */
export const ACTIVE_STATUSES: EvaluationStatus[] = [
  "PENDING",
  "RUNNING",
  "PROBES_COMPLETED",
  "AGENT_COMPLETED",
];

// ---- models ----

export interface ModelRead {
  id: number;
  hf_repo_id: string;
  model_metadata: Record<string, unknown>;
  checksum: string | null;
  revision: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ModelList {
  items: ModelRead[];
  next_cursor: string | null;
}

/** POST /v1/models/import-hf — provide exactly one of repo_id / url. */
export interface ImportHfRequest {
  repo_id?: string;
  url?: string;
  revision?: string;
}

// ---- Phase 7 evaluation contract ----

/** Mirrors backend EvaluationContractV1 (backend/app/schemas/evaluation_contract.py). */
export type EvaluationContractKind =
  | "pairing"
  | "registry"
  | "proxy_lr"
  | "documentation_only"
  | "user_dataset";

export interface EvaluationContractV1 {
  schema_version: "v1";
  kind: EvaluationContractKind;
  pairing_id: string | null;
  dataset_key: string | null;
  dataset_revision: string | null;
  model_ref: string;
  model_revision: string;
  task_type: string | null;
  label_space: string[] | number[] | null;
  modality: string | null;
  input_adapter: string | null;
  /** kind="user_dataset" only — the user's own local Fairness dataset. */
  user_dataset_id: string | null;
  dataset_uri: string | null;
  dataset_content_hash: string | null;
  target_column: string | null;
  group_column: string | null;
  text_column: string | null;
}

// ---- user-defined local Fairness datasets ----

export interface UserDatasetColumn {
  name: string;
  inferred_type: "numeric" | "categorical" | "unknown";
}

export interface UserDatasetRead {
  id: string;
  filename: string;
  format: string;
  content_hash: string;
  row_count: number;
  size_bytes: number;
  columns: UserDatasetColumn[];
  status: string;
  status_reason: string | null;
  created_at: string;
}

export interface UserDatasetList {
  items: UserDatasetRead[];
}

export interface ObservedGroup {
  value: string;
  count: number;
}

export interface GroupDiscoveryRead {
  group_column: string;
  total_rows: number;
  observed_groups: ObservedGroup[];
  missing_count: number;
  missing_reasons: Record<string, number>;
}

/** GET /v1/models/{id}/evaluation-options — approved contracts for this model only. */
export interface FairnessContractOption {
  kind: "pairing";
  pairing_id: string;
  dataset_key: string;
  dataset_revision: string;
  task_type: string;
  label_space: string[] | number[] | null;
  modality: string;
  notes: string | null;
}

export interface RobustnessContractOption {
  kind: "registry";
  dataset_key: string;
  evaluation_domain: string;
  notes: string | null;
}

export type DocumentationType =
  | "model_card"
  | "readme"
  | "technical_report"
  | "safety_system_card"
  | "evaluation_report"
  | "research_paper"
  | "other";

export interface DocumentationSourceRead {
  id: number;
  model_id: number;
  source_kind: "huggingface_hub" | "user_supplied";
  documentation_type: string;
  url: string | null;
  title: string | null;
  description: string | null;
  documentation_revision: string | null;
  documentation_content_hash: string | null;
  retrieval_status: string;
  retrieval_error: string | null;
  content_length: number | null;
  source_model_ref: string;
  source_model_revision: string | null;
  created_at: string;
}

export interface DocumentationSourceList {
  items: DocumentationSourceRead[];
}

export interface UserDocumentationCreate {
  url: string;
  documentation_type: DocumentationType;
  title?: string | null;
  description?: string | null;
}

export interface EvaluationOptionsRead {
  model_id: number;
  hf_repo_id: string;
  model_revision: string | null;
  fairness: FairnessContractOption[];
  robustness: RobustnessContractOption[];
  documentation_only_available: boolean;
  proxy_lr_available: boolean;
}

// ---- evaluations ----

export interface EvaluationCreate {
  model_id: number;
  evaluation_mode: EvaluationMode;
  probe_config?: Record<string, unknown>;
  task?: string;
  dataset?: string;
  config?: string;
  /** Phase 7 contract selection — mutually exclusive; omit all for documentation_only. */
  pairing_id?: string;
  dataset_key?: string;
  contract_kind?: "proxy_lr";
  /** User-defined local Fairness dataset selection (kind="user_dataset"). */
  user_dataset_id?: string;
  target_column?: string;
  group_column?: string;
  text_column?: string;
  included_group_values?: string[];
}

export interface ProbeProgress {
  completed: number;
  total: number;
}

export interface ProbeEvidenceRead {
  dimension: FriesDimension;
  status: string | null;
  status_reason: string | null;
  methodology_version: string | null;
  gates: string[] | null;
  risks_triggered: string[] | null;
  aspect_scoring: string | null;
  scored_risk_id: string | null;
  claim_boundary: Record<string, unknown> | null;
  limitations: string[] | null;
  flags: string[] | null;
  coverage_ratio: number | null;
  n_evaluated: number | null;
  fairness_mode: string | null;
  pairing_id: string | null;
  confidence: number | null;
  evidence_refs: Record<string, unknown>[];
  /** Phase 7 evaluation-contract identity, surfaced from persisted evidence. */
  model_ref: string | null;
  model_revision: string | null;
  dataset_key: string | null;
  dataset_revision: string | null;
  evaluation_class: string | null;
  inference_executed: boolean | null;
  metric_values: Record<string, unknown> | null;
}

/** Semantic probe status values actually emitted by the backend (ProbeEvaluationStatus). */
export type ProbeStatusValue =
  | "EVALUATED"
  | "INSUFFICIENT_EVIDENCE"
  | "NOT_APPLICABLE"
  | "SKIPPED"
  | "FAILED"
  | "PROXY";

export interface ConfidenceSummary {
  overall: number;
  by_dimension: Record<string, number>;
  method: string;
  proposed_calibration: boolean;
  note: string;
}

export interface OsdAspectSuggestion {
  aspect: FriesDimension;
  O: number | null;
  S: number | null;
  D: number | null;
  O_source?: string;
  S_source?: string | null;
  D_source?: string;
  osd_metadata?: Record<string, unknown>;
  confidence: number;
  rationale: string | null;
}

/** osd_agent_outputs.ai_suggestion payload (schema osd-agent-v1). */
export interface OsdAiSuggestion {
  schema_version: string;
  methodology_status: string;
  assessment_engine?: string;
  model_ref: string;
  overall_confidence: number | null;
  aspects: OsdAspectSuggestion[];
  scoring_withheld?: boolean;
  scoring_complete?: boolean;
  note: string;
}

export interface OsdAgentRead {
  ai_suggestion: OsdAiSuggestion;
  ai_confidence: number | null;
  methodology_status: string;
  rationale: string | null;
}

export interface FinalScoreRead {
  fries_score: number;
  dimension_scores: Record<string, number>;
  overall_confidence: number | null;
  evaluation_mode: EvaluationMode;
  human_reviewed: boolean;
  disclaimer: string | null;
}

export interface ModeDisclosure {
  evaluation_mode: EvaluationMode;
  human_reviewed: boolean;
  disclaimer: string;
  methodology_status: string;
  assessment_engine?: string | null;
  scoring_withheld?: boolean | null;
  fries_status?: "scored" | "withheld" | "not_scored_yet" | null;
}

export interface HumanReviewRead {
  id: number;
  evaluation_id: string;
  human_changed: boolean;
  accept_all: boolean;
  approved_osd: Record<string, unknown>;
  review_rationale: string | null;
  notes: string | null;
  created_at: string;
}

export interface ExecutionMetadata {
  device?: string | null;
  device_name?: string | null;
  execution_device: string | null;
  gpu_available: boolean | null;
  gpu_name: string | null;
  cuda_available: boolean | null;
  inference_backend?: string | null;
  device_reason?: string | null;
  fallback_reason?: string | null;
}

// ---- evaluation events (Phase 4 — append-only lifecycle audit trail) ----
//
// This is audit evidence only, never a source of truth: evaluation status,
// probe results, O/S/D, and FRIES all live in their own existing structures
// (EvaluationRead.status, .probes, .osd_agent, .final_score). Nothing here
// should ever be used to derive any of those — only to show when a
// already-decided fact happened.

export type EvaluationEventType =
  | "evaluation_created"
  | "evaluation_started"
  | "probes_completed"
  | "agent_completed"
  | "evaluation_failed"
  | "awaiting_review"
  | "human_review_submitted"
  | "evaluation_finalized"
  | "report_generated";

export interface EvaluationEventRead {
  id: number;
  evaluation_id: string;
  // Plain string, not a strict union, on the read side — an evaluation
  // created by a later TrustLens version may emit an event_type this
  // frontend build doesn't recognize; render it generically rather than
  // failing to parse.
  event_type: string;
  created_at: string;
  detail: Record<string, unknown> | null;
}

export interface EvaluationEventList {
  items: EvaluationEventRead[];
}

export interface EvaluationRead {
  id: string;
  model_id: number;
  status: EvaluationStatus;
  evaluation_mode: EvaluationMode;
  probe_config: Record<string, unknown>;
  task: string | null;
  dataset: string | null;
  config: string | null;
  model_revision: string | null;
  trustlens_version: string | null;
  // Real device/GPU evidence captured once per run from whichever probe
  // actually invoked LocalHFBackend. Null when no probe ran inference
  // (e.g. documentation-only contract) — never a fabricated device.
  execution_metadata?: ExecutionMetadata | null;
  is_published: boolean;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  probe_progress?: ProbeProgress | null;
  probes?: ProbeEvidenceRead[] | null;
  confidence_summary?: ConfidenceSummary | null;
  osd_agent?: OsdAgentRead | null;
  final_score?: FinalScoreRead | null;
  mode_disclosure?: ModeDisclosure | null;
  human_review?: HumanReviewRead | null;
}

export interface EvaluationList {
  items: EvaluationRead[];
  next_cursor: string | null;
}

// ---- human review ----

export interface AspectOSDEdit {
  aspect: FriesDimension;
  O?: number;
  S?: number;
  D?: number;
}

/** accept_all=true → omit aspects; accept_all=false → at least one aspect edit. */
export interface HumanReviewRequest {
  accept_all: boolean;
  aspects?: AspectOSDEdit[];
  notes?: string;
  review_rationale?: string;
}

// ---- reports (report_v1 — Phase 5/6) ----
//
// Typed to match backend/app/schemas/reports.py exactly. Every field here is
// a read of an already-persisted value — the frontend must never recompute
// or re-derive any of these (see ReportPage.tsx's top-of-file note).

export interface ReportEvaluation {
  id: string;
  status: EvaluationStatus;
  evaluation_mode: EvaluationMode;
  model_ref: string;
  model_id: number;
  created_at: string;
  finalized_context: Record<string, unknown>;
}

export interface ReportScore {
  score_type: "original_FRIES";
  // null exactly when scoring_withheld is true — never a fabricated 0.
  fries_score: number | null;
  dimension_scores: Record<string, number>;
  finalized_osd: Record<string, unknown>;
  overall_confidence: number | null;
  scoring_withheld: boolean;
  note: string;
}

export interface ReportProbe {
  dimension: FriesDimension;
  metric_values: Record<string, unknown>;
  confidence: number | null;
  flags: string[];
  evidence_refs: Record<string, unknown>[];
}

export interface ReportExecutiveSummary {
  headline: string;
  bullets: string[];
}

/** conclusion -> risk/status -> gate/rule -> [metric stays in probes[]] ->
 * evidence -> human O/S/D -> FRIES, one entry per FRIES dimension. Every
 * field is copied from ProbeEvidenceRead / final_scores — never recomputed
 * here or in the backend builder that produced it. */
export interface ReportTraceabilityEntry {
  dimension: FriesDimension;
  status: string | null;
  status_reason: string | null;
  aspect_scoring: string | null;
  scored_risk_id: string | null;
  risks_triggered: string[] | null;
  gates: string[] | null;
  // Explainability/Safety only. Always "documentation coverage" — never an
  // "Explainability score".
  coverage_ratio: number | null;
  confidence: number | null;
  evidence_refs: Record<string, unknown>[];
  limitations: string[] | null;
  // Present only once settled (FRIES not withheld); null otherwise.
  human_osd: {
    O: number | null;
    S: number | null;
    D: number | null;
    O_source: string | null;
    S_source: string | null;
    D_source: string | null;
  } | null;
  // null exactly when FRIES is withheld for this evaluation.
  fries_dimension_score: number | null;
}

export interface ReportV1 {
  schema_version: "report_v1";
  report_version: number;
  generated_at: string;
  evaluation: ReportEvaluation;
  mode_disclosure: ModeDisclosure;
  score: ReportScore;
  confidence_summary: ConfidenceSummary | null;
  probes: ReportProbe[];
  osd_agent: OsdAiSuggestion | null;
  human_review: Record<string, unknown> | null;
  attack_flags: Record<string, unknown>[];
  executive_summary: ReportExecutiveSummary;
  evidence_traceability: ReportTraceabilityEntry[];
  // Real device/GPU evidence (Phase 1). Null when no probe ran local
  // inference for this evaluation — never fabricated.
  execution_environment: ExecutionMetadata | null;
  documentation_sources: DocumentationSourceRead[];
  reproducibility: Record<string, unknown>;
  limitations: string[];
}

export interface ReportRead {
  evaluation_id: string;
  version: number;
  json_uri: string;
  json_hash: string;
  pdf_uri: string | null;
  pdf_hash: string | null;
  // null exactly when FRIES is withheld — the report is still complete.
  fries_score: number | null;
  mode_disclosure: ModeDisclosure;
  generated_at: string;
  report_json: ReportV1;
}

// ---- errors ----

/** Backend error envelope (app/api/errors.py). */
export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}
