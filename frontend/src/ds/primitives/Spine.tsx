import { fmtTimeSeconds } from "../../lib/format";

export type StageState = "done" | "current" | "pending" | "failed" | "not_required";
export interface SpineStage { key: string; label: string; state: StageState; at?: string | null; note?: string }

const WORD: Record<StageState, string> = {
  done: "Done", current: "Active", pending: "Pending", failed: "Failed", not_required: "Not required",
};
const GLYPH: Record<StageState, string> = {
  done: "✓", current: "●", pending: "○", failed: "✕", not_required: "—",
};

/** Pipeline spine. Presentational: stage states are derived elsewhere from
 * real backend state (deriveTheatre, Deliverable 4) — never invented here. */
export function Spine({ stages }: { stages: SpineStage[] }) {
  return (
    <ol className="tl-spine" aria-label="Evaluation pipeline">
      {stages.map((s) => (
        <li key={s.key} className="tl-spine__stage" data-state={s.state} aria-current={s.state === "current" ? "step" : undefined}>
          <span className="tl-spine__glyph" aria-hidden="true" data-pulse={s.state === "current" ? "" : undefined}>{GLYPH[s.state]}</span>
          <span className="tl-spine__label">{s.label}</span>
          <span className="tl-spine__state">{WORD[s.state]}</span>
          {s.at && <time dateTime={s.at} className="tl-spine__time num">{fmtTimeSeconds(s.at)}</time>}
          {s.note && <span className="tl-spine__note">{s.note}</span>}
        </li>
      ))}
    </ol>
  );
}
