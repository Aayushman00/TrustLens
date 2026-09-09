/**
 * Evaluation lifecycle timeline (Phase 4) — renders real, persisted
 * EvaluationEvent rows only. Never fabricates a step, a timestamp, or a
 * skeleton "Created → Running → Finalized" sequence when the backend has
 * recorded nothing (e.g. an evaluation created before this feature existed).
 * This is audit evidence, not a status indicator — evaluation status,
 * probe results, O/S/D, and FRIES remain sourced from their own existing
 * displays elsewhere on this page.
 */
import type { EvaluationEventRead } from "../api/types";
import { fmtDateTime } from "../lib/format";

const EVENT_LABELS: Record<string, string> = {
  evaluation_created: "Evaluation created",
  evaluation_started: "Evaluation started",
  probes_completed: "Probes completed",
  agent_completed: "O/S/D representation proposed",
  evaluation_failed: "Evaluation failed",
  awaiting_review: "Awaiting human review",
  human_review_submitted: "Human review submitted",
  evaluation_finalized: "Evaluation finalized",
  report_generated: "Report generated",
};

function labelFor(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType.replaceAll("_", " ");
}

function detailSummary(eventType: string, detail: Record<string, unknown> | null): string | null {
  if (!detail) return null;
  switch (eventType) {
    case "evaluation_created": {
      const enqueued = detail.enqueued;
      if (enqueued === false) {
        return "Not enqueued — the evaluation may be stuck at PENDING (no worker task was sent).";
      }
      return typeof detail.task_id === "string" ? `Task ${String(detail.task_id).slice(0, 12)}…` : null;
    }
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

export default function EvaluationTimeline({ events }: { events: EvaluationEventRead[] | null }) {
  if (events == null) {
    return <p className="muted">Loading timeline…</p>;
  }
  if (events.length === 0) {
    return (
      <p className="empty">
        No recorded timeline events for this evaluation — either it predates event
        tracking, or it has not progressed yet.
      </p>
    );
  }
  return (
    <ol className="timeline-list" style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {events.map((event) => {
        const summary = detailSummary(event.event_type, event.detail);
        return (
          <li
            key={event.id}
            style={{
              display: "flex",
              gap: "0.75rem",
              padding: "0.35rem 0",
              borderBottom: "1px solid var(--border, #2a2a2a22)",
            }}
          >
            <span className="mono muted" style={{ fontSize: "0.78rem", minWidth: "9.5rem" }}>
              {fmtDateTime(event.created_at)}
            </span>
            <span style={{ flex: 1 }}>
              <strong>{labelFor(event.event_type)}</strong>
              {summary ? <span className="muted"> — {summary}</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
