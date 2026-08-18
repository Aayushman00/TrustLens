/** Hand-written TS mirror of the backend Pydantic schemas (TrustLens 0.20.0). */

export type UserRole = "researcher" | "reviewer" | "admin";

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

// ---- auth ----

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserRead {
  id: number;
  email: string;
  role: UserRole;
}

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

// ---- evaluations ----

export interface EvaluationCreate {
  model_id: number;
  evaluation_mode: EvaluationMode;
  probe_config?: Record<string, unknown>;
  task?: string;
  dataset?: string;
  config?: string;
}

export interface ProbeProgress {
  completed: number;
  total: number;
}

export interface ConfidenceSummary {
  overall: number;
  by_dimension: Record<string, number>;
  method: string;
  proposed_calibration: boolean;
  note: string;
}

export interface OsdAspectSuggestion {
  aspect: FriesDimension;
  O: number;
  S: number;
  D: number;
  confidence: number;
  rationale: string | null;
}

/** osd_agent_outputs.ai_suggestion payload (schema osd-agent-v1). */
export interface OsdAiSuggestion {
  schema_version: string;
  methodology_status: string;
  model_ref: string;
  overall_confidence: number | null;
  aspects: OsdAspectSuggestion[];
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
}

export interface HumanReviewRead {
  id: number;
  evaluation_id: string;
  reviewer_id: number;
  human_changed: boolean;
  accept_all: boolean;
  approved_osd: Record<string, unknown>;
  review_rationale: string | null;
  notes: string | null;
  created_at: string;
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
  is_published: boolean;
  published_at: string | null;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  probe_progress?: ProbeProgress | null;
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
  O: number;
  S: number;
  D: number;
}

/** accept_all=true → omit aspects; accept_all=false → at least one aspect edit. */
export interface HumanReviewRequest {
  accept_all: boolean;
  aspects?: AspectOSDEdit[];
  notes?: string;
  review_rationale?: string;
}

// ---- reports ----

export interface ReportRead {
  evaluation_id: string;
  version: number;
  json_uri: string;
  json_hash: string;
  pdf_uri: string | null;
  pdf_hash: string | null;
  fries_score: number;
  mode_disclosure: ModeDisclosure;
  generated_at: string;
  report_json: Record<string, unknown>;
}

// ---- leaderboard ----

export interface LeaderboardReportRef {
  version: number;
  json_uri: string | null;
  pdf_uri: string | null;
}

export interface LeaderboardEntry {
  evaluation_id: string;
  model_id: number;
  hf_repo_id: string;
  model_revision: string | null;
  evaluation_mode: EvaluationMode;
  human_reviewed: boolean;
  task: string | null;
  dataset: string | null;
  config: string | null;
  trustlens_version: string | null;
  fries_score: number;
  overall_confidence: number | null;
  published_at: string | null;
  report: LeaderboardReportRef | null;
}

export interface LeaderboardList {
  items: LeaderboardEntry[];
  next_cursor: string | null;
  note: string | null;
}

// ---- errors ----

/** Backend error envelope (app/api/errors.py). */
export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}
