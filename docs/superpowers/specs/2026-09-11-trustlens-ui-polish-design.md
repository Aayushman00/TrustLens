# TrustLens UI Polish — Design Spec

**Status:** drafted from an audited pass over `frontend/src` — every claim below was checked against the real file, not assumed from the original prompt.
**Non-goals (unchanged from original prompt):** no Tailwind, no component kit, no CSS-in-JS, no new button size variants, no floating labels, no custom checkbox art, no stacked-card mobile table rebuild, no indeterminate progress animation, no color-identity change.

---

## Phase 1 — Token reorganization (zero visual diff)

### 1.1 Current state (audited)

`frontend/src/index.css:1-43` has one flat `:root` tier. There is **no raw-palette tier today** — `--amber-bg/text/border`, `--red-*`, `--blue-*`, `--green-*`, `--gray-*`, `--purple-*`, `--accent/-strong/-soft`, `--ink-accent/-strong/-soft` are already named semantically (by status/role), not as raw hex swatches. This differs from the original prompt's assumption of `--c-green-900/700/100` etc. — that raw tier doesn't exist and inventing one for colors that already have semantic names would be pure churn.

**Locked decision:** the raw tier covers only the truly ad-hoc neutrals — the cream (bg/surface/border) family, the ink (text/muted) family, and the green accent family. The existing status-color tokens (amber/red/blue/green/gray/purple, and the ink-accent alias trio) are left exactly as they are, just regrouped under a labeled `/* status colors */` section in the same file. No values change anywhere in this phase.

### 1.2 Raw tier (new names, values copied verbatim from current `:root`)

```css
/* raw palette */
--c-cream-100: #f1efe5;   /* was --bg */
--c-cream-0:   #fffdf8;   /* was --surface */
--c-cream-200: #eae7da;   /* was --surface-sunken */
--c-cream-300: #ddd8c8;   /* was --border */
--c-cream-400: #c7c0aa;   /* was --border-strong */
--c-ink-900:   #17160f;   /* was --text */
--c-ink-500:   #6c6858;   /* was --muted */
--c-green-700: #1e6b4f;   /* was --accent */
--c-green-900: #123f2e;   /* was --accent-strong */
--c-green-100: #e2ece5;   /* was --accent-soft */
```

### 1.3 Semantic tier (unchanged names, now aliasing the raw tier)

```css
--bg: var(--c-cream-100);
--surface: var(--c-cream-0);
--surface-sunken: var(--c-cream-200);
--border: var(--c-cream-300);
--border-strong: var(--c-cream-400);
--text: var(--c-ink-900);
--muted: var(--c-ink-500);
--accent: var(--c-green-700);
--accent-strong: var(--c-green-900);
--accent-soft: var(--c-green-100);
```

`--ink-accent/-strong/-soft` and the six amber/red/blue/green/gray/purple triples stay as literal hex, moved under a `/* status colors */` comment block, untouched.

### 1.4 Radius consolidation

Audited actual usage — the original prompt's premise ("5 ad hoc values: 7/8/10/12/999px") undercounts. Real non-circular values in use: **3, 4, 6, 7, 8, 10, 12, 999px** (circular radii — `50%` on avatars/dots/step-num circles — are out of scope, untouched).

**Locked mapping** (both decisions confirmed in chat):

| New token | Value | Replaces | Used by |
|---|---|---|---|
| `--radius-sm` | 7px | 3, 4, 6, 7px | `code` (4), `.brand-mark` (4), `.chain-tag` (4), `.btn` (6), `.stat-tile` (3), `.dimension-card` (3), input/select/textarea (7), `.nav-links a` (7), `.dimension-note` (7) |
| `--radius-md` | 10px | 8, 10, 12px | `.notice` (8), `pre.json-view` (8), `.skip-link` corner (8), `.auth-shell-note` (8), `.contract-card` (10), `.choice-card` (10), `.dimension-outcome-row` (10), `.dossier-section` (10), `.execution-card` (10), `.filter-bar` (10), `.fries-overall-card` (12→10, explicit drop per original prompt) |
| `--radius-pill` | 999px | 999px | `.local-engine-tag`, `.badge`, `.score-bar-track`, `.score-bar-fill`, `.status-pill`, `.chip`, `.execution-progress-track`, `.dimension-status-chip` |

