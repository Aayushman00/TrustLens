# TrustLens Design System (Tokens + Primitives + Gallery) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Deliverable 2 of the UI redesign — design tokens (both themes), 13 accessible primitives, and a `/gallery` living-docs page — without touching any existing page.

**Architecture:** All new code lives in `frontend/src/ds/`. Tokens are CSS custom properties prefixed `--tl-` and scoped to a `.tl` root class, so the legacy `index.css` pages keep rendering unchanged until Deliverable 3 migrates them. Primitives are hand-rolled React + SVG with zero new runtime libraries beyond self-hosted fonts. Display math (`riskT`, `friesTotal`) is a client mirror of `backend/app/scoring/fries.py`, verified against the frozen test vectors.

**Tech Stack:** React 19, TypeScript 5.7 (strict), Vite 6, vitest 5 + Testing Library + jsdom, `@fontsource-variable/fraunces`, `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono`.

**Spec:** `docs/superpowers/specs/2026-09-29-trustlens-ui-redesign-design.md` (§3–§7, §10, §11)

## Global Constraints

- Branch: `feat/ui-redesign`. All commands run from `frontend/` unless stated.
- Three layers never share visual material: **Evidence** = neutral ink + mono, never ramp colours; **Assessment** = dials, ramp on arcs/T only; **Score** = display serif + ramp + UV glow.
- UV accent `--tl-uv` is for interaction/attention only; it never encodes data.
- Dimension hues are identity only; always paired with glyph shape + monogram (● F, ■ R, ⬢ I, ◆ E, ▲ S).
- Null/missing is never rendered as `0`. Unscored = hollow/dashed + words ("not scored", "— not recorded", "Unavailable").
- Contrast: text pairs ≥ 4.5:1, non-text UI and ramp anchors ≥ 3:1 against `--tl-ink-0` and `--tl-ink-1`, in both themes.
- Motion tokens: micro 150 ms, std 240 ms, land 400 ms; only `transform`/`opacity`/`stroke-dashoffset` animate; `prefers-reduced-motion: reduce` **or** `data-motion="reduce"` sets all durations to 0 and stops pulses. Rendered SVG attributes are always the final state (no JS tweening).
- Numerals: `tabular-nums lining-nums` everywhere.
- No chart, animation, state, or virtualisation libraries. Fonts are self-hosted (no Google Fonts CDN).
- Every chart primitive: `aria-describedby` text summary + "Show as table" toggle.
- Do not modify existing pages/components or `src/index.css` in this deliverable.

## Review Focus

1. **Null / non-finite values** (`null`, `undefined`, `NaN` score, O/S/D, hash) → rendered as explicit "not scored / unavailable / not recorded", never `0` or `NaN`. Tests in Tasks 4, 6, 7.
2. **Unknown backend strings** (a newer backend emits an unrecognised `event_type` or probe status) → rendered verbatim, no crash. Tests in Tasks 3, 8.
3. **Clipboard unavailable** (`navigator.clipboard` undefined or rejects) → visible "Copy failed", not silent. Test in Task 4.
4. **Out-of-range numbers** (score 10.4 or −1, metric outside gauge range) → visuals clamp, numeral shows the true value. Tests in Tasks 2, 5, 6.
5. **Light theme + reduced motion** → every contrast pair re-checked for light; reduced motion leaves identical static end states. Tests in Tasks 1, 6, 10.

---

## File Structure

```
frontend/src/ds/
  tokens.css            # all --tl-* tokens, dark (.tl) + light (.tl[data-theme="light"]) + reduced-motion
  ds.css                # base .tl styles + one section per primitive (tl-* class prefix)
  fonts.ts              # self-hosted @fontsource imports
  tokens.test.ts        # WCAG contrast + ramp monotonicity, parsed from tokens.css
  dimensions.ts         # FRIES identity meta (label, monogram, shape, css var)
  ramp.ts               # trust ramp → CSS colour (color-mix between themed anchors)
  scoring.ts            # display mirror of backend fries.py
  scoring.test.ts       # frozen test vectors
  ramp.test.ts
  primitives/
    Card.tsx            # Card (chrome) + Slip (evidence paper)
    StatusChip.tsx
    DimensionMark.tsx   # DimensionGlyph + DimensionMark
    HashBadge.tsx       # shortHash + CopyButton + HashBadge
    EvidenceChip.tsx    # EvidenceRef + toEvidenceRef + EvidenceChip
    ChartFrame.tsx      # figure + sr summary + table toggle
    Gauge.tsx           # readCI + Gauge (evidence layer)
    Dial.tsx            # arcPath + Dial (assessment layer)
    ScoreRing.tsx       # score layer
    Pentagon.tsx        # score layer
    Spine.tsx
    Timeline.tsx
    TracePanel.tsx
    *.test.tsx          # one per primitive file
  gallery/
    GalleryPage.tsx
    GalleryPage.test.tsx
Modify:
  frontend/package.json        # 3 font deps
  frontend/vitest.config.ts    # include src/ds/**/*.test.ts
  frontend/src/App.tsx         # /gallery route (outside Layout)
```

---

### Task 1: Tokens, fonts, base styles, contrast test

**Files:**
- Create: `frontend/src/ds/tokens.css`, `frontend/src/ds/ds.css`, `frontend/src/ds/fonts.ts`, `frontend/src/ds/tokens.test.ts`
- Modify: `frontend/package.json`, `frontend/vitest.config.ts:17`

**Interfaces:**
- Produces: CSS vars `--tl-ink-0|1|2`, `--tl-line-1|2`, `--tl-text-1|2|3`, `--tl-uv`, `--tl-fail`, `--tl-dim-f|r|i|e|s`, `--tl-ramp-0|3|5|7|8_5|10`, `--tl-font-display|ui|mono`, `--tl-fs-*`, `--tl-s-1..12`, `--tl-r-slip|card|chip`, `--tl-dur-micro|std|land`, `--tl-ease-micro|spring|land`, `--tl-glow`. Classes `.tl`, `.tl-display`, `.num`, `.tl-sr-only`.

- [ ] **Step 1: Install fonts**

Run: `npm install @fontsource-variable/fraunces@^5.3.0 @fontsource/ibm-plex-sans@^5.3.0 @fontsource/ibm-plex-mono@^5.3.0`
Then: `ls node_modules/@fontsource-variable/fraunces/*.css`
Expected: list includes `full.css` (all axes incl. `opsz`, `SOFT`). If `full.css` is absent, use `index.css` in Step 6 and note it in the commit.

- [ ] **Step 2: Let vitest see `.test.ts` files under `ds/`**

In `frontend/vitest.config.ts` replace `include: ["src/**/*.test.tsx"],` with:

```ts
    include: ["src/**/*.test.tsx", "src/ds/**/*.test.ts"],
```

(`src/lib/format.test.ts` stays on `node:test`; the new glob is limited to `ds/` so it is not picked up twice.)

- [ ] **Step 3: Write the failing contrast test** — `frontend/src/ds/tokens.test.ts`

```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/ds/tokens.css"), "utf8");

function block(selector: RegExp): Record<string, string> {
  const match = css.match(selector);
  if (!match) throw new Error(`token block not found: ${selector}`);
  const out: Record<string, string> = {};
  for (const [, key, value] of match[1].matchAll(/(--tl-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    out[key] = value;
  }
  return out;
}

const dark = block(/\.tl\s*\{([^}]*)\}/);
const light = { ...dark, ...block(/\.tl\[data-theme="light"\]\s*\{([^}]*)\}/) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT = [
  "--tl-text-1", "--tl-text-2", "--tl-text-3", "--tl-uv", "--tl-fail",
  "--tl-dim-f", "--tl-dim-r", "--tl-dim-i", "--tl-dim-e", "--tl-dim-s",
];
const NON_TEXT = [
  "--tl-line-2", "--tl-ramp-0", "--tl-ramp-3", "--tl-ramp-5",
  "--tl-ramp-7", "--tl-ramp-8_5", "--tl-ramp-10",
];
const RAMP = NON_TEXT.slice(1);

for (const [name, theme] of [["dark", dark], ["light", light]] as const) {
  describe(`${name} theme contrast`, () => {
    for (const bg of ["--tl-ink-0", "--tl-ink-1"]) {
      test.each(TEXT)(`%s on ${bg} >= 4.5:1`, (fg) => {
        expect(ratio(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5);
      });
      test.each(NON_TEXT)(`%s on ${bg} >= 3:1`, (fg) => {
        expect(ratio(theme[fg], theme[bg])).toBeGreaterThanOrEqual(3);
      });
    }
  });
}

test("dark ramp luminance strictly increases (trust glows)", () => {
  const l = RAMP.map((k) => luminance(dark[k]));
  l.slice(1).forEach((v, i) => expect(v).toBeGreaterThan(l[i]));
});

test("light ramp luminance strictly decreases (trust = deeper ink)", () => {
  const l = RAMP.map((k) => luminance(light[k]));
  l.slice(1).forEach((v, i) => expect(v).toBeLessThan(l[i]));
});
```

- [ ] **Step 4: Run it — expect FAIL**

Run: `npx vitest run src/ds/tokens.test.ts`
Expected: FAIL — `ENOENT ... src/ds/tokens.css`.

- [ ] **Step 5: Create `frontend/src/ds/tokens.css`**

