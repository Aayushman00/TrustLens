import { useId } from "react";
import { rampColor } from "../ramp";

const R = 42;
export const RING_CIRCUMFERENCE = 2 * Math.PI * R;

/** Score-layer ring. The rendered dashoffset IS the final state — CSS
 * transitions animate toward it, and reduced motion simply shows it. */
export function ScoreRing({ value, label, veto = false, proposed = false, size = "md" }: {
  value: number | null; label: string; veto?: boolean; proposed?: boolean; size?: "sm" | "md" | "lg";
}) {
  const hatchId = `tl-hatch-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  // Non-finite (NaN/Infinity) is treated exactly like null: unscored.
  const v = value != null && Number.isFinite(value) ? value : null;
  const clamped = v === null ? 0 : Math.min(10, Math.max(0, v));
  const offset = veto ? 0 : RING_CIRCUMFERENCE * (1 - clamped / 10);
  const state = v === null ? "unscored" : veto ? "veto" : proposed ? "proposed" : "final";
  const valuetext = v === null
    ? `${label}: not scored`
    : `${label}: ${v.toFixed(2)} of 10${veto ? ", vetoed — a component was rated 0" : ""}${proposed ? ", proposed — not final" : ""}`;
  return (
    <div
      className={`tl-ring tl-ring--${size}`}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={10}
      aria-valuenow={v ?? undefined}
      aria-valuetext={valuetext}
      data-state={state}
    >
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <defs>
          <pattern id={hatchId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="tl-ring__hatch" />
          </pattern>
        </defs>
        <circle cx="50" cy="50" r={R} className="tl-ring__track" />
        {v !== null && (
          <circle
            cx="50" cy="50" r={R}
            className="tl-ring__arc"
            strokeDasharray={RING_CIRCUMFERENCE.toFixed(3)}
            strokeDashoffset={offset.toFixed(3)}
            transform="rotate(-90 50 50)"
            style={{ stroke: veto ? `url(#${hatchId})` : rampColor(clamped) }}
            data-testid="ring-arc"
          />
        )}
      </svg>
      <span className="tl-ring__num tl-display" aria-hidden="true">{v === null ? "—" : v.toFixed(2)}</span>
      {veto && <span className="tl-ring__flag">VETO</span>}
      {proposed && !veto && <span className="tl-ring__flag">proposed</span>}
      {v === null && <span className="tl-ring__flag">not scored</span>}
    </div>
  );
}
