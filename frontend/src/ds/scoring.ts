/** Display mirror of backend/app/scoring/fries.py. Used only for the Learn
 * page, what-if weight previews and proposed-value T — never to replace a
 * persisted final score. Verified against shared/scoring/fixtures. */

export interface OSD { O: number; S: number; D: number }
export type WeightCheck = { ok: true } | { ok: false; reason: string };

export const MIN_WEIGHT = 0.1;
const SUM_TOL = 1e-6;

function component(value: number, name: string): number {
  if (!Number.isInteger(value) || value < 0 || value > 10) {
    throw new RangeError(`${name} must be an integer 0..10, got ${value}`);
  }
  return value;
}

export function isVeto(O: number, S: number, D: number): boolean {
  return O === 0 || S === 0 || D === 0;
}

/** T = ∛(O·S·D); veto to 0 if any component is 0; all tens → exactly 10. */
export function riskT(O: number, S: number, D: number): number {
  const o = component(O, "O");
  const s = component(S, "S");
  const d = component(D, "D");
  if (isVeto(o, s, d)) return 0;
  if (o === 10 && s === 10 && d === 10) return 10;
  return Math.cbrt(o * s * d);
}

/** Aspect score = mean of its risks' T; no risks → 0 (backend behaviour). */
export function aspectScore(risks: OSD[]): number {
  if (risks.length === 0) return 0;
  return risks.reduce((sum, r) => sum + riskT(r.O, r.S, r.D), 0) / risks.length;
}

const upper = (m: Record<string, number>) =>
  Object.fromEntries(Object.entries(m).map(([k, v]) => [k.toUpperCase(), v]));

export function checkWeights(weights: Record<string, number>, aspects: string[]): WeightCheck {
  const w = upper(weights);
  const keys = aspects.map((a) => a.toUpperCase()).sort();
  if (JSON.stringify(Object.keys(w).sort()) !== JSON.stringify(keys)) {
    return { ok: false, reason: "weights must cover exactly the scored aspects" };
  }
  if (Object.values(w).some((x) => x < MIN_WEIGHT)) {
    return { ok: false, reason: `every weight must be >= ${MIN_WEIGHT}` };
  }
  const total = Object.values(w).reduce((a, b) => a + b, 0);
  if (Math.abs(total - 1) > SUM_TOL) return { ok: false, reason: `weights must sum to 1 (got ${total})` };
  return { ok: true };
}

/** T = Σ ωᵢ·Tᵢ. Default: equal weights over the aspects PRESENT. */
export function friesTotal(scores: Record<string, number>, weights?: Record<string, number>): number {
  const s = upper(scores);
  const keys = Object.keys(s);
  if (keys.length === 0) throw new RangeError("scores must not be empty");
  let w: Record<string, number>;
  if (weights === undefined) {
    w = Object.fromEntries(keys.map((k) => [k, 1 / keys.length]));
  } else {
    const check = checkWeights(weights, keys);
    if (!check.ok) throw new RangeError(check.reason);
    w = upper(weights);
  }
  return keys.reduce((sum, k) => sum + w[k] * s[k], 0);
}
