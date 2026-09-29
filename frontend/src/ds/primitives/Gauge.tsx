import { ChartFrame } from "./ChartFrame";

export interface MetricCI { lower: number; upper: number; method?: string }

/** Backend CI shape: { ci_lower, ci_upper, method, B, point }. */
export function readCI(raw: unknown): MetricCI | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.ci_lower !== "number" || typeof r.ci_upper !== "number") return null;
  return { lower: r.ci_lower, upper: r.ci_upper, method: typeof r.method === "string" ? r.method : undefined };
}

const X0 = 8;
const X1 = 232;

/** Evidence-layer readout: neutral ink only, never the trust ramp. */
export function Gauge({ label, metricKey, value, min = 0, max = 1, ci = null, digits = 3 }: {
  label: string; metricKey: string; value: number | null;
  min?: number; max?: number; ci?: MetricCI | null; digits?: number;
}) {
  const x = (v: number) => X0 + ((Math.min(max, Math.max(min, v)) - min) / (max - min)) * (X1 - X0);
  const fmt = (v: number) => v.toFixed(digits);
  const summary =
    value == null
      ? `${label}: not reported.`
      : `${label}: ${fmt(value)} on a ${min} to ${max} scale` +
        (ci ? `, confidence interval ${fmt(ci.lower)} to ${fmt(ci.upper)}${ci.method ? ` (${ci.method})` : ""}.` : ".");
  const rows = [[metricKey, value == null ? "not reported" : fmt(value), ci ? fmt(ci.lower) : "—", ci ? fmt(ci.upper) : "—"]];
  return (
    <ChartFrame title={label} summary={summary} table={{ columns: ["metric", "value", "CI lower", "CI upper"], rows }}>
      <div className="tl-gauge">
        <svg viewBox="0 0 240 24" className="tl-gauge__svg" aria-hidden="true">
          <line x1={X0} x2={X1} y1={12} y2={12} className="tl-gauge__track" />
          {ci && value != null && (
            <rect x={x(ci.lower)} width={Math.max(1, x(ci.upper) - x(ci.lower))} y={8} height={8}
              className="tl-gauge__ci" data-testid="gauge-ci" />
          )}
          {value != null && (
            <line x1={x(value)} x2={x(value)} y1={3} y2={21} className="tl-gauge__mark" data-testid="gauge-mark" />
          )}
        </svg>
        <span className="tl-gauge__value num">{value == null ? "— not reported" : fmt(value)}</span>
        <code className="tl-gauge__key">{metricKey}</code>
      </div>
    </ChartFrame>
  );
}
