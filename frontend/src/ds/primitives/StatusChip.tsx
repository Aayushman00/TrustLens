type Tone = "ok" | "warn" | "muted" | "fail" | "info";

/** Semantic probe statuses the backend emits (ProbeStatusValue) plus the two
 * Theatre lane states. Shape + word first; colour is secondary. */
export const CHIP_STATUSES: Record<string, { glyph: string; word: string; tone: Tone }> = {
  EVALUATED: { glyph: "✓", word: "Evaluated", tone: "ok" },
  INSUFFICIENT_EVIDENCE: { glyph: "◐", word: "Insufficient evidence", tone: "warn" },
  NOT_APPLICABLE: { glyph: "⊘", word: "Not applicable", tone: "muted" },
  SKIPPED: { glyph: "⤼", word: "Skipped", tone: "muted" },
  FAILED: { glyph: "✕", word: "Failed", tone: "fail" },
  PROXY: { glyph: "≈", word: "Proxy", tone: "info" },
  AWAITING: { glyph: "○", word: "Awaiting evidence", tone: "muted" },
  NOT_PRODUCED: { glyph: "✕", word: "Not produced", tone: "fail" },
};

export function StatusChip({ status }: { status: string }) {
  const meta = CHIP_STATUSES[status] ?? { glyph: "?", word: status, tone: "muted" as Tone };
  return (
    <span className="tl-chip" data-tone={meta.tone}>
      <span className="tl-chip__glyph" aria-hidden="true">{meta.glyph}</span>
      {meta.word}
    </span>
  );
}