### 1.5 Pre-existing bug fix (in-scope per original prompt's own instruction)

`frontend/src/components/EvaluationTimeline.tsx:86` — `borderBottom: "1px solid var(--border, #2a2a2a22)"` has a literal hex fallback outside `:root`. Fix: drop the fallback, use `var(--border)` directly (the CSS custom property is always defined by the time this component renders).

### 1.6 Verification

Zero visual diff — every raw/semantic value above is copied verbatim from the current file. Radius changes ARE a visual diff (1-3px deltas on 9 classes) — original prompt explicitly scoped `.fries-overall-card` 12→10 as a visual change; the same logic extends to the 3/4/6px→7px folds. Verify by diffing computed `border-radius` per class before/after, not full-page screenshot diff.

---

## Phase 2 — Accessibility

### 2.1 `:focus-visible` additions

**Existing precedent, audited:** `.contract-card:focus-visible` (`index.css:1183`) is the *only* `:focus-visible` rule in the codebase today, and it reads:
```css
outline: 2px solid var(--ink-accent);
outline-offset: 2px;
```
**Deviation from the original prompt, flagged for review:** the prompt's instruction text says to reuse `outline: 2px solid var(--accent)` — but `--accent` (green, `#1e6b4f`) is a different token from the one actually used (`--ink-accent`, blue, `#1f3a5f`). Since the stated goal is "reuse the existing pattern exactly — don't invent a second focus style," and the only real precedent uses `--ink-accent`, this spec uses `--ink-accent` for every new rule below. If you want `--accent` instead, say so before the plan is written — it's a one-line change once decided.

**Second deviation, audited and locked:** there is no `<input type="radio">` anywhere in the codebase — grepped. `.radio-row` (`ReviewPage.tsx:274`) actually wraps a `type="checkbox"` (`ReviewPage.tsx:276`), not a radio. The only two checkboxes in the app are `CreateEvaluationDraftPage.tsx:241` and `ReviewPage.tsx:276`; the "radios" half of the original prompt's bullet is dead scope.

Checkboxes are also not cleanly "missing" `:focus-visible` — the existing bare `input:focus, select:focus, textarea:focus` rule (`index.css:449-454`, `outline: 2px solid var(--accent-soft); border-color: var(--accent)`) already matches them on *every* focus, mouse included, not just keyboard. Bolting on a separate `input[type="checkbox"]:focus-visible` rule would leave two competing focus treatments on the same element (accent-soft on mouse focus, ink-accent on keyboard focus) — a worse UX bug than the scope creep of touching the shared rule.

**Locked decision:** convert the shared rule itself to `:focus-visible`, unifying every text input/select/textarea/checkbox under one focus treatment instead of adding a parallel checkbox-only rule:
```css
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--accent-soft);
  border-color: var(--accent);
}
```
This keeps the existing `--accent-soft`/`--accent` colors (that pair is untouched — only the pseudo-class changes), and is separate from the new `--ink-accent` `:focus-visible` rules added for elements that had no focus treatment at all:
```css
.tab:focus-visible,
.choice-card:focus-visible,
.dossier-section > summary:focus-visible {
  outline: 2px solid var(--ink-accent);
  outline-offset: 2px;
}
```
`.step` is NOT made focusable in this pass — it's a static status indicator (`.step`/`.step.done`/`.step.current`), never a click target anywhere in `CreateEvaluationDraftPage.tsx`. No `tabindex` or `role="button"` exists on it. Skip it; the original prompt's "(if made clickable)" condition doesn't hold today.

### 2.2 `aria-live`

Grepped: **zero** `aria-live` usage exists anywhere in `frontend/src` today. This isn't an extension of an existing pattern — it's new. Add to `frontend/src/pages/EvaluationDetailPage.tsx`, wrapping the `.execution-progress-track` container (around line 157):
```tsx
<div className="execution-progress-track" role="status" aria-live="polite">
  <div className="execution-progress-fill" style={{ width: `${pct}%` }} />
</div>
```

### 2.3 Contrast — computed, not eyeballed

Real light-mode value is `--muted: #6c6858` on `--bg: #f1efe5` (the original prompt's assumed hex values, `#6d6a60`/`#f6f4ef`, don't match the file). Computed via WCAG relative-luminance formula:

