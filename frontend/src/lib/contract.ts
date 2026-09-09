/**
 * Read the frozen Phase 7 evaluation contract off an EvaluationRead.
 *
 * The backend persists it at `probe_config.evaluation_contract` (see
 * backend/app/services/evaluation_service.py `create_evaluation`) rather than
 * as a dedicated typed API field — this reads the same raw JSON the backend
 * already returns, so it works for both list and detail responses.
 */
import type { EvaluationContractV1, EvaluationRead } from "../api/types";

export function getEvaluationContract(
  evaluation: Pick<EvaluationRead, "probe_config">,
): EvaluationContractV1 | null {
  const raw = evaluation.probe_config?.evaluation_contract;
  if (!raw || typeof raw !== "object") return null;
  const contract = raw as EvaluationContractV1;
  if (typeof contract.kind !== "string" || typeof contract.model_ref !== "string") {
    return null;
  }
  return contract;
}

/** User-facing label for a contract kind — never the internal enum value. */
export function contractKindLabel(kind: EvaluationContractV1["kind"] | undefined | null): string {
  switch (kind) {
    case "pairing":
      return "Model-faithful";
    case "registry":
      return "Model-faithful";
    case "proxy_lr":
      return "Proxy evaluation";
    case "documentation_only":
      return "Documentation evaluation";
    case "user_dataset":
      return "User-defined local evaluation";
    default:
      return "Unknown";
  }
}

export function contractFamilyLabel(kind: EvaluationContractV1["kind"] | undefined | null): string {
  switch (kind) {
    case "pairing":
      return "Fairness";
    case "registry":
      return "Robustness";
    case "proxy_lr":
      return "Fairness (proxy)";
    case "documentation_only":
      return "Documentation & Governance";
    case "user_dataset":
      return "Fairness (local dataset)";
    default:
      return "Unknown";
  }
}

/** Short, 8-char display revision — never fabricate a hash, just truncate. */
export function shortRevision(revision: string | null | undefined): string {
  if (!revision) return "unpinned";
  return revision.slice(0, 8);
}
