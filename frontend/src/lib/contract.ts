/**
 * Read the frozen EvaluationContractV2 off an EvaluationRead.
 *
 * The backend persists it at `probe_config.evaluation_contract` (see
 * backend/app/services/evaluation_service_v2.py `create_from_draft`) rather
 * than as a dedicated typed API field — this reads the same raw JSON the
 * backend already returns, so it works for both list and detail responses.
 * An evaluation created via the bare `POST /v1/evaluations` path carries no
 * `evaluation_contract` at all — `getEvaluationContract` returns `null` for
 * those, same as it does for a malformed/absent value.
 */
import type { EvaluationRead } from "../api/types";

export interface EvaluationContractDimension {
  dataset_content_id: string;
  text_column: string;
  target_column: string;
  sensitive_column?: string;
}

export interface EvaluationContract {
  schema_version: "v2";
  model_ref: string;
  model_revision: string;
  fairness: EvaluationContractDimension | null;
  robustness: EvaluationContractDimension | null;
}

export function getEvaluationContract(
  evaluation: Pick<EvaluationRead, "probe_config">,
): EvaluationContract | null {
  const raw = evaluation.probe_config?.evaluation_contract;
  if (!raw || typeof raw !== "object") return null;
  const contract = raw as EvaluationContract;
  if (contract.schema_version !== "v2" || typeof contract.model_ref !== "string") {
    return null;
  }
  return contract;
}

/** User-facing label for which dimensions this contract configures. */
export function contractFamilyLabel(contract: EvaluationContract | null | undefined): string {
  if (!contract) return "Documentation & Governance";
  const hasFairness = contract.fairness != null;
  const hasRobustness = contract.robustness != null;
  if (hasFairness && hasRobustness) return "Fairness + Robustness";
  if (hasFairness) return "Fairness";
  if (hasRobustness) return "Robustness";
  return "Documentation & Governance";
}

/** Short, 8-char display revision — never fabricate a hash, just truncate. */
export function shortRevision(revision: string | null | undefined): string {
  if (!revision) return "unpinned";
  return revision.slice(0, 8);
}
