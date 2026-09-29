import { rampColor } from "../ramp";

const NAMES = { O: "Occurrence", S: "Severity", D: "Detection" } as const;
const START = 135;
const SWEEP = 270;

export function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const at = (deg: number) => {
    const a = (deg * Math.PI) / 180;
    return `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`;
  };
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${at(startDeg)} A ${r} ${r} 0 ${large} 1 ${at(endDeg)}`;
}

/** Assessment-layer instrument. Inverted FMEA: higher = safer. */
export function Dial({ letter, value, source }: { letter: "O" | "S" | "D"; value: number | null; source?: string | null }) {
  const name = NAMES[letter];
  const end = value == null ? START : START + (SWEEP * Math.min(10, Math.max(0, value))) / 10;
  return (
    <div
      className="tl-dial"
      role="meter"
      aria-label={name}
      aria-valuemin={0}
      aria-valuemax={10}
      aria-valuenow={value ?? undefined}
      aria-valuetext={value == null ? `${name} unavailable` : `${name} ${value} of 10, higher is safer`}
    >
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <path d={arcPath(32, 32, 26, START, START + SWEEP)} className="tl-dial__track" />
        {Array.from({ length: 11 }, (_, i) => {
          const a = ((START + (SWEEP * i) / 10) * Math.PI) / 180;
          const inner = i % 5 === 0 ? 19 : 21;
          return (
            <line key={i} className="tl-dial__tick"
              x1={32 + inner * Math.cos(a)} y1={32 + inner * Math.sin(a)}
              x2={32 + 23 * Math.cos(a)} y2={32 + 23 * Math.sin(a)} />
          );
        })}
        {value != null && value > 0 && (
          <path d={arcPath(32, 32, 26, START, end)} className="tl-dial__arc"
            style={{ stroke: rampColor(value) }} data-testid="dial-arc" />
        )}
      </svg>
      <span className="tl-dial__letter" aria-hidden="true">{letter}</span>
      <span className="tl-dial__value num" aria-hidden="true">{value ?? "—"}</span>
      {source && <span className="tl-dial__source">{source}</span>}
    </div>
  );
}
