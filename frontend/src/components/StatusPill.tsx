/**
 * Semantic dimension-status pill — distinct from EvaluationStatus (StatusBadge).
 *
 * These seven states are never collapsed into a generic color or "N/A":
 * Evaluated, Running, Not configured (NOT_APPLICABLE — the dimension wasn't
 * configured for this evaluation), Insufficient evidence (a genuinely
 * attempted-but-inconclusive result), Failed, Withheld, Proxy. See backend
 * ProbeEvaluationStatus (app/db/enums.py) plus the FRIES-withheld state,
 * which has no probe-level equivalent.
 */
import type { ProbeStatusValue } from "../api/types";

export type DisplayStatus = ProbeStatusValue | "RUNNING" | "WITHHELD";

const CONFIG: Record<DisplayStatus, { label: string; icon: string; cls: string }> = {
  EVALUATED: { label: "Evaluated", icon: "✓", cls: "status-pill-evaluated" },
  RUNNING: { label: "Running", icon: "●", cls: "status-pill-running" },
  NOT_APPLICABLE: { label: "Not configured", icon: "–", cls: "status-pill-not_applicable" },
  INSUFFICIENT_EVIDENCE: {
    label: "Insufficient evidence",
    icon: "!",
    cls: "status-pill-insufficient_evidence",
  },
  FAILED: { label: "Failed", icon: "✕", cls: "status-pill-failed" },
  WITHHELD: { label: "Withheld", icon: "■", cls: "status-pill-withheld" },
  PROXY: { label: "Proxy", icon: "~", cls: "status-pill-proxy" },
  SKIPPED: { label: "Skipped", icon: "–", cls: "status-pill-skipped" },
};

export function normalizeStatus(raw: string | null | undefined): DisplayStatus {
  if (!raw) return "NOT_APPLICABLE";
  const upper = raw.toUpperCase();
  if (upper in CONFIG) return upper as DisplayStatus;
  return "NOT_APPLICABLE";
}

export default function StatusPill({
  status,
  title,
}: {
  status: DisplayStatus | string | null | undefined;
  title?: string;
}) {
  const key = normalizeStatus(typeof status === "string" ? status : undefined);
  const entry = CONFIG[key] ?? { label: String(status ?? "Unknown"), icon: "?", cls: "status-pill-unknown" };
  return (
    <span className={`status-pill ${entry.cls}`} title={title}>
      <span className="status-pill-icon" aria-hidden="true">
        {entry.icon}
      </span>
      {entry.label}
    </span>
  );
}
