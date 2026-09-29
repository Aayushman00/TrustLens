/** Trust ramp (spec §3.4). Returns a CSS colour that follows the active
 * theme, because anchors are CSS variables defined per theme in tokens.css. */

export const RAMP_ANCHORS = [0, 3, 5, 7, 8.5, 10] as const;

export function rampVar(anchor: number): string {
  return `var(--tl-ramp-${String(anchor).replace(".", "_")})`;
}

export function rampColor(value: number): string {
  if (!Number.isFinite(value)) throw new RangeError(`ramp value must be finite, got ${value}`);
  const v = Math.min(10, Math.max(0, value));
  for (let i = 0; i < RAMP_ANCHORS.length - 1; i++) {
    const lo = RAMP_ANCHORS[i];
    const hi = RAMP_ANCHORS[i + 1];
    if (v === lo) return rampVar(lo);
    if (v < hi) {
      const pct = ((v - lo) / (hi - lo)) * 100;
      return `color-mix(in oklch, ${rampVar(hi)} ${pct.toFixed(1)}%, ${rampVar(lo)})`;
    }
  }
  return rampVar(10);
}