| Pair | Ratio | AA (4.5:1 normal text) |
|---|---|---|
| `--muted` / `--bg` | **4.85:1** | Pass |

Not borderline — passes with margin. All six status text/bg pairs also checked (needed for phase 6 baseline anyway):

| Pair | Ratio |
|---|---|
| green-text / green-bg | 5.56:1 |
| red-text / red-bg | 6.29:1 |
| blue-text / blue-bg | 6.30:1 |
| gray-text / gray-bg | 5.05:1 |
| purple-text / purple-bg | 7.38:1 |
| amber-text / amber-bg | 5.38:1 |

All pass AA. No changes needed to any light-mode color value.

---

## Phase 3 — Motion

Add transitions (verified selectors exist as named):

```css
.tab { transition: border-bottom-color 120ms ease, color 120ms ease; }

.card, .contract-card, .choice-card {
  transition: border-color 120ms ease;
}
```
(`.card:hover`, `.contract-card:hover`, `.choice-card:hover:not(:disabled)` already change `border-color`/`box-shadow` per `index.css:1178-1181, 1314-1317` — none currently declare a `transition` property. This just adds it.)

**Dossier open/close — audited, deviated from the original prompt's naive CSS:** the three consumers that actually use `.dossier-section`/`.dossier-section-body` — `EvidenceDossier.tsx` (both `<details>` blocks), `ReportPage.tsx:273-275`, `ReportTraceabilityPanel.tsx` — are native `<details>`/`<summary>` with no JS-controlled open state. (`EvaluationDetailPage.tsx:174`'s `<details>` is a plain, unclassed telemetry toggle — it never gets `.dossier-section` styling and is out of scope here regardless.) A plain `transition: opacity 150ms ease` on `.dossier-section-body` scoped to `[open]` would be inert — native `<details>` unmounts closed content entirely, so there's no rendered box for the browser to transition from; content would just snap in at full opacity, same as today.

**Locked:** use `@starting-style` + `transition-behavior: allow-discrete` (CSS-only, no JS, no new dependency — Baseline 2024, works in current Chrome/Edge/Safari; degrades gracefully to an instant/no-animation open on browsers without it, e.g. current Firefox — never broken, just not always animated):
```css
.dossier-section-body {
  transition: opacity 150ms ease, display 150ms allow-discrete;
}

.dossier-section:not([open]) .dossier-section-body {
  opacity: 0;
  display: none;
}

@starting-style {
  .dossier-section[open] .dossier-section-body {
    opacity: 0;
  }
}
```
No markup or React change needed — `.dossier-section-body` already exists as a class (`index.css:1569`, wrapping the content inside every dossier `<details>`), and `[open]` is a native `<details>` state, not something the app manages.

`.execution-progress-fill` already has `transition: width 0.3s ease` (`index.css:1575`) — leave as-is, it's the real-number-backed template the original prompt references. No indeterminate variant, confirmed non-goal.

Global reduced-motion rule, added once at the end of `index.css`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
```

---

## Phase 4 — Loading states

### 4.1 New component

`frontend/src/components/Skeleton.tsx` — a single component rendering N gray gradient-pulse blocks, shaped via props (`rows`, `height`) so callers can approximate a table or stat-tile grid. ~30 lines, CSS-only animation (already exempted from the reduced-motion blanket rule is NOT needed — pulse animation should also respect `prefers-reduced-motion`, so it inherits the global rule above with no special-casing).

### 4.2 Wiring — audited actual fetch patterns

**`OverviewPage.tsx` (confirmed bug, matches original prompt's complaint exactly):** lines 15-41 fetch models and evaluations via one `Promise.all`, and `loading` (line 41) is `models == null && evaluations == null && error == null` — a single shared gate. Fix: split into two independent `useEffect`/`useState` pairs (`modelsLoading`, `evaluationsLoading`), each rendering its own table or `<Skeleton>` independently, so the models table can render while evaluations is still in flight.

**`ModelsPage.tsx`** and **`EvaluationsHistoryPage.tsx`**: each already has a single `loading` state gating a single list — swap the `<Spinner>` for `<Skeleton>` shaped like their respective table, no structural change needed (single fetch, single loading state, already correct pattern — just the visual treatment changes).

Spinner stays unchanged everywhere else (form submissions, single-record fetches) per original prompt's explicit carve-out.

---

## Phase 5 — Consistency fixes

### 5.1 `.dimension-status-chip`

Current markup, `EvaluationDetailPage.tsx:160-170`:
```tsx
<span key={dim} className="dimension-status-chip">
  {dim.charAt(0) + dim.slice(1).toLowerCase()}
  {p ? " · done" : " · pending"}
