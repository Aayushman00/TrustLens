/**
 * Evaluation lifecycle timeline (Phase 4) — renders real, persisted
 * EvaluationEvent rows only. Never fabricates a step, a timestamp, or a
 * skeleton "Created → Running → Finalized" sequence when the backend has
 * recorded nothing (e.g. an evaluation created before this feature existed).
 * This is audit evidence, not a status indicator — evaluation status,
 * probe results, O/S/D, and FRIES remain sourced from their own existing
 * displays elsewhere on this page.
 */
import type { ReactNode } from "react";
import type { EvaluationEventRead } from "../api/types";
import { fmtTimeSeconds } from "../lib/format";

const EVENT_LABELS: Record<string, string> = {
  evaluation_created: "Evaluation created",
  evaluation_requeued: "Evaluation re-queued",
  evaluation_started: "Evaluation started",
  probes_completed: "Probes completed",
  agent_completed: "O/S/D representation proposed",
  evaluation_failed: "Evaluation failed",
  awaiting_review: "Awaiting human review",
  human_review_submitted: "Human review submitted",
  evaluation_finalized: "Evaluation finalized",
  report_generated: "Report generated",
};

export function gapLabel(prevIso: string, currIso: string): string | null {
  const prev = new Date(prevIso).getTime();
  const curr = new Date(currIso).getTime();
  if (Number.isNaN(prev) || Number.isNaN(curr)) return null;
  const diffMs = curr - prev;
  if (diffMs < 1000) return "same instant";
  const totalSeconds = Math.round(diffMs / 1000);
  if (totalSeconds < 60) return `+${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds === 0 ? `+${minutes}m` : `+${minutes}m ${seconds}s`;
}

export function attemptNumbers(events: EvaluationEventRead[]): number[] {
  const result: number[] = [];
  let attempt = 1;
  for (const evt of events) {
    result.push(attempt);
    if (evt.event_type === "evaluation_requeued") attempt += 1;
  }
  return result;
}

function labelFor(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType.replaceAll("_", " ");
}

function enqueueDetailSummary(detail: Record<string, unknown>): string | null {
  const enqueued = detail.enqueued;
  if (enqueued === false) {
    return "Not enqueued — the evaluation may be stuck at PENDING (no worker task was sent).";
  }
  return typeof detail.task_id === "string" ? `Task ${String(detail.task_id).slice(0, 12)}…` : null;
}

function detailSummary(eventType: string, detail: Record<string, unknown> | null): string | null {
  if (!detail) return null;
  switch (eventType) {
    case "evaluation_created":
    case "evaluation_requeued":
      return enqueueDetailSummary(detail);
    case "probes_completed":
      return typeof detail.probe_count === "number" ? `${detail.probe_count} probe(s) ran` : null;
    case "evaluation_failed":
      return typeof detail.reason_code === "string" ? `Reason: ${String(detail.reason_code).replaceAll("_", " ")}` : null;
    case "human_review_submitted": {
      const parts: string[] = [];
      if (detail.accept_all === true) parts.push("accepted as-is");
      if (detail.accept_all === false) parts.push("edited");
      if (detail.human_changed === true) parts.push("values changed");
      return parts.length ? parts.join(" · ") : null;
    }
    case "evaluation_finalized": {
      const withheld = detail.scoring_withheld;
      if (withheld === true) return "FRIES withheld — see evaluation for why.";
      if (withheld === false) return "FRIES scored — see the evaluation's own FRIES card for the number.";
      return null;
    }
    case "report_generated":
      return typeof detail.version === "number" ? `Version ${detail.version}` : null;
    default:
      return null;
  }
}

export default function EvaluationTimeline({
  events,
  live = false,
}: {
  events: EvaluationEventRead[] | null;
  live?: boolean;
}) {
  const liveBadge = live ? (
    <div className="live-badge">
      <span className="live-badge-dot" />
      Live — updating automatically
    </div>
  ) : null;

  if (events == null) {
    return (
      <>
        {liveBadge}
        <p className="muted">Loading timeline…</p>
      </>
    );
  }
  if (events.length === 0) {
    return (
      <>
        {liveBadge}
        <p className="empty">
          No recorded timeline events for this evaluation — either it predates event
          tracking, or it has not progressed yet.
        </p>
      </>
    );
  }

  const attempts = attemptNumbers(events);
  const showAttempts = attempts[attempts.length - 1] > 1;

  return (
    <>
      {liveBadge}
      <ol className="timeline-list" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {events.map((event, idx) => {
          const summary = detailSummary(event.event_type, event.detail);
          const gap = idx > 0 ? gapLabel(events[idx - 1].created_at, event.created_at) : null;
          const hasDetail = event.detail != null && Object.keys(event.detail).length > 0;
          const rows: ReactNode[] = [];

          if (showAttempts && (idx === 0 || attempts[idx] !== attempts[idx - 1])) {
            rows.push(
              <li key={`attempt-${attempts[idx]}`} className="timeline-attempt-divider">
                Attempt {attempts[idx]}
              </li>,
            );
          }

          rows.push(
            <li key={event.id} className="timeline-row">
              <span className="mono muted timeline-row-time">
                {fmtTimeSeconds(event.created_at)}
                {gap ? <span className="timeline-row-gap"> · {gap}</span> : null}
              </span>
              <span className="timeline-row-body">
                <strong>{labelFor(event.event_type)}</strong>
                {summary ? <span className="muted"> — {summary}</span> : null}
                {hasDetail ? (
                  <details className="timeline-row-details">
                    <summary>Details</summary>
                    <pre className="mono">{JSON.stringify(event.detail, null, 2)}</pre>
                  </details>
                ) : null}
              </span>
            </li>,
          );

          return rows;
        })}
      </ol>
    </>
  );
}
