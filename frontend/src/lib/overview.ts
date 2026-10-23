import type { EvaluationRead } from "../api/types";
import { ACTIVE_STATUSES } from "../api/types";

export interface StatusCounts {
  awaiting: number;
  active: number;
  finalized: number;
  failed: number;
  /** Status this build doesn't recognise (newer backend) — never dropped from the total. */
  other: number;
  total: number;
}

/** Counts over the loaded page only. Every status maps to exactly one bucket. */
export function countStatuses(items: Pick<EvaluationRead, "status">[]): StatusCounts {
  const c: StatusCounts = { awaiting: 0, active: 0, finalized: 0, failed: 0, other: 0, total: items.length };
  for (const { status } of items) {
    if (status === "AWAITING_REVIEW") c.awaiting++;
    else if (ACTIVE_STATUSES.includes(status)) c.active++;
    else if (status === "FINALIZED") c.finalized++;
    else if (status === "FAILED") c.failed++;
    else c.other++;
  }
  return c;
}
