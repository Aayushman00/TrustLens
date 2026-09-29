import { useId, useState } from "react";
import { fmtTimeSeconds } from "../../lib/format";

export interface TimelineEvent { id: number; event_type: string; created_at: string; detail?: Record<string, unknown> | null }

/** The 10 types emitted today (backend/app/db/repositories/evaluation_event.py). */
export const EVENT_LABELS: Record<string, string> = {
  evaluation_created: "Evaluation created",
  evaluation_requeued: "Re-queued",
  evaluation_started: "Evaluation started",
  probes_completed: "Probes completed",
  agent_completed: "O/S/D proposal ready",
  evaluation_failed: "Evaluation failed",
  awaiting_review: "Awaiting human review",
  human_review_submitted: "Human review submitted",
  evaluation_finalized: "Evaluation finalized",
  report_generated: "Report generated",
};

export const eventLabel = (type: string): string => EVENT_LABELS[type] ?? type;

export function Timeline({ events, onSelect }: { events: TimelineEvent[]; onSelect?: (e: TimelineEvent) => void }) {
  const [filter, setFilter] = useState("all");
  const selectId = useId();
  if (events.length === 0) return <p className="tl-timeline__empty">No events recorded yet.</p>;

  const sorted = [...events].sort((a, b) => a.id - b.id);
  const t0 = Date.parse(sorted[0].created_at);
  const types = [...new Set(sorted.map((e) => e.event_type))];
  const shown = filter === "all" ? sorted : sorted.filter((e) => e.event_type === filter);
  const latest = sorted[sorted.length - 1];

  return (
    <div className="tl-timeline">
      <div className="tl-timeline__filter">
        <label htmlFor={selectId}>Filter</label>
        <select id={selectId} value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All events ({sorted.length})</option>
          {types.map((t) => <option key={t} value={t}>{eventLabel(t)}</option>)}
        </select>
      </div>
      {/* Live region announces only newly appended events — never re-reads the list on filter changes. */}
      <div role="log" aria-live="polite" className="tl-sr-only">Latest event: {eventLabel(latest.event_type)}</div>
      <ol className="tl-timeline__list" aria-label="Evaluation events">
        {shown.map((e) => {
          const delta = (Date.parse(e.created_at) - t0) / 1000;
          const body = (
            <>
              <span className="tl-timeline__node" data-kind={e.event_type === "evaluation_failed" ? "fail" : "ok"} aria-hidden="true" />
              <span className="tl-timeline__label">{eventLabel(e.event_type)}</span>
              <time dateTime={e.created_at} className="num">{fmtTimeSeconds(e.created_at)}</time>
              <span className="tl-timeline__delta num">+{delta.toFixed(1)}s</span>
            </>
          );
          return (
            <li key={e.id} className="tl-timeline__item">
              {onSelect ? <button type="button" className="tl-timeline__row" onClick={() => onSelect(e)}>{body}</button> : <div className="tl-timeline__row">{body}</div>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
