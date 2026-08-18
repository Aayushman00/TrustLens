import type { EvaluationStatus } from "../api/types";

export default function StatusBadge({ status }: { status: EvaluationStatus }) {
  return (
    <span className={`badge status-${status.toLowerCase()}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}
