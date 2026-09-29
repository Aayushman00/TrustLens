import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

import { aspectScore, checkWeights, friesTotal, isVeto, riskT } from "./scoring";

interface Vector { id: number; inputs: any; expected: any }
const vectors: Vector[] = JSON.parse(
  readFileSync(resolve(process.cwd(), "../shared/scoring/fixtures/fries_test_vectors.json"), "utf8"),
).test_cases;
const v = (id: number) => vectors.find((c) => c.id === id)!;

test("#1 single middling risk", () => {
  const { O, S, D } = v(1).inputs;
  expect(riskT(O, S, D)).toBeCloseTo(v(1).expected.Pi, 10);
  expect(aspectScore([{ O, S, D }])).toBeCloseTo(v(1).expected.aspect_Ti, 10);
});

test("#2 golden fairness risk", () => {
  const { O, S, D } = v(2).inputs;
  expect(riskT(O, S, D)).toBeCloseTo(v(2).expected.Pi_exact, 9);
});

test.each([3, 4])("#%i veto", (id) => {
  const { O, S, D } = v(id).inputs;
  expect(riskT(O, S, D)).toBe(0);
  expect(isVeto(O, S, D)).toBe(true);
});

test("#5 all tens", () => {
  expect(riskT(10, 10, 10)).toBe(10);
});

test("#6 two-risk aspect mean", () => {
  const [r1, r2] = v(6).inputs.risks;
  expect(riskT(r1.O, r1.S, r1.D)).toBeCloseTo(v(6).expected.Pi1_exact, 9);
  expect(riskT(r2.O, r2.S, r2.D)).toBeCloseTo(v(6).expected.Pi2_exact, 9);
  expect(Math.abs(aspectScore([r1, r2]) - v(6).expected.aspect_mean_paper)).toBeLessThan(0.01);
});

test("#7 full golden reference (Table 8)", () => {
  const { weights, risks } = v(7).inputs;
  const byAspect: Record<string, { O: number; S: number; D: number }[]> = {};
  for (const r of risks) (byAspect[r.aspect] ??= []).push(r);
  const scores = Object.fromEntries(Object.entries(byAspect).map(([k, rs]) => [k, aspectScore(rs)]));
  for (const [aspect, paper] of Object.entries(v(7).expected.aspect_scores_paper)) {
    expect(Math.abs(scores[aspect] - (paper as number))).toBeLessThan(0.01);
  }
  // fixture value is labelled "approx" (10 dp); exact is 5.048395215364…
  expect(friesTotal(scores, weights)).toBeCloseTo(v(7).expected.T_exact_approx, 6);
});

test.each([8, 9])("#%i weighted total", (id) => {
  const { Ti, wi } = v(id).inputs;
  const keys = ["FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY"];
  const scores = Object.fromEntries(keys.map((k, i) => [k, Ti[i]]));
  const weights = Object.fromEntries(keys.map((k, i) => [k, wi[i]]));
  expect(friesTotal(scores, weights)).toBeCloseTo(v(id).expected.T, 10);
});

test("#10 weight floor", () => {
  const w = { FAIRNESS: 0.25, ROBUSTNESS: 0.25, INTEGRITY: 0.25, EXPLAINABILITY: 0.25, SAFETY: v(10).inputs.omega_S };
  const check = checkWeights(w, Object.keys(w));
  expect(check.ok).toBe(v(10).expected.valid);
  expect(() => friesTotal({ FAIRNESS: 1, ROBUSTNESS: 1, INTEGRITY: 1, EXPLAINABILITY: 1, SAFETY: 1 }, w)).toThrow();
});

test("default weights are equal over PRESENT aspects (backend renormalisation)", () => {
  expect(friesTotal({ FAIRNESS: 8, ROBUSTNESS: 4 })).toBe(6);
});

test("keys are case-insensitive like the backend", () => {
  expect(friesTotal({ fairness: 5 }, { FAIRNESS: 1 })).toBe(5);
});

test("rejects non-integer or out-of-range components", () => {
  expect(() => riskT(11, 5, 5)).toThrow(RangeError);
  expect(() => riskT(4.5, 5, 5)).toThrow(RangeError);
  expect(() => riskT(-1, 5, 5)).toThrow(RangeError);
});

test("compound fixture values reproduce", () => {
  expect(riskT(6, 6, 8)).toBeCloseTo(6.6039, 4);
  expect(riskT(2, 2, 3)).toBeCloseTo(2.2894, 4);
  expect(riskT(1, 1, 2)).toBeCloseTo(1.2599, 4);
});