```css
/* TrustLens design tokens (spec §3–§6). Scoped to .tl so legacy pages that
   use src/index.css are untouched until they are migrated. Dark is primary. */
.tl {
  color-scheme: dark;
  --tl-ink-0: #0B0D12;
  --tl-ink-1: #12151C;
  --tl-ink-2: #1A1E27;
  --tl-line-1: #262C38;
  --tl-line-2: #606A7E;
  --tl-text-1: #E8EAF0;
  --tl-text-2: #A3ABBA;
  --tl-text-3: #7A8394;
  --tl-uv: #A594FF;
  --tl-fail: #FF8A7A;
  --tl-dim-f: #E6A23C;
  --tl-dim-r: #5DB8EC;
  --tl-dim-i: #E57A5A;
  --tl-dim-e: #D286B6;
  --tl-dim-s: #35C29A;
  --tl-ramp-0: #5E7AB0;
  --tl-ramp-3: #7D8290;
  --tl-ramp-5: #8E8A7E;
  --tl-ramp-7: #A89A70;
  --tl-ramp-8_5: #C6AE5E;
  --tl-ramp-10: #F2D65A;
  --tl-glow: 0 0 32px rgb(165 148 255 / 0.18);

  --tl-font-display: "Fraunces Variable", Georgia, serif;
  --tl-font-ui: "IBM Plex Sans", system-ui, sans-serif;
  --tl-font-mono: "IBM Plex Mono", ui-monospace, monospace;
  --tl-fs-12: 0.75rem;
  --tl-fs-14: 0.875rem;
  --tl-fs-16: 1rem;
  --tl-fs-20: 1.25rem;
  --tl-fs-25: 1.5625rem;
  --tl-fs-31: 1.9375rem;
  --tl-fs-39: 2.4375rem;
  --tl-fs-49: 3.0625rem;
  --tl-fs-61: 3.8125rem;
  --tl-fs-76: 4.75rem;

  --tl-s-1: 4px;
  --tl-s-2: 8px;
  --tl-s-3: 12px;
  --tl-s-4: 16px;
  --tl-s-5: 24px;
  --tl-s-6: 32px;
  --tl-s-7: 40px;
  --tl-s-8: 48px;
  --tl-s-9: 64px;
  --tl-s-10: 80px;
  --tl-s-11: 96px;
  --tl-s-12: 128px;
  --tl-r-slip: 2px;
  --tl-r-card: 8px;
  --tl-r-chip: 999px;

  --tl-dur-micro: 150ms;
  --tl-dur-std: 240ms;
  --tl-dur-land: 400ms;
  --tl-ease-micro: cubic-bezier(0.2, 0, 0, 1);
  /* critically damped spring */
  --tl-ease-spring: linear(0, 0.25 8%, 0.53 18%, 0.76 30%, 0.9 44%, 0.97 60%, 1);
  /* landing spring, overshoot <= 4% */
  --tl-ease-land: linear(0, 0.3 8%, 0.62 18%, 0.88 30%, 1.02 44%, 1.04 54%, 1.01 72%, 1);
}

.tl[data-theme="light"] {
  color-scheme: light;
  --tl-ink-0: #F6F5F1;
  --tl-ink-1: #FFFFFF;
  --tl-ink-2: #EFEDE7;
  --tl-line-1: #D9D7D0;
  --tl-line-2: #7E8490;
  --tl-text-1: #14161B;
  --tl-text-2: #4A5160;
  --tl-text-3: #636B7A;
  --tl-uv: #5B45E0;
  --tl-fail: #B42318;
  --tl-dim-f: #9A5F00;
  --tl-dim-r: #0A6AA6;
  --tl-dim-i: #B0452A;
  --tl-dim-e: #A0467F;
  --tl-dim-s: #0B7F5E;
  --tl-ramp-0: #6F86B8;
  --tl-ramp-3: #7A7F8C;
  --tl-ramp-5: #807A62;
  --tl-ramp-7: #86743A;
  --tl-ramp-8_5: #8A6F1C;
  --tl-ramp-10: #7A5C00;
  --tl-glow: 0 0 24px rgb(91 69 224 / 0.12);
}

@media (prefers-reduced-motion: reduce) {
  .tl {
    --tl-dur-micro: 0ms;
    --tl-dur-std: 0ms;
    --tl-dur-land: 0ms;
  }
}

.tl[data-motion="reduce"] {
  --tl-dur-micro: 0ms;
  --tl-dur-std: 0ms;
  --tl-dur-land: 0ms;
}
```

- [ ] **Step 6: Create `frontend/src/ds/fonts.ts`**

```ts
// Self-hosted (local-first): no runtime request to a font CDN.
import "@fontsource-variable/fraunces/full.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
```

- [ ] **Step 7: Create `frontend/src/ds/ds.css` (base section; later tasks append sections)**

```css
/* ---- base ---- */
.tl {
  background: var(--tl-ink-0);
  color: var(--tl-text-1);
  font-family: var(--tl-font-ui);
  font-size: var(--tl-fs-16);
  line-height: 1.5;
  font-variant-numeric: tabular-nums lining-nums;
  -webkit-font-smoothing: antialiased;
}
.tl *, .tl *::before, .tl *::after { box-sizing: border-box; }
.tl code, .tl .num, .tl .mono {
  font-family: var(--tl-font-mono);
  font-variant-numeric: tabular-nums lining-nums;
}
.tl .tl-display {
  font-family: var(--tl-font-display);
  font-variation-settings: "opsz" 72, "SOFT" 30;
  font-weight: 500;
  letter-spacing: -0.01em;
}
.tl :focus-visible { outline: 2px solid var(--tl-uv); outline-offset: 2px; }
.tl button {
  font: inherit;
  color: inherit;
  background: none;
  border: 1px solid var(--tl-line-2);
  border-radius: var(--tl-r-card);
  padding: var(--tl-s-1) var(--tl-s-3);
  cursor: pointer;
  transition: border-color var(--tl-dur-micro) var(--tl-ease-micro),
    background-color var(--tl-dur-micro) var(--tl-ease-micro);
}
.tl button:hover { border-color: var(--tl-uv); }
.tl button[aria-pressed="true"] {
  background: color-mix(in oklch, var(--tl-uv) 18%, transparent);
  border-color: var(--tl-uv);
}
.tl-sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
@keyframes tl-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
.tl [data-pulse] { animation: tl-pulse 2s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) { .tl [data-pulse] { animation: none; } }
.tl[data-motion="reduce"] [data-pulse] { animation: none; }
```

- [ ] **Step 8: Run test — expect PASS**

Run: `npx vitest run src/ds/tokens.test.ts`
Expected: PASS (all dark + light pairs, both monotonicity tests).

- [ ] **Step 9: Typecheck + commit**

Run: `npx tsc -b` → no errors.

```bash
git add package.json package-lock.json vitest.config.ts src/ds/tokens.css src/ds/ds.css src/ds/fonts.ts src/ds/tokens.test.ts
git commit -m "feat(ds): design tokens, self-hosted fonts, contrast-verified palette"
```

---

### Task 2: Dimension meta, trust ramp, scoring display math

**Files:**
- Create: `frontend/src/ds/dimensions.ts`, `frontend/src/ds/ramp.ts`, `frontend/src/ds/ramp.test.ts`, `frontend/src/ds/scoring.ts`, `frontend/src/ds/scoring.test.ts`

**Interfaces:**
- Consumes: `FriesDimension`, `FRIES_DIMENSIONS` from `src/api/types.ts`.
- Produces:
  - `DIMENSIONS: Record<FriesDimension, DimensionMeta>`; `DimensionMeta = { key; label; monogram; shape: "circle"|"square"|"hexagon"|"diamond"|"triangle"; cssVar: string }`
  - `RAMP_ANCHORS: readonly number[]`, `rampVar(anchor: number): string`, `rampColor(value: number): string`
  - `riskT(O, S, D): number`, `isVeto(O, S, D): boolean`, `aspectScore(risks: OSD[]): number`, `checkWeights(weights, aspects): WeightCheck`, `friesTotal(scores, weights?): number`; `OSD = { O: number; S: number; D: number }`; `WeightCheck = { ok: true } | { ok: false; reason: string }`

- [ ] **Step 1: Write failing scoring test** — `frontend/src/ds/scoring.test.ts`

```ts
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
```

- [ ] **Step 2: Write failing ramp test** — `frontend/src/ds/ramp.test.ts`

```ts
import { expect, test } from "vitest";
import { rampColor, rampVar, RAMP_ANCHORS } from "./ramp";

test("anchors map to their css variable", () => {
  expect(RAMP_ANCHORS).toEqual([0, 3, 5, 7, 8.5, 10]);
  expect(rampVar(8.5)).toBe("var(--tl-ramp-8_5)");
  expect(rampColor(0)).toBe("var(--tl-ramp-0)");
  expect(rampColor(10)).toBe("var(--tl-ramp-10)");
});

test("between anchors mixes in oklch", () => {
  expect(rampColor(4)).toBe("color-mix(in oklch, var(--tl-ramp-5) 50.0%, var(--tl-ramp-3))");
});

test("out of range clamps", () => {
  expect(rampColor(-1)).toBe("var(--tl-ramp-0)");
  expect(rampColor(10.4)).toBe("var(--tl-ramp-10)");
});

test("non-finite throws (callers must treat as unscored)", () => {
  expect(() => rampColor(Number.NaN)).toThrow(RangeError);
});
```

- [ ] **Step 3: Run — expect FAIL**

Run: `npx vitest run src/ds/scoring.test.ts src/ds/ramp.test.ts`
Expected: FAIL — cannot resolve `./scoring` / `./ramp`.

- [ ] **Step 4: Create `frontend/src/ds/scoring.ts`**

```ts
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
```

- [ ] **Step 5: Create `frontend/src/ds/ramp.ts`**

```ts
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
```

- [ ] **Step 6: Create `frontend/src/ds/dimensions.ts`**

```ts
import type { FriesDimension } from "../api/types";

export interface DimensionMeta {
  key: FriesDimension;
  label: string;
  monogram: string;
  shape: "circle" | "square" | "hexagon" | "diamond" | "triangle";
  cssVar: string;
}

/** Identity only — a hue says WHICH dimension, never how good. */
export const DIMENSIONS: Record<FriesDimension, DimensionMeta> = {
  FAIRNESS: { key: "FAIRNESS", label: "Fairness", monogram: "F", shape: "circle", cssVar: "--tl-dim-f" },
  ROBUSTNESS: { key: "ROBUSTNESS", label: "Robustness", monogram: "R", shape: "square", cssVar: "--tl-dim-r" },
  INTEGRITY: { key: "INTEGRITY", label: "Integrity", monogram: "I", shape: "hexagon", cssVar: "--tl-dim-i" },
  EXPLAINABILITY: { key: "EXPLAINABILITY", label: "Explainability", monogram: "E", shape: "diamond", cssVar: "--tl-dim-e" },
  SAFETY: { key: "SAFETY", label: "Safety", monogram: "S", shape: "triangle", cssVar: "--tl-dim-s" },
};
```

- [ ] **Step 7: Run — expect PASS**

Run: `npx vitest run src/ds/scoring.test.ts src/ds/ramp.test.ts`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ds/dimensions.ts src/ds/ramp.ts src/ds/ramp.test.ts src/ds/scoring.ts src/ds/scoring.test.ts
git commit -m "feat(ds): dimension identity, themed trust ramp, scoring mirror verified on test vectors"
```

---

### Task 3: Card, Slip, StatusChip, DimensionMark

**Files:**
- Create: `frontend/src/ds/primitives/Card.tsx`, `StatusChip.tsx`, `DimensionMark.tsx`, `Card.test.tsx`, `StatusChip.test.tsx`, `DimensionMark.test.tsx`
- Modify: `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Consumes: `DIMENSIONS` (Task 2).
- Produces: `Card({title?, actions?, children})`, `Slip({label?, children})`, `StatusChip({status: string})`, `CHIP_STATUSES`, `DimensionGlyph({dimension, size?})`, `DimensionMark({dimension, showLabel?})`.

- [ ] **Step 1: Failing tests**

`frontend/src/ds/primitives/Card.test.tsx`
```tsx
import { render, screen } from "@testing-library/react";
import { Card, Slip } from "./Card";

test("Card renders a titled section", () => {
  render(<Card title="Probe lanes">body</Card>);
  expect(screen.getByRole("heading", { name: "Probe lanes" })).toBeInTheDocument();
  expect(screen.getByText("body")).toBeInTheDocument();
});

test("Slip is evidence material with a label", () => {
  const { container } = render(<Slip label="metric_values">0.368</Slip>);
  expect(container.querySelector(".tl-slip")).not.toBeNull();
  expect(screen.getByText("metric_values")).toBeInTheDocument();
});
```