</span>
```
Replace the string suffix with icon+label, as its own small component (not `StatusPill` reuse — confirmed by original prompt's reasoning: done/pending isn't one of `StatusPill`'s 8 states in `StatusPill.tsx`). New `frontend/src/components/DimensionProgressChip.tsx`:
```tsx
export default function DimensionProgressChip({ label, done }: { label: string; done: boolean }) {
  return (
    <span className="dimension-status-chip">
      <span aria-hidden="true">{done ? "✓" : "○"}</span> {label}
    </span>
  );
}
```
Usage becomes `<DimensionProgressChip key={dim} label={dim.charAt(0) + dim.slice(1).toLowerCase()} done={!!p} />`.

### 5.2 Sticky `<thead>`

`EvaluationsHistoryPage.tsx:115` has exactly one `<thead>`. Add:
```css
.table-wrap thead th {
  position: sticky;
  top: 0;
  background: var(--surface);
}
```
Scoped to `.table-wrap thead` (not a bare `thead` rule) so it doesn't affect any other table on the site that isn't inside a scrollable wrap.

**Locked, deviates from a literal single-page reading of the original prompt:** `.table-wrap` isn't unique to `EvaluationsHistoryPage` — it's used in 8 places (`OverviewPage.tsx` ×2, `ModelDetailPage.tsx`, `EvaluationDetailPage.tsx`, `ReportPage.tsx` ×2, `ReviewPage.tsx`, `EvaluationsHistoryPage.tsx`). The class-selector rule above applies site-wide the moment it's added. Confirmed with user: apply it site-wide rather than inventing a page-specific wrapper class — sticky+`top: 0` is inert on any table short enough to already fit the viewport, so there's no downside on the other 7 tables, only a consistency win.

### 5.3 Empty-state copy

Audited: **good examples** already in the codebase — `CreateEvaluationDraftPage.tsx:322` ("No models yet — import one first."), `OverviewPage.tsx:98,132` ("No models yet — ...", "No evaluations yet — ..."). **Bad example to fix:** `ModelsPage.tsx:51` — `"Nothing registered yet — <Link>import a model</Link>."` → change to `"No models registered yet — import one first."` (matching the established pattern's verb-first action clause).

### 5.4 Tablet breakpoint (600-900px)

`.identity-header` (`index.css:1090-1097`) already has `flex-wrap: wrap`. Current breakpoints: `.app-shell`/`.sidebar` react at `900px` (`index.css:292`), `.container` padding drops at the same `900px` query (`index.css:320`) straight from `1.75rem 2rem 4rem` to `1.25rem 1rem 3rem` — there is no intermediate step, confirming the original prompt's complaint. Add one intermediate breakpoint:
```css
@media (max-width: 900px) and (min-width: 601px) {
  .container {
    padding: 1.5rem 1.25rem 3.5rem;
  }
}
```
This sits inside the existing `max-width: 900px` block's cascade — since CSS applies in source order and both rules match in the 601-900px range, this narrower-range rule must be declared BEFORE the existing `@media (max-width: 900px)` block, or given equal specificity it'll lose to the later one. Verify `.identity-header` wrapping manually in-browser at 700px width with a long model name + badge + button; no code change anticipated there beyond the padding step, but confirm before closing this task.

---

## Phase 6 — Dark mode (separate, reviewed on its own — implement last)

### 6.1 Mechanism

Per original prompt: light values stay default on bare `:root`; `@media (prefers-color-scheme: dark)` scoped under `:root:not([data-theme="light"])` redefines only the ten semantic tokens (`--bg`, `--surface`, `--surface-sunken`, `--border`, `--border-strong`, `--text`, `--muted`, `--accent`, `--accent-strong`, `--accent-soft`) plus the six status triples; repeat verbatim under `:root[data-theme="dark"]`. Raw tier and every component class are never touched — everything already reads through tokens (confirmed — the only literal-hex-outside-root hit was the one `EvaluationTimeline.tsx` fallback fixed in phase 1).

### 6.2 Proposed dark values (same hue identity, re-tuned for contrast, not inverted)

```css
--bg: #1a1814;
--surface: #242019;
--surface-sunken: #14120e;
--border: #3a352a;
--border-strong: #4d4636;
--text: #f0ede4;
--muted: #a39c88;
--accent: #4caf82;
--accent-strong: #7ecba3;
--accent-soft: #1f3327;
--ink-accent: #7ba3d9;
--ink-accent-strong: #a9c6ea;
--ink-accent-soft: #1f2c3d;

