import { FRIES_DIMENSIONS, type FriesDimension } from "../../api/types";
import { DIMENSIONS } from "../dimensions";
import { ChartFrame } from "./ChartFrame";

export type PentagonScores = Partial<Record<FriesDimension, number | null>>;

const CX = 120;
const CY = 120;
const R = 92;

function polar(i: number, radius: number): [number, number] {
  const a = ((-90 + 72 * i) * Math.PI) / 180;
  return [CX + radius * Math.cos(a), CY + radius * Math.sin(a)];
}

export function vertex(i: number, v: number): [number, number] {
  return polar(i, (R * Math.min(10, Math.max(0, v))) / 10);
}

const fmtPt = ([x, y]: [number, number]) => `${x.toFixed(2)} ${y.toFixed(2)}`;

/** Closed path only when all five exist; otherwise only segments between
 * adjacent present vertices — an incomplete audit must LOOK incomplete. */
function shapePath(values: (number | null)[]): string {
  const pts = values.map((v, i) => (v == null || !Number.isFinite(v) ? null : vertex(i, v)));
  if (pts.every((p) => p !== null)) return `M ${pts.map((p) => fmtPt(p!)).join(" L ")} Z`;
  const segs: string[] = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    if (a && b) segs.push(`M ${fmtPt(a)} L ${fmtPt(b)}`);
  }
  return segs.join(" ");
}

export function Pentagon({ scores, ghost, title = "FRIES aspect scores" }: {
  scores: PentagonScores; ghost?: PentagonScores; title?: string;
}) {
  const values = FRIES_DIMENSIONS.map((d) => {
    const v = scores[d];
    return v == null || !Number.isFinite(v) ? null : v;
  });
  const complete = values.every((v) => v !== null);
  const summary =
    `${title}: ` +
    FRIES_DIMENSIONS.map((d, i) => `${DIMENSIONS[d].label} ${values[i] == null ? "not scored" : values[i]!.toFixed(2)}`).join("; ") +
    "." +
    (complete ? "" : " Missing dimensions are shown hollow and are not counted as zero.");
  const rows = FRIES_DIMENSIONS.map((d, i) => [DIMENSIONS[d].label, values[i] == null ? "not scored" : values[i]!.toFixed(4)]);

  return (
    <ChartFrame title={title} summary={summary} table={{ columns: ["Dimension", "Score (0–10)"], rows }}>
      <svg viewBox="0 0 240 240" className="tl-penta" aria-hidden="true" data-complete={complete}>
        {[2, 4, 6, 8, 10].map((level) => (
          <polygon key={level} className="tl-penta__grid"
            points={FRIES_DIMENSIONS.map((_, i) => vertex(i, level).map((n) => n.toFixed(2)).join(",")).join(" ")} />
        ))}
        {FRIES_DIMENSIONS.map((d, i) => {
          const [x, y] = vertex(i, 10);
          return <line key={d} x1={CX} y1={CY} x2={x} y2={y} className="tl-penta__axis" style={{ stroke: `var(${DIMENSIONS[d].cssVar})` }} />;
        })}
        {ghost && (
          <path d={shapePath(FRIES_DIMENSIONS.map((d) => ghost[d] ?? null))} className="tl-penta__ghost" data-testid="penta-ghost" />
        )}
        <path d={shapePath(values)} className={complete ? "tl-penta__shape tl-penta__shape--filled" : "tl-penta__shape"} data-testid="penta-shape" />
        {FRIES_DIMENSIONS.map((d, i) => {
          const v = values[i];
          const [x, y] = vertex(i, v ?? 10);
          return v == null
            ? <circle key={d} cx={x} cy={y} r={5} className="tl-penta__missing" data-missing={d} />
            : <circle key={d} cx={x} cy={y} r={3.5} className="tl-penta__dot" data-dim={d} />;
        })}
        {FRIES_DIMENSIONS.map((d, i) => {
          const [x, y] = polar(i, R * 1.18);
          return (
            <text key={d} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="tl-penta__label"
              style={{ fill: `var(${DIMENSIONS[d].cssVar})` }}>
              {DIMENSIONS[d].monogram}
            </text>
          );
        })}
      </svg>
    </ChartFrame>
  );
}