`frontend/src/ds/primitives/StatusChip.test.tsx`
```tsx
import { render, screen } from "@testing-library/react";
import { CHIP_STATUSES, StatusChip } from "./StatusChip";

test.each(Object.entries(CHIP_STATUSES))("%s shows its word, not just colour", (status, meta) => {
  render(<StatusChip status={status} />);
  expect(screen.getByText(meta.word)).toBeInTheDocument();
});

test("unknown backend status renders verbatim", () => {
  render(<StatusChip status="QUARANTINED" />);
  expect(screen.getByText("QUARANTINED")).toBeInTheDocument();
});
```

`frontend/src/ds/primitives/DimensionMark.test.tsx`
```tsx
import { render, screen } from "@testing-library/react";
import { FRIES_DIMENSIONS } from "../../api/types";
import { DIMENSIONS } from "../dimensions";
import { DimensionMark } from "./DimensionMark";

test.each(FRIES_DIMENSIONS)("%s shows monogram + label", (d) => {
  render(<DimensionMark dimension={d} />);
  expect(screen.getByText(DIMENSIONS[d].monogram)).toBeInTheDocument();
  expect(screen.getByText(DIMENSIONS[d].label)).toBeInTheDocument();
});

test("label-less mark still has an accessible name", () => {
  render(<DimensionMark dimension="SAFETY" showLabel={false} />);
  expect(screen.getByRole("img", { name: "Safety" })).toBeInTheDocument();
});

test("each dimension has a distinct glyph shape", () => {
  const shapes = FRIES_DIMENSIONS.map((d) => DIMENSIONS[d].shape);
  expect(new Set(shapes).size).toBe(5);
});
```

- [ ] **Step 2: Run — expect FAIL** (`npx vitest run src/ds/primitives`) — modules not found.

- [ ] **Step 3: Implement**

`frontend/src/ds/primitives/Card.tsx`
```tsx
import type { ReactNode } from "react";

/** Structural chrome. Not a data layer — use Slip for evidence. */
export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="tl-card">
      {(title || actions) && (
        <header className="tl-card__head">
          {title && <h3 className="tl-card__title">{title}</h3>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/** Evidence material: hairline "specimen paper". Never takes score colours. */
export function Slip({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="tl-slip">
      {label && <div className="tl-slip__label">{label}</div>}
      {children}
    </div>
  );
}
```

`frontend/src/ds/primitives/StatusChip.tsx`
```tsx
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
```

`frontend/src/ds/primitives/DimensionMark.tsx`
```tsx
import type { CSSProperties } from "react";
import type { FriesDimension } from "../../api/types";
import { DIMENSIONS } from "../dimensions";

const SHAPES = {
  circle: <circle cx="8" cy="8" r="6" />,
  square: <rect x="2.5" y="2.5" width="11" height="11" />,
  hexagon: <polygon points="8,1.5 13.6,4.75 13.6,11.25 8,14.5 2.4,11.25 2.4,4.75" />,
  diamond: <polygon points="8,1.5 14.5,8 8,14.5 1.5,8" />,
  triangle: <polygon points="8,2 14.5,13.5 1.5,13.5" />,
};

export function DimensionGlyph({ dimension, size = 16 }: { dimension: FriesDimension; size?: number }) {
  return (
    <svg className="tl-dim__glyph" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
      {SHAPES[DIMENSIONS[dimension].shape]}
    </svg>
  );
}

export function DimensionMark({ dimension, showLabel = true }: { dimension: FriesDimension; showLabel?: boolean }) {
  const meta = DIMENSIONS[dimension];
  const style = { "--tl-dim-c": `var(${meta.cssVar})` } as CSSProperties;
  return (
    <span
      className="tl-dim"
      style={style}
      {...(showLabel ? {} : { role: "img", "aria-label": meta.label })}
    >
      <DimensionGlyph dimension={dimension} />
      <span className="tl-dim__mono" aria-hidden={showLabel ? undefined : true}>{meta.monogram}</span>
      {showLabel && <span className="tl-dim__label">{meta.label}</span>}
    </span>
  );
}
```

Append to `frontend/src/ds/ds.css`:
```css
/* ---- Card / Slip ---- */
.tl-card {
  background: var(--tl-ink-1);
  border: 1px solid var(--tl-line-1);
  border-radius: var(--tl-r-card);
  padding: var(--tl-s-5);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 0.03);
}
.tl-card__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--tl-s-3); margin-bottom: var(--tl-s-4); }
.tl-card__title { margin: 0; font-size: var(--tl-fs-14); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--tl-text-2); }
.tl-slip {
  border: 1px solid var(--tl-line-1);
  border-radius: var(--tl-r-slip);
  padding: var(--tl-s-2) var(--tl-s-3);
  font-family: var(--tl-font-mono);
  font-size: var(--tl-fs-14);
  color: var(--tl-text-1);
  background: transparent;
}
.tl-slip__label { font-size: var(--tl-fs-12); color: var(--tl-text-3); margin-bottom: var(--tl-s-1); }

/* ---- StatusChip ---- */
.tl-chip {
  display: inline-flex; align-items: center; gap: var(--tl-s-1);
  padding: 2px var(--tl-s-2);
  border: 1px solid var(--tl-line-2);
  border-radius: var(--tl-r-chip);
  font-size: var(--tl-fs-12);
  color: var(--tl-text-2);
}
.tl-chip[data-tone="ok"] { color: var(--tl-text-1); }
.tl-chip[data-tone="fail"] { color: var(--tl-fail); border-color: var(--tl-fail); }
.tl-chip[data-tone="warn"] { border-style: dashed; color: var(--tl-text-1); }
.tl-chip__glyph { font-size: 0.9em; }

/* ---- DimensionMark ---- */
.tl-dim { display: inline-flex; align-items: center; gap: var(--tl-s-1); color: var(--tl-dim-c); }
.tl-dim__glyph { fill: none; stroke: currentColor; stroke-width: 1.6; }
.tl-dim__mono { font-family: var(--tl-font-mono); font-weight: 500; font-size: var(--tl-fs-12); }
.tl-dim__label { color: var(--tl-text-1); }
```

- [ ] **Step 4: Run — expect PASS** (`npx vitest run src/ds/primitives`).

- [ ] **Step 5: Commit**

```bash
git add src/ds/primitives/Card.tsx src/ds/primitives/Card.test.tsx src/ds/primitives/StatusChip.tsx src/ds/primitives/StatusChip.test.tsx src/ds/primitives/DimensionMark.tsx src/ds/primitives/DimensionMark.test.tsx src/ds/ds.css
git commit -m "feat(ds): Card, Slip, StatusChip, DimensionMark primitives"
```

---

### Task 4: HashBadge, EvidenceChip

**Files:**
- Create: `frontend/src/ds/primitives/HashBadge.tsx`, `EvidenceChip.tsx`, `HashBadge.test.tsx`, `EvidenceChip.test.tsx`
- Modify: `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Produces: `shortHash(hash: string): string`, `HashBadge({hash: string|null|undefined, label?: string})`, `EvidenceRef` interface `{ evidence_id, hash, uri, content_type, probe_name, created_at }` (all `string | null`), `toEvidenceRef(raw: Record<string, unknown>): EvidenceRef`, `EvidenceChip({evidence: EvidenceRef, onTrace?: (e: EvidenceRef) => void})`.

- [ ] **Step 1: Failing tests**

`frontend/src/ds/primitives/HashBadge.test.tsx`
```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { HashBadge, shortHash } from "./HashBadge";

const FULL = "sha256:86ad1cd39099df1de8ddc73c2af90c53a60de07e9cff1d081dc782922b5ca149";