--amber-bg: #46350f; --amber-text: #e8b563; --amber-border: #5c4720;
--red-bg: #46201a;   --red-text: #ef7b68;   --red-border: #5c2b22;
--blue-bg: #1c2c46;  --blue-text: #7fa8e0;  --blue-border: #28405c;
--green-bg: #1c3d26; --green-text: #6fcf97; --green-border: #245c37;
--gray-bg: #332e24;  --gray-text: #9b968a;  --gray-border: #3d392c;
--purple-bg: #332648;--purple-text: #c9a6f0;--purple-border: #453262;
```

### 6.3 Computed contrast — dark mode (all six safety pairs + muted/bg)

| Pair | Ratio | AA |
|---|---|---|
| `--muted` / `--bg` | 6.47:1 | Pass |
| `--text` / `--bg` | 15.14:1 | Pass |
| green-text / green-bg | 6.33:1 | Pass |
| red-text / red-bg | 5.20:1 | Pass |
| blue-text / blue-bg | 5.73:1 | Pass |
| gray-text / gray-bg | 4.57:1 | Pass (tightest — 0.07 over threshold, don't erode further in implementation) |
| purple-text / purple-bg | 6.75:1 | Pass |
| amber-text / amber-bg | 6.32:1 | Pass |

### 6.4 Mandatory safety-distinction re-check (per original prompt — new code, own review)

- **WITHHELD (purple) vs FAILED (red), against each other:** both chip backgrounds sit at near-identical luminance (`red-bg`/`purple-bg` ratio 1.03:1) — by design, same as the existing light-mode pair (`#fbe9e7` red-bg vs `#ece7f6` purple-bg is likewise low-contrast against each other). Distinction is by **hue**, not luminance, consistent with the established convention — not a regression.
- **WITHHELD vs FAILED, against dark surface:** both chip backgrounds (`#46201a`, `#332648`) sit at ~1.14-1.17:1 luminance ratio against `--surface` (`#242019`) — visibly lighter/more saturated than the card, same relationship as light mode's chips against `--surface`. Chips read as chips, not as blended-into-card.
- **NOT_APPLICABLE (gray) vs a darkened "zero":** `gray-bg` (`#332e24`) is warm-toned (shares the cream/olive hue family, not a flat gray-black), and `gray-text` (`#9b968a`) at 4.57:1 against it reads as a distinct neutral chip, not as a dimmed/failed score. Side-by-side check against `--red-bg`/`--amber-bg` (also warm-dark) confirmed the gray sits at lower saturation, not lower value alone — the differentiator survives in dark mode.

### 6.5 Required manual check before merge (per original prompt)

All eight `StatusPill` states (`StatusPill.tsx:16-27`: Evaluated, Running, Not configured, Insufficient evidence, Failed, Withheld, Proxy, Skipped) rendered side-by-side in light and dark, screenshotted, compared — this is a manual/visual step, not something this spec can complete on paper. Flag as a task-level acceptance check in the implementation plan.

---

## Acceptance criteria (carried over from original prompt, unchanged)

- Existing Vitest suite passes unchanged, except new/updated coverage for `.dimension-status-chip` → `DimensionProgressChip` markup change.
- Zero visual diff after phase 1's token/alias work (radius fold IS a visible 1-3px change, called out above — not "zero diff" for that sub-part).
- This document is the documented WCAG AA contrast check for both light and dark semantic pairs, required before phase 6 ships.
- All eight status states manually compared side-by-side in light and dark before merge (6.5).
