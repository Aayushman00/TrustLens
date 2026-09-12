export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Like fmtDateTime, but with second precision -- for views (the evaluation
 * timeline) where sub-minute gaps between events are meaningful and must be
 * visible, not rounded away. */
export function fmtTimeSeconds(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtNumber(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : value.toFixed(digits);
}

/** Render O/S/D for display. Null is unavailable, never blank or implied zero. */
export function fmtOsd(value: number | null | undefined): string {
  if (value == null) return "Unavailable";
  return String(value);
}

/**
 * Parse a review O/S/D field. Empty → null. Invalid / non-integer → null.
 * Does not coerce parse failures to 0 (FRIES veto).
 */
export function parseOsdInput(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  if (!/^-?\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || !Number.isInteger(value)) return null;
  if (value < 0 || value > 10) return null;
  return value;
}