function mockClipboard(writeText: (t: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

test("shortHash keeps first 8 and last 4 of the digest", () => {
  expect(shortHash(FULL)).toBe("86ad1cd3…a149");
  expect(shortHash("local")).toBe("local");
});

test("null hash says not recorded and offers no copy", () => {
  render(<HashBadge hash={null} />);
  expect(screen.getByText("— not recorded")).toBeInTheDocument();
  expect(screen.queryByRole("button")).toBeNull();
});

test("full hash is exposed to assistive tech", () => {
  render(<HashBadge hash={FULL} label="evidence hash" />);
  expect(screen.getByLabelText(`evidence hash ${FULL}`)).toBeInTheDocument();
});

test("copy writes the full hash and confirms", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  mockClipboard(writeText);
  render(<HashBadge hash={FULL} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy hash" }));
  expect(await screen.findByText("Copied")).toBeInTheDocument();
  expect(writeText).toHaveBeenCalledWith(FULL);
});

test("clipboard failure is visible, not silent", async () => {
  mockClipboard(vi.fn().mockRejectedValue(new Error("denied")));
  render(<HashBadge hash={FULL} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy hash" }));
  expect(await screen.findByText("Copy failed")).toBeInTheDocument();
});

test("missing clipboard API is visible, not silent", async () => {
  Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
  render(<HashBadge hash={FULL} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy hash" }));
  expect(await screen.findByText("Copy failed")).toBeInTheDocument();
});
```

`frontend/src/ds/primitives/EvidenceChip.test.tsx`
```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { EvidenceChip, toEvidenceRef } from "./EvidenceChip";

// Real ref from results/flawed_model_suite/eval_results_v2/variant6_compound.json
const RAW = {
  uri: "s3://trustlens/evidence/39efa7ad-95a2-4281-85f5-b5dbaa7c4a8c/c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5.json",
  hash: "sha256:86ad1cd39099df1de8ddc73c2af90c53a60de07e9cff1d081dc782922b5ca149",
  created_at: "2026-09-15T00:05:29.311587Z",
  probe_name: "fairness",
  evidence_id: "c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5",
  content_type: "application/json",
};

test("toEvidenceRef keeps string fields and nulls the rest", () => {
  expect(toEvidenceRef(RAW).evidence_id).toBe(RAW.evidence_id);
  expect(toEvidenceRef({ hash: 42 }).hash).toBeNull();
  expect(toEvidenceRef({}).content_type).toBeNull();
});

test("chip shows short id, type and hash", () => {
  render(<EvidenceChip evidence={toEvidenceRef(RAW)} />);
  expect(screen.getByText("ev_c8b8f84a")).toBeInTheDocument();
  expect(screen.getByText("application/json")).toBeInTheDocument();
  expect(screen.getByText("86ad1cd3…a149")).toBeInTheDocument();
});

test("clicking traces the evidence", () => {
  const onTrace = vi.fn();
  render(<EvidenceChip evidence={toEvidenceRef(RAW)} onTrace={onTrace} />);
  fireEvent.click(screen.getByRole("button", { name: `Trace evidence ${RAW.evidence_id}` }));
  expect(onTrace).toHaveBeenCalledWith(expect.objectContaining({ evidence_id: RAW.evidence_id }));
});

test("missing fields are labelled, not blank", () => {
  render(<EvidenceChip evidence={toEvidenceRef({})} />);
  expect(screen.getByText("ev_unknown")).toBeInTheDocument();
  expect(screen.getByText("unknown type")).toBeInTheDocument();
  expect(screen.getByText("— not recorded")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run — expect FAIL** (`npx vitest run src/ds/primitives/HashBadge.test.tsx src/ds/primitives/EvidenceChip.test.tsx`).

- [ ] **Step 3: Implement**

`frontend/src/ds/primitives/HashBadge.tsx`
```tsx
import { useEffect, useState } from "react";

export function shortHash(hash: string): string {
  const digest = hash.slice(hash.lastIndexOf(":") + 1);
  return digest.length <= 12 ? digest : `${digest.slice(0, 8)}…${digest.slice(-4)}`;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), 1500);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <>
      <button type="button" className="tl-copy" onClick={copy} aria-label={label}>⧉</button>
      <span className="tl-copy__status" role="status">
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : ""}
      </span>
    </>
  );
}

export function HashBadge({ hash, label = "hash" }: { hash: string | null | undefined; label?: string }) {
  if (!hash) return <span className="tl-hash tl-hash--none">— not recorded</span>;
  const colon = hash.lastIndexOf(":");
  const algo = colon > 0 ? hash.slice(0, colon) : null;
  return (
    <span className="tl-hash">
      <code title={hash} aria-label={`${label} ${hash}`}>
        {algo && <span className="tl-hash__algo" aria-hidden="true">{algo}:</span>}
        <span aria-hidden="true">{shortHash(hash)}</span>
      </code>
      <CopyButton text={hash} label={`Copy ${label}`} />
    </span>
  );
}
```

Note: `getByText("86ad1cd3…a149")` in the EvidenceChip test matches the inner `<span>` (text match ignores `aria-hidden`).

`frontend/src/ds/primitives/EvidenceChip.tsx`
```tsx
import { HashBadge } from "./HashBadge";

export interface EvidenceRef {
  evidence_id: string | null;
  hash: string | null;
  uri: string | null;
  content_type: string | null;
  probe_name: string | null;
  created_at: string | null;
}

const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);

/** evidence_refs are Record<string, unknown> on the wire — narrow them here. */
export function toEvidenceRef(raw: Record<string, unknown>): EvidenceRef {
  return {
    evidence_id: str(raw.evidence_id),
    hash: str(raw.hash),
    uri: str(raw.uri),
    content_type: str(raw.content_type),
    probe_name: str(raw.probe_name),
    created_at: str(raw.created_at),
  };
}

export function EvidenceChip({ evidence, onTrace }: { evidence: EvidenceRef; onTrace?: (e: EvidenceRef) => void }) {
  const id = evidence.evidence_id ? `ev_${evidence.evidence_id.slice(0, 8)}` : "ev_unknown";
  const body = (
    <>
      <span className="tl-evchip__id">{id}</span>
      <span className="tl-evchip__type">{evidence.content_type ?? "unknown type"}</span>
    </>
  );
  return (
    <span className="tl-evchip">
      {onTrace ? (
        <button
          type="button"
          className="tl-evchip__main"
          onClick={() => onTrace(evidence)}
          aria-label={`Trace evidence ${evidence.evidence_id ?? "unknown"}`}
        >
          {body}
        </button>
      ) : (
        <span className="tl-evchip__main">{body}</span>
      )}
      <HashBadge hash={evidence.hash} label={`${id} hash`} />
    </span>
  );
}
```

Append to `frontend/src/ds/ds.css`:
```css
/* ---- HashBadge / EvidenceChip (evidence material: neutral only) ---- */
.tl-hash { display: inline-flex; align-items: center; gap: var(--tl-s-1); font-size: var(--tl-fs-12); }
.tl-hash code { color: var(--tl-text-1); }
.tl-hash__algo { color: var(--tl-text-3); }
.tl-hash--none { color: var(--tl-text-3); font-family: var(--tl-font-mono); }
.tl .tl-copy { padding: 0 var(--tl-s-1); border-color: transparent; color: var(--tl-text-3); line-height: 1.4; }
.tl .tl-copy:hover { color: var(--tl-text-1); }
.tl-copy__status { font-size: var(--tl-fs-12); color: var(--tl-text-2); min-width: 0; }
.tl-evchip {
  display: inline-flex; align-items: center; gap: var(--tl-s-2);
  border: 1px solid var(--tl-line-1); border-radius: var(--tl-r-slip);
  padding: 2px var(--tl-s-2); font-family: var(--tl-font-mono); font-size: var(--tl-fs-12);
}
.tl .tl-evchip__main { display: inline-flex; gap: var(--tl-s-2); border: 0; padding: 0; border-radius: 0; }
.tl-evchip__id { color: var(--tl-text-1); }
.tl-evchip__type { color: var(--tl-text-3); }
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/ds/primitives/HashBadge.tsx src/ds/primitives/HashBadge.test.tsx src/ds/primitives/EvidenceChip.tsx src/ds/primitives/EvidenceChip.test.tsx src/ds/ds.css
git commit -m "feat(ds): HashBadge with honest copy feedback, EvidenceChip"
```

---

### Task 5: ChartFrame + Gauge (evidence layer)

**Files:**
- Create: `frontend/src/ds/primitives/ChartFrame.tsx`, `Gauge.tsx`, `ChartFrame.test.tsx`, `Gauge.test.tsx`
- Modify: `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Produces: `ChartTable = { columns: string[]; rows: (string|number)[][] }`, `ChartFrame({title, summary, table, children})`, `MetricCI = { lower: number; upper: number; method?: string }`, `readCI(raw: unknown): MetricCI | null`, `Gauge({label, metricKey, value, min?, max?, ci?, digits?})`.

- [ ] **Step 1: Failing tests**

`frontend/src/ds/primitives/ChartFrame.test.tsx`
```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { ChartFrame } from "./ChartFrame";

test("summary describes the figure; table toggle swaps the chart", () => {
  render(
    <ChartFrame title="Demo" summary="Two values." table={{ columns: ["k", "v"], rows: [["a", 1]] }}>
      <svg data-testid="chart" />
    </ChartFrame>,
  );
  expect(screen.getByRole("figure")).toHaveAccessibleDescription("Two values.");
  expect(screen.getByTestId("chart")).toBeInTheDocument();
  const toggle = screen.getByRole("button", { name: "Show as table" });
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.queryByTestId("chart")).toBeNull();
  expect(screen.getByRole("columnheader", { name: "k" })).toBeInTheDocument();
});
```

`frontend/src/ds/primitives/Gauge.test.tsx`
```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { Gauge, readCI } from "./Gauge";

// Real dp_ci from variant6_compound.json
const DP_CI = { B: 1000, point: 0.36831, method: "bootstrap_percentile", ci_lower: 0.326535, ci_upper: 0.412892 };

test("readCI narrows the backend CI shape", () => {
  expect(readCI(DP_CI)).toEqual({ lower: 0.326535, upper: 0.412892, method: "bootstrap_percentile" });
  expect(readCI(null)).toBeNull();
  expect(readCI({ ci_lower: "x" })).toBeNull();
});

test("renders value, CI band and summary", () => {
  render(<Gauge label="Demographic parity difference" metricKey="demographic_parity_difference" value={0.36831} ci={readCI(DP_CI)} />);
  expect(screen.getByText("0.368")).toBeInTheDocument();
  expect(screen.getByTestId("gauge-ci")).toBeInTheDocument();
  expect(screen.getByRole("figure")).toHaveAccessibleDescription(/0\.368.*0\.327 to 0\.413/);
});

test("null value is 'not reported', no marker", () => {
  render(<Gauge label="EOD" metricKey="equalized_odds_difference" value={null} />);
  expect(screen.getByText("— not reported")).toBeInTheDocument();
  expect(screen.queryByTestId("gauge-mark")).toBeNull();
});

test("out-of-range value clamps the marker but prints the true value", () => {
  render(<Gauge label="X" metricKey="x" value={1.7} max={1} />);
  expect(screen.getByTestId("gauge-mark")).toHaveAttribute("x1", "232");
  expect(screen.getByText("1.700")).toBeInTheDocument();
});

test("table view lists the metric key", () => {
  render(<Gauge label="X" metricKey="subgroup_f1_spread" value={0.160639} />);
  fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
  expect(screen.getByRole("cell", { name: "subgroup_f1_spread" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement**

`frontend/src/ds/primitives/ChartFrame.tsx`
```tsx
import { useId, useState, type ReactNode } from "react";

export interface ChartTable { columns: string[]; rows: (string | number)[][] }

/** Accessible wrapper every chart uses: text summary + data-table toggle. */
export function ChartFrame({ title, summary, table, children }: {
  title: string; summary: string; table: ChartTable; children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const summaryId = useId();
  return (
    <figure className="tl-chart" aria-describedby={summaryId}>
      <figcaption className="tl-chart__head">
        <span className="tl-chart__title">{title}</span>
        <button type="button" className="tl-chart__toggle" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
          Show as table
        </button>
      </figcaption>
      <p id={summaryId} className="tl-sr-only">{summary}</p>
      {asTable ? (
        <table className="tl-chart__table">
          <thead><tr>{table.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
            ))}
          </tbody>
        </table>
      ) : children}
    </figure>
  );
}
```

`frontend/src/ds/primitives/Gauge.tsx`
```tsx
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
```

Append to `frontend/src/ds/ds.css`:
```css
/* ---- ChartFrame ---- */
.tl-chart { margin: 0; }
.tl-chart__head { display: flex; justify-content: space-between; align-items: baseline; gap: var(--tl-s-3); margin-bottom: var(--tl-s-2); }
.tl-chart__title { font-size: var(--tl-fs-14); color: var(--tl-text-2); }
.tl .tl-chart__toggle { font-size: var(--tl-fs-12); padding: 0 var(--tl-s-2); }
.tl-chart__table { border-collapse: collapse; font-size: var(--tl-fs-14); width: 100%; }
.tl-chart__table th, .tl-chart__table td { text-align: left; padding: var(--tl-s-1) var(--tl-s-2); border-bottom: 1px solid var(--tl-line-1); }
.tl-chart__table th { color: var(--tl-text-3); font-weight: 500; }

/* ---- Gauge (evidence) ---- */
.tl-gauge { display: grid; grid-template-columns: 1fr auto; gap: 0 var(--tl-s-3); align-items: center; }
.tl-gauge__svg { width: 100%; height: 24px; }
.tl-gauge__track { stroke: var(--tl-line-2); stroke-width: 1; }
.tl-gauge__ci { fill: var(--tl-text-3); opacity: 0.35; }
.tl-gauge__mark { stroke: var(--tl-text-1); stroke-width: 2; }
.tl-gauge__value { font-size: var(--tl-fs-16); }
.tl-gauge__key { grid-column: 1 / -1; font-size: var(--tl-fs-12); color: var(--tl-text-3); }
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/ds/primitives/ChartFrame.tsx src/ds/primitives/ChartFrame.test.tsx src/ds/primitives/Gauge.tsx src/ds/primitives/Gauge.test.tsx src/ds/ds.css
git commit -m "feat(ds): accessible ChartFrame and evidence-layer Gauge with CI"
```

---

### Task 6: Dial (assessment) + ScoreRing (score)

**Files:**
- Create: `frontend/src/ds/primitives/Dial.tsx`, `ScoreRing.tsx`, `Dial.test.tsx`, `ScoreRing.test.tsx`
- Modify: `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Consumes: `rampColor` (Task 2).
- Produces: `arcPath(cx, cy, r, startDeg, endDeg): string`, `Dial({letter: "O"|"S"|"D", value: number|null, source?: string|null})`, `RING_CIRCUMFERENCE: number`, `ScoreRing({value: number|null, label: string, veto?: boolean, proposed?: boolean, size?: "sm"|"md"|"lg"})`.

- [ ] **Step 1: Failing tests**

`frontend/src/ds/primitives/Dial.test.tsx`
```tsx
import { render, screen } from "@testing-library/react";
import { arcPath, Dial } from "./Dial";

test("arcPath is deterministic", () => {
  // 135° → (13.62, 50.38); 405° ≡ 45° → (50.38, 50.38); 270° sweep → large-arc flag 1
  expect(arcPath(32, 32, 26, 135, 405)).toBe("M 13.62 50.38 A 26 26 0 1 1 50.38 50.38");
});

test("dial announces value with the inverted convention", () => {
  render(<Dial letter="O" value={6} source="agent" />);
  const meter = screen.getByRole("meter", { name: "Occurrence" });
  expect(meter).toHaveAttribute("aria-valuenow", "6");
  expect(meter).toHaveAttribute("aria-valuetext", "Occurrence 6 of 10, higher is safer");
  expect(screen.getByTestId("dial-arc")).toBeInTheDocument();
  expect(screen.getByText("agent")).toBeInTheDocument();
});

test("null is unavailable, never zero", () => {
  render(<Dial letter="D" value={null} />);
  expect(screen.getByRole("meter", { name: "Detection" })).toHaveAttribute("aria-valuetext", "Detection unavailable");
  expect(screen.queryByTestId("dial-arc")).toBeNull();
  expect(screen.queryByText("0")).toBeNull();
});

test("zero shows 0 with no arc", () => {
  render(<Dial letter="S" value={0} />);
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.queryByTestId("dial-arc")).toBeNull();
});
```

`frontend/src/ds/primitives/ScoreRing.test.tsx`
```tsx
import { render, screen } from "@testing-library/react";
import { RING_CIRCUMFERENCE, ScoreRing } from "./ScoreRing";

test("final score: numeral, meter, static end-state dashoffset", () => {
  render(<ScoreRing value={6.6039} label="Fairness" />);
  expect(screen.getByText("6.60")).toBeInTheDocument();
  const meter = screen.getByRole("meter", { name: "Fairness" });
  expect(meter).toHaveAttribute("data-state", "final");
  expect(screen.getByTestId("ring-arc")).toHaveAttribute(
    "stroke-dashoffset",
    (RING_CIRCUMFERENCE * (1 - 0.66039)).toFixed(3),
  );
});

test("null is 'not scored', no arc, no zero", () => {
  render(<ScoreRing value={null} label="Safety" />);
  expect(screen.getByText("not scored")).toBeInTheDocument();
  expect(screen.queryByTestId("ring-arc")).toBeNull();
  expect(screen.queryByText("0.00")).toBeNull();
});

test("NaN is treated as not scored", () => {
  render(<ScoreRing value={Number.NaN} label="Safety" />);
  expect(screen.getByText("not scored")).toBeInTheDocument();
  expect(screen.queryByText("NaN")).toBeNull();
});

test("veto is labelled, not just darkest colour", () => {
  render(<ScoreRing value={0} veto label="Integrity" />);
  expect(screen.getByText("VETO")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "Integrity" })).toHaveAttribute("data-state", "veto");
});

test("proposed values say so", () => {
  render(<ScoreRing value={5.04} proposed label="Fairness" />);
  expect(screen.getByText("proposed")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "Fairness" })).toHaveAttribute(
    "aria-valuetext",
    "Fairness: 5.04 of 10, proposed — not final",
  );
});

test("out-of-range value clamps the arc but prints the true value", () => {
  render(<ScoreRing value={10.4} label="X" />);
  expect(screen.getByText("10.40")).toBeInTheDocument();
  expect(screen.getByTestId("ring-arc")).toHaveAttribute("stroke-dashoffset", "0.000");
});
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement**

`frontend/src/ds/primitives/Dial.tsx`
```tsx
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
```

Note: `getByText` ignores `aria-hidden`, so the zero test finds the value span; the null test relies on that span printing "—".

`frontend/src/ds/primitives/ScoreRing.tsx`
```tsx
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
  const scored = v !== null;
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
        {scored && (
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
      {!scored && <span className="tl-ring__flag">not scored</span>}
    </div>
  );
}
```

Append to `frontend/src/ds/ds.css`:
```css
/* ---- Dial (assessment) ---- */
.tl-dial { position: relative; display: inline-grid; justify-items: center; width: 72px; }
.tl-dial svg { width: 64px; height: 64px; }
.tl-dial__track { fill: none; stroke: var(--tl-line-1); stroke-width: 4; stroke-linecap: round; }
.tl-dial__tick { stroke: var(--tl-line-2); stroke-width: 1; }
.tl-dial__arc { fill: none; stroke-width: 4; stroke-linecap: round; transition: d var(--tl-dur-std) var(--tl-ease-spring); }
.tl-dial__letter { position: absolute; top: 18px; font-size: var(--tl-fs-12); color: var(--tl-text-3); }
.tl-dial__value { position: absolute; top: 30px; font-size: var(--tl-fs-16); }
.tl-dial__source { font-size: var(--tl-fs-12); color: var(--tl-text-3); }

/* ---- ScoreRing (score / lens) ---- */
.tl-ring { position: relative; display: inline-grid; place-items: center; }
.tl-ring--sm { width: 56px; } .tl-ring--md { width: 112px; } .tl-ring--lg { width: 200px; }
.tl-ring svg { width: 100%; height: auto; grid-area: 1 / 1; }
.tl-ring__track { fill: none; stroke: var(--tl-line-1); stroke-width: 6; }
.tl-ring[data-state="unscored"] .tl-ring__track { stroke-dasharray: 3 5; stroke: var(--tl-line-2); }
.tl-ring__arc {
  fill: none; stroke-width: 6; stroke-linecap: round;
  transition: stroke-dashoffset var(--tl-dur-land) var(--tl-ease-land);
}
.tl-ring[data-state="proposed"] .tl-ring__arc { opacity: 0.6; }
.tl-ring__hatch { stroke: var(--tl-text-2); stroke-width: 2; }
.tl-ring__num { grid-area: 1 / 1; font-size: var(--tl-fs-25); }
.tl-ring--lg .tl-ring__num { font-size: var(--tl-fs-49); }
.tl-ring--sm .tl-ring__num { font-size: var(--tl-fs-14); }
.tl-ring__flag { font-size: var(--tl-fs-12); letter-spacing: 0.08em; text-transform: uppercase; color: var(--tl-text-2); }
.tl-ring--lg { filter: drop-shadow(var(--tl-glow)); }
```

(Proposed uses reduced opacity, not a dash pattern — `stroke-dasharray` is already the fill mechanism.)

- [ ] **Step 4: Run — expect PASS** (`npx vitest run src/ds/primitives/Dial.test.tsx src/ds/primitives/ScoreRing.test.tsx`).

- [ ] **Step 5: Commit**

```bash
git add src/ds/primitives/Dial.tsx src/ds/primitives/Dial.test.tsx src/ds/primitives/ScoreRing.tsx src/ds/primitives/ScoreRing.test.tsx src/ds/ds.css
git commit -m "feat(ds): O/S/D Dial and ScoreRing with veto, proposed and unscored states"
```

---

### Task 7: Pentagon

**Files:**
- Create: `frontend/src/ds/primitives/Pentagon.tsx`, `Pentagon.test.tsx`
- Modify: `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Consumes: `FRIES_DIMENSIONS`, `DIMENSIONS`, `ChartFrame`.
- Produces: `PentagonScores = Partial<Record<FriesDimension, number | null>>`, `vertex(i: number, v: number): [number, number]`, `Pentagon({scores, ghost?, title?})`.

- [ ] **Step 1: Failing test** — `frontend/src/ds/primitives/Pentagon.test.tsx`

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { Pentagon, vertex } from "./Pentagon";

const COMPOUND = { FAIRNESS: 6.6039, ROBUSTNESS: 9.0, INTEGRITY: 2.2894, EXPLAINABILITY: 1.2599, SAFETY: 1.2599 };

test("vertex 0 at full scale points straight up", () => {
  const [x, y] = vertex(0, 10);
  expect(x).toBeCloseTo(120, 6);
  expect(y).toBeCloseTo(28, 6);
});

test("complete scores draw a closed, filled shape", () => {
  const { container } = render(<Pentagon scores={COMPOUND} />);
  expect(container.querySelector("svg")).toHaveAttribute("data-complete", "true");
  expect(screen.getByTestId("penta-shape").getAttribute("d")).toMatch(/Z$/);
  expect(container.querySelectorAll("[data-dim]")).toHaveLength(5);
});

test("missing dimension is hollow, not zero, and not closed", () => {
  const { container } = render(<Pentagon scores={{ ...COMPOUND, SAFETY: null }} />);
  expect(container.querySelector("svg")).toHaveAttribute("data-complete", "false");
  expect(screen.getByTestId("penta-shape").getAttribute("d")).not.toMatch(/Z/);
  expect(container.querySelector('[data-missing="SAFETY"]')).not.toBeNull();
  expect(screen.getByRole("figure")).toHaveAccessibleDescription(/Safety not scored.*not counted as zero/);
  fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
  expect(screen.getByRole("row", { name: /Safety not scored/ })).toBeInTheDocument();
  expect(screen.queryByRole("cell", { name: "0.0000" })).toBeNull();
});

test("absent keys behave like null", () => {
  const { container } = render(<Pentagon scores={{ FAIRNESS: 5 }} />);
  expect(container.querySelectorAll("[data-missing]")).toHaveLength(4);
});

test("ghost outline renders proposed values", () => {
  render(<Pentagon scores={{}} ghost={COMPOUND} />);
  expect(screen.getByTestId("penta-ghost")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement** — `frontend/src/ds/primitives/Pentagon.tsx`

```tsx
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
```

Append to `frontend/src/ds/ds.css`:
```css
/* ---- Pentagon (score / lens) ---- */
.tl-penta { width: 100%; max-width: 320px; height: auto; overflow: visible; }
.tl-penta__grid { fill: none; stroke: var(--tl-line-1); stroke-width: 1; }
.tl-penta__axis { stroke-width: 1; opacity: 0.55; }
.tl-penta__ghost { fill: none; stroke: var(--tl-text-3); stroke-width: 1; stroke-dasharray: 3 3; }
.tl-penta__shape { fill: none; stroke: var(--tl-uv); stroke-width: 2; stroke-linejoin: round; }
.tl-penta__shape--filled { fill: color-mix(in oklch, var(--tl-uv) 16%, transparent); }
.tl-penta__dot { fill: var(--tl-uv); transition: cx var(--tl-dur-land) var(--tl-ease-land), cy var(--tl-dur-land) var(--tl-ease-land); }
.tl-penta__missing { fill: none; stroke: var(--tl-text-3); stroke-width: 1.5; stroke-dasharray: 2 2; }
.tl-penta__label { font-family: var(--tl-font-mono); font-size: 12px; font-weight: 500; }
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/ds/primitives/Pentagon.tsx src/ds/primitives/Pentagon.test.tsx src/ds/ds.css
git commit -m "feat(ds): FRIES Pentagon with hollow missing vertices and table view"
```

---

### Task 8: Spine + Timeline

**Files:**
- Create: `frontend/src/ds/primitives/Spine.tsx`, `Timeline.tsx`, `Spine.test.tsx`, `Timeline.test.tsx`
- Modify: `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Consumes: `fmtTimeSeconds` from `src/lib/format.ts`.
- Produces: `StageState = "done"|"current"|"pending"|"failed"|"not_required"`, `SpineStage = { key: string; label: string; state: StageState; at?: string|null; note?: string }`, `Spine({stages})`; `TimelineEvent = { id: number; event_type: string; created_at: string; detail?: Record<string, unknown>|null }`, `EVENT_LABELS`, `eventLabel(t: string): string`, `Timeline({events, onSelect?})`. (`EvaluationEventRead` from `api/types.ts` is structurally assignable to `TimelineEvent`.)

- [ ] **Step 1: Failing tests**

`frontend/src/ds/primitives/Spine.test.tsx`
```tsx
import { render, screen, within } from "@testing-library/react";
import { Spine, type SpineStage } from "./Spine";

const STAGES: SpineStage[] = [
  { key: "draft", label: "Draft", state: "done", at: "2026-09-15T00:04:50Z" },
  { key: "probes", label: "Probes", state: "current" },
  { key: "review", label: "Human review", state: "not_required", note: "AI_AUTONOMOUS mode" },
  { key: "final", label: "Final score", state: "pending" },
];

test("current stage is aria-current=step and says Active in words", () => {
  render(<Spine stages={STAGES} />);
  const current = screen.getByText("Probes").closest("li")!;
  expect(current).toHaveAttribute("aria-current", "step");
  expect(within(current).getByText("Active")).toBeInTheDocument();
});

test("done stages lock with a timestamp; pending ones have none", () => {
  render(<Spine stages={STAGES} />);
  expect(screen.getByText("Draft").closest("li")!.querySelector("time")).toHaveAttribute("datetime", "2026-09-15T00:04:50Z");
  expect(screen.getByText("Final score").closest("li")!.querySelector("time")).toBeNull();
});

test("not-required stage explains why", () => {
  render(<Spine stages={STAGES} />);
  expect(screen.getByText("Not required")).toBeInTheDocument();
  expect(screen.getByText("AI_AUTONOMOUS mode")).toBeInTheDocument();
});
```

`frontend/src/ds/primitives/Timeline.test.tsx`
```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { Timeline, type TimelineEvent } from "./Timeline";

const EVENTS: TimelineEvent[] = [
  { id: 3, event_type: "probes_completed", created_at: "2026-09-15T00:06:08Z", detail: { probe_count: 5 } },
  { id: 1, event_type: "evaluation_created", created_at: "2026-09-15T00:04:50Z" },
  { id: 2, event_type: "evaluation_started", created_at: "2026-09-15T00:04:51Z" },
  { id: 4, event_type: "probe_heartbeat_v9", created_at: "2026-09-15T00:06:09Z" },
];

test("orders by id and shows +Δs from the first event", () => {
  render(<Timeline events={EVENTS} />);
  const items = screen.getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Evaluation created");
  expect(items[0]).toHaveTextContent("+0.0s");
  expect(items[2]).toHaveTextContent("Probes completed");
  expect(items[2]).toHaveTextContent("+78.0s");
});

test("is a polite live log", () => {
  render(<Timeline events={EVENTS} />);
  const log = screen.getByRole("log");
  expect(log).toHaveAttribute("aria-live", "polite");
});

test("unknown event types render verbatim", () => {
  render(<Timeline events={EVENTS} />);
  expect(screen.getAllByText("probe_heartbeat_v9").length).toBeGreaterThan(0);
});

test("filter narrows to one type", () => {
  render(<Timeline events={EVENTS} />);
  fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "evaluation_started" } });
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
});

test("rows are selectable when onSelect is given", () => {
  const onSelect = vi.fn();
  render(<Timeline events={EVENTS} onSelect={onSelect} />);
  fireEvent.click(screen.getAllByRole("button")[0]);
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
});

test("empty state is explicit", () => {
  render(<Timeline events={[]} />);
  expect(screen.getByText("No events recorded yet.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement**

`frontend/src/ds/primitives/Spine.tsx`
```tsx
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
```

`frontend/src/ds/primitives/Timeline.tsx`
```tsx
import { useId, useState } from "react";
import { fmtTimeSeconds } from "../../lib/format";

export interface TimelineEvent { id: number; event_type: string; created_at: string; detail?: Record<string, unknown> | null }

/** The 10 types emitted today (backend/app/db/repositories/evaluation_event.py). */
export const EVENT_LABELS: Record<string, string> = {
  evaluation_created: "Evaluation created",
  evaluation_requeued: "Re-queued",
  evaluation_started: "Evaluation started",
  probes_completed: "Probes completed",
  agent_completed: "O/S/D proposal ready",
  evaluation_failed: "Evaluation failed",
  awaiting_review: "Awaiting human review",
  human_review_submitted: "Human review submitted",
  evaluation_finalized: "Evaluation finalized",
  report_generated: "Report generated",
};

export const eventLabel = (type: string): string => EVENT_LABELS[type] ?? type;

export function Timeline({ events, onSelect }: { events: TimelineEvent[]; onSelect?: (e: TimelineEvent) => void }) {
  const [filter, setFilter] = useState("all");
  const selectId = useId();
  if (events.length === 0) return <p className="tl-timeline__empty">No events recorded yet.</p>;

  const sorted = [...events].sort((a, b) => a.id - b.id);
  const t0 = Date.parse(sorted[0].created_at);
  const types = [...new Set(sorted.map((e) => e.event_type))];
  const shown = filter === "all" ? sorted : sorted.filter((e) => e.event_type === filter);

  return (
    <div className="tl-timeline">
      <div className="tl-timeline__filter">
        <label htmlFor={selectId}>Filter</label>
        <select id={selectId} value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All events ({sorted.length})</option>
          {types.map((t) => <option key={t} value={t}>{eventLabel(t)}</option>)}
        </select>
      </div>
      <ol className="tl-timeline__list" role="log" aria-live="polite" aria-label="Evaluation events">
        {shown.map((e) => {
          const delta = (Date.parse(e.created_at) - t0) / 1000;
          const body = (
            <>
              <span className="tl-timeline__node" data-kind={e.event_type === "evaluation_failed" ? "fail" : "ok"} aria-hidden="true" />
              <span className="tl-timeline__label">{eventLabel(e.event_type)}</span>
              <time dateTime={e.created_at} className="num">{fmtTimeSeconds(e.created_at)}</time>
              <span className="tl-timeline__delta num">+{delta.toFixed(1)}s</span>
            </>
          );
          return (
            <li key={e.id} className="tl-timeline__item">
              {onSelect ? <button type="button" className="tl-timeline__row" onClick={() => onSelect(e)}>{body}</button> : <div className="tl-timeline__row">{body}</div>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
```

Hook order note: `useState`/`useId` run before the early return, so hook order is stable.

Append to `frontend/src/ds/ds.css`:
```css
/* ---- Spine ---- */
.tl-spine { list-style: none; margin: 0; padding: 0; display: flex; gap: var(--tl-s-2); overflow-x: auto; }
.tl-spine__stage {
  flex: 1 0 120px; display: grid; gap: 2px; padding: var(--tl-s-2) var(--tl-s-3);
  border-top: 2px solid var(--tl-line-1); color: var(--tl-text-3);
}
.tl-spine__stage[data-state="done"] { border-top-color: var(--tl-text-2); color: var(--tl-text-1); }
.tl-spine__stage[data-state="current"] { border-top-color: var(--tl-uv); color: var(--tl-text-1); }
.tl-spine__stage[data-state="failed"] { border-top-color: var(--tl-fail); color: var(--tl-fail); }
.tl-spine__stage[data-state="not_required"] { border-top-style: dashed; }
.tl-spine__glyph { font-size: var(--tl-fs-12); }
.tl-spine__stage[data-state="current"] .tl-spine__glyph { color: var(--tl-uv); }
.tl-spine__label { font-weight: 500; }
.tl-spine__state, .tl-spine__time, .tl-spine__note { font-size: var(--tl-fs-12); }

/* ---- Timeline ---- */
.tl-timeline__filter { display: flex; gap: var(--tl-s-2); align-items: center; margin-bottom: var(--tl-s-2); font-size: var(--tl-fs-14); }
.tl-timeline__filter select { font: inherit; color: var(--tl-text-1); background: var(--tl-ink-1); border: 1px solid var(--tl-line-2); border-radius: var(--tl-r-card); padding: 2px var(--tl-s-2); }
.tl-timeline__list { list-style: none; margin: 0; padding: 0; border-left: 1px solid var(--tl-line-1); }
.tl-timeline__item { content-visibility: auto; contain-intrinsic-size: auto 32px; }
.tl .tl-timeline__row {
  display: grid; grid-template-columns: 12px 1fr auto auto; gap: var(--tl-s-3); align-items: center;
  width: 100%; text-align: left; padding: var(--tl-s-1) var(--tl-s-3); border: 0; border-radius: 0; font-size: var(--tl-fs-14);
}
.tl-timeline__node { width: 7px; height: 7px; border-radius: 50%; background: var(--tl-text-2); margin-left: -16px; }
.tl-timeline__node[data-kind="fail"] { background: var(--tl-fail); border-radius: 0; }
.tl-timeline__delta { color: var(--tl-text-3); }
.tl-timeline__empty { color: var(--tl-text-3); }
```

- [ ] **Step 4: Run — expect PASS.** The `+78.0s` assertion = 00:06:08 − 00:04:50.

- [ ] **Step 5: Commit**

```bash
git add src/ds/primitives/Spine.tsx src/ds/primitives/Spine.test.tsx src/ds/primitives/Timeline.tsx src/ds/primitives/Timeline.test.tsx src/ds/ds.css
git commit -m "feat(ds): pipeline Spine and filterable event Timeline"
```

---

### Task 9: TracePanel

**Files:**
- Create: `frontend/src/ds/primitives/TracePanel.tsx`, `TracePanel.test.tsx`
- Modify: `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Consumes: `EvidenceChip`, `EvidenceRef` (Task 4).
- Produces: `TraceLayer = "score"|"assessment"|"evidence"`, `TraceLevel = { layer: TraceLayer; heading: string; value?: string; rows?: [string, string][]; evidence?: EvidenceRef[]; raw?: unknown }`, `TraceChain = { title: string; levels: TraceLevel[] }`, `TracePanel({chain: TraceChain|null, onClose: () => void})`.

- [ ] **Step 1: Failing test** — `frontend/src/ds/primitives/TracePanel.test.tsx`

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";
import { TracePanel, type TraceChain } from "./TracePanel";

const CHAIN: TraceChain = {
  title: "Fairness 6.60",
  levels: [
    { layer: "score", heading: "Aspect score", value: "6.6039" },
    { layer: "assessment", heading: "Risk: group disparity", rows: [["O", "6"], ["S", "6"], ["D", "8"], ["T = ∛(O·S·D)", "6.6039"]] },
    { layer: "evidence", heading: "Fairness probe", rows: [["demographic_parity_difference", "0.368"]], raw: { demographic_parity_difference: 0.36831 } },
  ],
};

test("renders nothing when closed", () => {
  const { container } = render(<TracePanel chain={null} onClose={() => {}} />);
  expect(container).toBeEmptyDOMElement();
});

test("focuses its heading on open and lists layers in chain order", () => {
  render(<TracePanel chain={CHAIN} onClose={() => {}} />);
  expect(screen.getByRole("heading", { name: "Fairness 6.60" })).toHaveFocus();
  const layers = screen.getAllByText(/^(FRIES score|Risk assessment|Evidence)$/).map((n) => n.textContent);
  expect(layers).toEqual(["FRIES score", "Risk assessment", "Evidence"]);
});

test("raw JSON is two clicks away (collapsed by default)", () => {
  render(<TracePanel chain={CHAIN} onClose={() => {}} />);
  expect(screen.getByText("Raw JSON").closest("details")).not.toHaveAttribute("open");
});

test("Escape closes", () => {
  const onClose = vi.fn();
  render(<TracePanel chain={CHAIN} onClose={onClose} />);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalled();
});

test("focus returns to the trigger after closing", () => {
  function Harness() {
    const [chain, setChain] = useState<TraceChain | null>(null);
    return (
      <>
        <button onClick={() => setChain(CHAIN)}>6.60</button>
        <TracePanel chain={chain} onClose={() => setChain(null)} />
      </>
    );
  }
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "6.60" });
  trigger.focus();
  fireEvent.click(trigger);
  expect(screen.getByRole("heading", { name: "Fairness 6.60" })).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: "Close trace" }));
  expect(trigger).toHaveFocus();
});
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement** — `frontend/src/ds/primitives/TracePanel.tsx`

```tsx
import { useEffect, useId, useRef } from "react";
import { EvidenceChip, type EvidenceRef } from "./EvidenceChip";

export type TraceLayer = "score" | "assessment" | "evidence";
export interface TraceLevel {
  layer: TraceLayer;
  heading: string;
  value?: string;
  rows?: [string, string][];
  evidence?: EvidenceRef[];
  raw?: unknown;
}
export interface TraceChain { title: string; levels: TraceLevel[] }

const LAYER_NAME: Record<TraceLayer, string> = {
  score: "FRIES score",
  assessment: "Risk assessment",
  evidence: "Evidence",
};

/** Non-modal side sheet: the page stays inspectable while tracing.
 * Summary → evidence (1 click) → raw JSON (2 clicks). */
export function TracePanel({ chain, onClose }: { chain: TraceChain | null; onClose: () => void }) {
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });

  useEffect(() => {
    if (!chain) return;
    const returnTo = document.activeElement as HTMLElement | null;
    headingRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      returnTo?.focus?.();
    };
  }, [chain]);

  if (!chain) return null;
  return (
    <aside className="tl-trace" role="dialog" aria-modal="false" aria-labelledby={headingId}>
      <header className="tl-trace__head">
        <h2 id={headingId} ref={headingRef} tabIndex={-1} className="tl-display">{chain.title}</h2>
        <button type="button" onClick={onClose} aria-label="Close trace">✕</button>
      </header>
      <ol className="tl-trace__chain">
        {chain.levels.map((level, i) => (
          <li key={i} className={`tl-trace__level tl-trace__level--${level.layer}`}>
            <span className="tl-trace__layer">{LAYER_NAME[level.layer]}</span>
            <h3 className="tl-trace__heading">{level.heading}</h3>
            {level.value && <p className="tl-trace__value num">{level.value}</p>}
            {level.rows && (
              <dl className="tl-trace__rows">
                {level.rows.map(([k, v]) => (
                  <div key={k}><dt>{k}</dt><dd className="num">{v}</dd></div>
                ))}
              </dl>
            )}
            {level.evidence?.map((ev, j) => <EvidenceChip key={`${i}-${j}`} evidence={ev} />)}
            {level.raw !== undefined && (
              <details className="tl-trace__raw">
                <summary>Raw JSON</summary>
                <pre>{JSON.stringify(level.raw, null, 2)}</pre>
              </details>
            )}
          </li>
        ))}
      </ol>
    </aside>
  );
}
```

Append to `frontend/src/ds/ds.css`:
```css
/* ---- TracePanel ---- */
.tl-trace {
  position: fixed; inset: 0 0 0 auto; width: min(440px, 100vw); overflow-y: auto;
  background: var(--tl-ink-2); border-left: 1px solid var(--tl-line-2); padding: var(--tl-s-5);
  z-index: 50;
  animation: tl-trace-in var(--tl-dur-std) var(--tl-ease-spring);
}
@keyframes tl-trace-in { from { transform: translateX(16px); opacity: 0; } to { transform: none; opacity: 1; } }
.tl-trace__head { display: flex; justify-content: space-between; align-items: start; gap: var(--tl-s-3); }
.tl-trace__head h2 { margin: 0; font-size: var(--tl-fs-25); }
.tl-trace__chain { list-style: none; margin: var(--tl-s-5) 0 0; padding: 0; display: grid; gap: var(--tl-s-4); }
.tl-trace__level { padding-left: var(--tl-s-4); border-left: 2px solid var(--tl-line-2); }
.tl-trace__level--score { border-left-color: var(--tl-uv); }
.tl-trace__level--evidence { border-left-style: dotted; }
.tl-trace__layer { font-size: var(--tl-fs-12); letter-spacing: 0.08em; text-transform: uppercase; color: var(--tl-text-3); }
.tl-trace__heading { margin: 2px 0 var(--tl-s-2); font-size: var(--tl-fs-16); font-weight: 500; }
.tl-trace__level--score .tl-trace__value { font-family: var(--tl-font-display); font-size: var(--tl-fs-31); margin: 0; }
.tl-trace__rows { display: grid; gap: 2px; margin: 0; font-size: var(--tl-fs-14); }
.tl-trace__rows div { display: flex; justify-content: space-between; gap: var(--tl-s-3); }
.tl-trace__rows dt { font-family: var(--tl-font-mono); color: var(--tl-text-2); }
.tl-trace__rows dd { margin: 0; }
.tl-trace__raw pre { font-size: var(--tl-fs-12); overflow-x: auto; background: var(--tl-ink-0); padding: var(--tl-s-2); border-radius: var(--tl-r-slip); }
```

(The `tl-trace-in` animation duration comes from `--tl-dur-std`, which is `0ms` under reduced motion.)

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/ds/primitives/TracePanel.tsx src/ds/primitives/TracePanel.test.tsx src/ds/ds.css
git commit -m "feat(ds): TracePanel side sheet with focus management and raw JSON disclosure"
```

---

### Task 10: Gallery page + `/gallery` route

**Files:**
- Create: `frontend/src/ds/gallery/GalleryPage.tsx`, `frontend/src/ds/gallery/GalleryPage.test.tsx`
- Modify: `frontend/src/App.tsx` (import + route), `frontend/src/ds/ds.css` (append)

**Interfaces:**
- Consumes: every primitive above, `DIMENSIONS`, `RAMP_ANCHORS`, `rampVar`, `riskT`.
- Produces: default export `GalleryPage`; route `/gallery` rendered **outside** `Layout`.

- [ ] **Step 1: Failing test** — `frontend/src/ds/gallery/GalleryPage.test.tsx`

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import GalleryPage from "./GalleryPage";

const SECTIONS = [
  "Colour", "Type", "Motion", "Materials", "Status", "Dimensions", "Evidence",
  "Gauge", "Dial", "Score ring", "Pentagon", "Spine", "Timeline", "Trace panel",
];

test("every primitive has a gallery section", () => {
  render(<GalleryPage />);
  for (const name of SECTIONS) {
    expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
  }
});

test("labels itself as specimen data, never an audit", () => {
  render(<GalleryPage />);
  expect(screen.getByText(/Specimen data — not an audit/)).toBeInTheDocument();
});

test("theme and reduced-motion toggles set root attributes", () => {
  const { container } = render(<GalleryPage />);
  const root = container.firstElementChild!;
  expect(root).toHaveAttribute("data-theme", "dark");
  fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
  expect(root).toHaveAttribute("data-theme", "light");
  fireEvent.click(screen.getByRole("button", { name: "Reduce motion" }));
  expect(root).toHaveAttribute("data-motion", "reduce");
});

test("clicking a score opens the trace panel", () => {
  render(<GalleryPage />);
  fireEvent.click(screen.getByRole("button", { name: "Trace Fairness 6.60" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement** — `frontend/src/ds/gallery/GalleryPage.tsx`

```tsx
import { useState, type ReactNode } from "react";
import "../fonts";
import "../tokens.css";
import "../ds.css";
import { FRIES_DIMENSIONS } from "../../api/types";
import { RAMP_ANCHORS, rampVar } from "../ramp";
import { riskT } from "../scoring";
import { Card, Slip } from "../primitives/Card";
import { Dial } from "../primitives/Dial";
import { DimensionMark } from "../primitives/DimensionMark";
import { EvidenceChip, toEvidenceRef } from "../primitives/EvidenceChip";
import { Gauge, readCI } from "../primitives/Gauge";
import { HashBadge } from "../primitives/HashBadge";
import { Pentagon } from "../primitives/Pentagon";
import { ScoreRing } from "../primitives/ScoreRing";
import { Spine } from "../primitives/Spine";
import { CHIP_STATUSES, StatusChip } from "../primitives/StatusChip";
import { Timeline } from "../primitives/Timeline";
import { TracePanel, type TraceChain } from "../primitives/TracePanel";

// Specimen values copied from results/flawed_model_suite/eval_results_v2/variant6_compound.json.
const COMPOUND = { FAIRNESS: 6.6039, ROBUSTNESS: 9.0, INTEGRITY: 2.2894, EXPLAINABILITY: 1.2599, SAFETY: 1.2599 };
const FAIRNESS_OSD = { O: 6, S: 6, D: 8 };
const FAIRNESS_REF = toEvidenceRef({
  uri: "s3://trustlens/evidence/39efa7ad-95a2-4281-85f5-b5dbaa7c4a8c/c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5.json",
  hash: "sha256:86ad1cd39099df1de8ddc73c2af90c53a60de07e9cff1d081dc782922b5ca149",
  created_at: "2026-09-15T00:05:29.311587Z",
  probe_name: "fairness",
  evidence_id: "c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5",
  content_type: "application/json",
});
const DP_CI = readCI({ ci_lower: 0.326535, ci_upper: 0.412892, method: "bootstrap_percentile" });
// Event timestamps are illustrative (the source run stored no events).
const EVENTS = [
  { id: 1, event_type: "evaluation_created", created_at: "2026-09-15T00:04:50Z" },
  { id: 2, event_type: "evaluation_started", created_at: "2026-09-15T00:04:51Z" },
  { id: 3, event_type: "probes_completed", created_at: "2026-09-15T00:06:08Z", detail: { probe_count: 5 } },
  { id: 4, event_type: "agent_completed", created_at: "2026-09-15T00:06:12Z" },
  { id: 5, event_type: "evaluation_finalized", created_at: "2026-09-15T00:06:12Z" },
];
const SWATCHES = [
  "--tl-ink-0", "--tl-ink-1", "--tl-ink-2", "--tl-line-1", "--tl-line-2",
  "--tl-text-1", "--tl-text-2", "--tl-text-3", "--tl-uv", "--tl-fail",
];
const T_FAIR = riskT(FAIRNESS_OSD.O, FAIRNESS_OSD.S, FAIRNESS_OSD.D);
const TRACE: TraceChain = {
  title: `Fairness ${T_FAIR.toFixed(2)}`,
  levels: [
    { layer: "score", heading: "Aspect score (mean of 1 risk)", value: COMPOUND.FAIRNESS.toFixed(4) },
    {
      layer: "assessment",
      heading: "Risk: outcome disparity across identity groups",
      rows: [["O", "6"], ["S", "6"], ["D", "8"], ["T = ∛(O·S·D)", T_FAIR.toFixed(4)]],
    },
    {
      layer: "evidence",
      heading: "Fairness probe · EVALUATED · n = 3000",
      rows: [["demographic_parity_difference", "0.368"], ["equalized_odds_difference", "0.167"], ["subgroup_f1_spread", "0.161"]],
      evidence: [FAIRNESS_REF],
      raw: { demographic_parity_difference: 0.36831, dp_ci: { ci_lower: 0.326535, ci_upper: 0.412892 } },
    },
  ],
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="tl-gallery__section">
      <h2 className="tl-gallery__h2">{title}</h2>
      {children}
    </section>
  );
}

export default function GalleryPage() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [reduce, setReduce] = useState(false);
  const [trace, setTrace] = useState<TraceChain | null>(null);
  const [demo, setDemo] = useState(0);
  const DEMO_VALUES = [COMPOUND.FAIRNESS, COMPOUND.EXPLAINABILITY, COMPOUND.ROBUSTNESS];

  return (
    <div className="tl tl-gallery" data-theme={theme} data-motion={reduce ? "reduce" : undefined}>
      <header className="tl-gallery__head">
        <div>
          <h1 className="tl-display tl-gallery__h1">TrustLens design system</h1>
          <p className="tl-gallery__note">Specimen data — not an audit. Values from variant6_compound; event times illustrative.</p>
        </div>
        <div className="tl-gallery__toggles">
          <button type="button" aria-pressed={theme === "light"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>Light theme</button>
          <button type="button" aria-pressed={reduce} onClick={() => setReduce(!reduce)}>Reduce motion</button>
        </div>
      </header>

      <Section title="Colour">
        <div className="tl-gallery__swatches">
          {SWATCHES.map((v) => (
            <figure key={v} className="tl-gallery__swatch"><span style={{ background: `var(${v})` }} /><figcaption><code>{v}</code></figcaption></figure>
          ))}
        </div>
        <p className="tl-gallery__caption">Trust ramp (score layer only) — anchors 0 → 10</p>
        <div className="tl-gallery__ramp">
          {RAMP_ANCHORS.map((a) => <span key={a} style={{ background: rampVar(a) }}><code>{a}</code></span>)}
        </div>
      </Section>

      <Section title="Type">
        <p className="tl-display tl-gallery__spec-display">4.08</p>
        <p>IBM Plex Sans — Demographic parity difference across identity groups</p>
        <p><code>ev_c8b8f84a  application/json  sha256:86ad1cd3…a149</code></p>
      </Section>

      <Section title="Motion">
        <p className="tl-gallery__caption">Moves only on a real change (here: your click). Reduced motion shows the end state instantly.</p>
        <ScoreRing value={DEMO_VALUES[demo]} label="Demo aspect" size="lg" />
        <button type="button" onClick={() => setDemo((demo + 1) % DEMO_VALUES.length)}>Change value</button>
      </Section>

      <Section title="Materials">
        <div className="tl-gallery__row">
          <Card title="Card (chrome)">Structural surface.</Card>
          <Slip label="Slip (evidence)">demographic_parity_difference = 0.36831</Slip>
        </div>
      </Section>

      <Section title="Status">
        <div className="tl-gallery__row">{Object.keys(CHIP_STATUSES).map((s) => <StatusChip key={s} status={s} />)}</div>
      </Section>

      <Section title="Dimensions">
        <div className="tl-gallery__row">{FRIES_DIMENSIONS.map((d) => <DimensionMark key={d} dimension={d} />)}</div>
      </Section>

      <Section title="Evidence">
        <div className="tl-gallery__col">
          <HashBadge hash={FAIRNESS_REF.hash} label="evidence hash" />
          <HashBadge hash={null} label="TrustLens version" />
          <EvidenceChip evidence={FAIRNESS_REF} onTrace={() => setTrace(TRACE)} />
        </div>
      </Section>

      <Section title="Gauge">
        <Gauge label="Demographic parity difference" metricKey="demographic_parity_difference" value={0.36831} ci={DP_CI} />
        <Gauge label="Equalized odds difference" metricKey="equalized_odds_difference" value={null} />
      </Section>

      <Section title="Dial">
        <div className="tl-gallery__row">
          <Dial letter="O" value={FAIRNESS_OSD.O} source="agent" />
          <Dial letter="S" value={FAIRNESS_OSD.S} source="agent" />
          <Dial letter="D" value={FAIRNESS_OSD.D} source="agent" />
          <Dial letter="D" value={null} />
        </div>
        <p className="tl-gallery__caption">T = ∛(O × S × D) = ∛(6 × 6 × 8) = {T_FAIR.toFixed(2)} · higher = safer (inverted FMEA)</p>
      </Section>

      <Section title="Score ring">
        <div className="tl-gallery__row">
          <button type="button" className="tl-gallery__trace" aria-label={`Trace Fairness ${T_FAIR.toFixed(2)}`} onClick={() => setTrace(TRACE)}>
            <ScoreRing value={COMPOUND.FAIRNESS} label="Fairness" />
          </button>
          <ScoreRing value={5.04} proposed label="Proposed" />
          <ScoreRing value={0} veto label="Vetoed" />
          <ScoreRing value={null} label="Unscored" />
        </div>
      </Section>

      <Section title="Pentagon">
        <div className="tl-gallery__row">
          <Pentagon scores={COMPOUND} title="Complete (compound flaw)" />
          <Pentagon scores={{ ...COMPOUND, SAFETY: null }} title="Safety missing" />
        </div>
        <p className="tl-gallery__caption">Traceable aggregation of risk assessments — not an absolute safety measure.</p>
      </Section>

      <Section title="Spine">
        <Spine stages={[
          { key: "draft", label: "Draft", state: "done", at: "2026-09-15T00:04:50Z" },
          { key: "dataset", label: "Dataset validated", state: "done", at: "2026-09-15T00:04:50Z" },
          { key: "probes", label: "Probes", state: "current" },
          { key: "osd", label: "O/S/D proposal", state: "pending" },
          { key: "review", label: "Human review", state: "not_required", note: "AI_AUTONOMOUS mode" },
          { key: "final", label: "Final score", state: "pending" },
          { key: "report", label: "Report", state: "pending" },
        ]} />
      </Section>

      <Section title="Timeline">
        <Timeline events={EVENTS} />
      </Section>

      <Section title="Trace panel">
        <button type="button" onClick={() => setTrace(TRACE)}>Open example trace</button>
      </Section>

      <TracePanel chain={trace} onClose={() => setTrace(null)} />
    </div>
  );
}
```

Append to `frontend/src/ds/ds.css`:
```css
/* ---- Gallery ---- */
.tl-gallery { min-height: 100vh; padding: var(--tl-s-8) var(--tl-s-7); }
.tl-gallery__head { display: flex; justify-content: space-between; align-items: end; gap: var(--tl-s-5); flex-wrap: wrap; margin-bottom: var(--tl-s-8); }
.tl-gallery__h1 { margin: 0; font-size: var(--tl-fs-49); }
.tl-gallery__note { margin: var(--tl-s-2) 0 0; color: var(--tl-text-3); font-size: var(--tl-fs-14); }
.tl-gallery__toggles { display: flex; gap: var(--tl-s-2); }
.tl-gallery__section { padding: var(--tl-s-6) 0; border-top: 1px solid var(--tl-line-1); display: grid; gap: var(--tl-s-4); }
.tl-gallery__h2 { margin: 0; font-size: var(--tl-fs-14); letter-spacing: 0.08em; text-transform: uppercase; color: var(--tl-text-2); font-weight: 600; }
.tl-gallery__row { display: flex; flex-wrap: wrap; gap: var(--tl-s-5); align-items: start; }
.tl-gallery__col { display: grid; gap: var(--tl-s-3); justify-items: start; }
.tl-gallery__caption { margin: 0; color: var(--tl-text-3); font-size: var(--tl-fs-14); }
.tl-gallery__swatches { display: flex; flex-wrap: wrap; gap: var(--tl-s-3); }
.tl-gallery__swatch { margin: 0; display: grid; gap: var(--tl-s-1); font-size: var(--tl-fs-12); }
.tl-gallery__swatch span { width: 96px; height: 48px; border: 1px solid var(--tl-line-1); border-radius: var(--tl-r-slip); }
.tl-gallery__ramp { display: grid; grid-template-columns: repeat(6, 1fr); max-width: 640px; }
.tl-gallery__ramp span { height: 40px; display: grid; place-items: end start; padding: 2px var(--tl-s-1); color: var(--tl-ink-0); font-size: var(--tl-fs-12); }
.tl-gallery__spec-display { margin: 0; font-size: var(--tl-fs-76); line-height: 1; }
.tl .tl-gallery__trace { border: 0; padding: 0; border-radius: 50%; }
@media (max-width: 1023px) { .tl-gallery { padding: var(--tl-s-5) var(--tl-s-4); } }
```

In `frontend/src/App.tsx` add `import GalleryPage from "./ds/gallery/GalleryPage";` and, directly above the `<Route path="*" …>` line (outside the `Layout` route):

```tsx
        <Route path="/gallery" element={<GalleryPage />} />
```

- [ ] **Step 4: Run — expect PASS** (`npx vitest run src/ds`).

- [ ] **Step 5: Commit**

```bash
git add src/ds/gallery/GalleryPage.tsx src/ds/gallery/GalleryPage.test.tsx src/ds/ds.css src/App.tsx
git commit -m "feat(ds): /gallery living-docs page for tokens and primitives"
```

---

### Task 11: Full verification + visual check

**Files:** none new (fixes only, if a check fails).

- [ ] **Step 1: Whole suite** — Run: `npm test` → Expected: `node:test` format tests pass, all vitest files pass (existing + new). Any existing-test regression is a blocker.
- [ ] **Step 2: Type + build** — Run: `npm run build` → Expected: `tsc -b` clean, Vite build succeeds; `dist/assets` contains Fraunces/Plex `.woff2` files (self-hosted fonts).
- [ ] **Step 3: Visual check** — start `npm run dev`, open `http://localhost:5173/gallery` in the browser pane; screenshot dark and light themes; tab through the page confirming a visible UV focus ring on every control; toggle "Reduce motion" and confirm the ring change is instant and the Spine pulse stops. Confirm `http://localhost:5173/` still renders the legacy UI unchanged.
- [ ] **Step 4: Commit any fixes** with a message describing the fix, then stop — **Deliverable 2 complete; wait for user approval before Deliverable 3.**
