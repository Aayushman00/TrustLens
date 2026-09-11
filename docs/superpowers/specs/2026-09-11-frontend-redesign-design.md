# TrustLens frontend redesign — "Audit Ledger"

## Context

TrustLens is a local-first ML model evaluation tool: users import a Hugging
Face model, configure Fairness/Robustness dimensions against a dataset,
run probes, and review evidence-backed results (evidence chains, FRIES
confidence scoring, dossiers). The current UI (warm cream background,
Source Serif 4 + IBM Plex Sans, forest-green/navy accents) is functional
but visually generic and under-explains its own workflow to a first-time
user — buttons, dimensions, and terms like "FRIES" or "confidence" are not
self-explanatory.

Goal of this pass: a full visual redesign (design tokens + every page and
shared component) that reads as a professional, precise audit/compliance
tool — not a generic SaaS dashboard — while making the workflow legible
through inline explanation rather than through a tour or modal.

## Scope

Full system: `frontend/src/index.css` (design tokens + shared component
styles) and every page/component listed below. No backend changes. No
change to component logic/data flow — this is a visual + copy pass.

Files touched:
- `frontend/src/index.css` — full token and component-style rewrite
- `frontend/src/components/*.tsx` — visual updates, inline help copy
  additions, no prop/behavior changes unless a copy string requires a new
  optional prop (e.g. a `helpText` prop on a form field)
- `frontend/src/pages/*.tsx` — layout/copy updates within existing data
  flow
- `frontend/index.html` (or wherever fonts are loaded) — swap font
  imports

## Design tokens

### Color

Cool, precise palette — avoids both the common warm-cream-serif AI look
and the near-black-plus-neon-accent look. Base is a pale, slightly
green-grey paper (not cream); ink is near-black graphite (not pure
black); one confident indigo accent carries all primary UI action and
navigation; amber/red/green stay strictly semantic (risk/evidence
signaling), never decorative.

```
--bg: #F1F3EF
--surface: #FFFFFF
--surface-sunken: #E7EAE4
--border: #D7DBD2
--border-strong: #B8C0B2
--ink: #16191C
--ink-muted: #5A6058

--accent: #2A3EA8
--accent-strong: #1C2B7A
--accent-soft: #E4E7F7

--risk-amber-bg: #FDF3E1
--risk-amber-text: #8A5A0B
--risk-amber-border: #EED9AE

--risk-red-bg: #FBE9E7
--risk-red-text: #9C2F24
--risk-red-border: #EFC7C0

--evidence-green-bg: #E2F0E6
--evidence-green-text: #1B6B3A
--evidence-green-border: #BCDCC6

--info-blue-bg: #E7EEF9
--info-blue-text: #24559C
--info-blue-border: #C8D8F0

--gray-bg: #EDEAE1
--gray-text: #66625A
--gray-border: #DDD7C8

--purple-bg: #ECE7F6
--purple-text: #55388F
--purple-border: #D7CBEE
```

(Amber/red/green/blue/gray/purple roles are carried over unchanged in
*meaning* from the current CSS — only the base/accent identity changes.
This preserves every existing semantic-status usage: `.status-*`,
`.chain-tag-*`, `.badge-*`.)

### Type

- Display/headings: **Fraunces** (variable slab-serif). Distinctive,
  reads like a report masthead rather than a generic "AI serif." Used
  for `h1`, `h2`, page titles, the FRIES score display, dimension-card
  titles.
- Body/UI/labels: **IBM Plex Sans** — unchanged. Already the correct
  register for a technical tool; keep as-is.
- Data/IDs/hashes/mono values: **IBM Plex Mono** — unchanged.

Type scale (rem, at 15px base, unchanged base size):
- h1: 2rem / 600 / -0.01em
- h2: 1.35rem / 600
- h3 (new, for card titles currently styled ad hoc): 1.05rem / 600
- body: 1rem / 400 / line-height 1.55
- small/meta: 0.82rem
- micro (badges/labels): 0.7rem, letter-spacing 0.02em — **no
  all-caps by default**; existing all-caps badges (`.badge`,
  `.status-pill`) are a pre-existing pattern tied to status semantics
  and are kept as-is (they encode meaning, not decoration), but no
  *new* all-caps treatments are introduced elsewhere (nav labels, card
  titles, section headers stay sentence case).

### Layout

- Left-aligned throughout; no centered marketing-style hero anywhere —
  this is a working tool, not a landing page.
- Radius scale, applied deliberately instead of the current
  arbitrary 3px/4px/6px/7px/10px mix:
  - `--radius-sharp: 3px` — data containers (tables, stat tiles, dimension
    cards) — precision/document feel
  - `--radius-soft: 8px` — interactive surfaces (buttons, inputs, choice
    cards, contract cards)
  - `--radius-pill: 999px` — status badges/pills only
- Numbered sequences (stepper, dimension order) stay numbered because
  they are genuinely sequential; nothing else gets numbered markers.
- Sidebar shell layout (fixed left nav, sticky, responsive collapse to
  top bar under 900px) is kept structurally — it's the right pattern for
  a tool used repeatedly — but nav active/hover states move to the new
  accent, and each nav section gets a one-line (dismissible,
  localStorage-remembered) description on first visit.

## Per-page/component treatment

### Layout.tsx (shell/sidebar)
- Nav active state: `--accent-soft` background, `--accent-strong` text
  (was navy ink-accent).
- Add a short one-line description under each `.nav-section-label`
  (e.g. under "Workspace": "Models, evaluations, and results you own
  locally") — dismissible per-section via a small close affordance,
  state in localStorage so it doesn't reappear once dismissed.

### OverviewPage.tsx
- Stat tiles (`.stat-tile`) unchanged structurally; add `.stat-tile-sub`
  copy explaining what's counted where it isn't obvious, e.g. under
  "In progress": "Running or waiting for your review" (already present
  as sub-copy in some cases — extend to all four tiles consistently).

### CreateEvaluationDraftPage.tsx (wizard)
- Each step in the stepper gets a one-sentence explanation directly
  under its heading, in the interface's voice, stating what happens if
  the step is skipped (e.g. Robustness: "Needs a labeled dataset —
  leave this off and Robustness is marked Not Applicable, not failed").
- `DatasetIntakeForm.tsx` / `ColumnRoleMappingForm.tsx`: every field
  (text_column, target_column, label_mapping, sensitive_column) gets a
  `field-hint` line already partially present in CSS
  (`.field-hint`) — extend to cover every field that isn't
  self-explanatory from its label alone.
- Fairness/Robustness enable checkboxes get one line of copy beside the
  checkbox, visible before the section expands, stating what enabling it
  does (e.g. "Checks the model's predictions for score gaps across a
  sensitive attribute you map below").

### EvaluationDetailPage.tsx / ReportPage.tsx
- `DimensionCard.tsx`, `EvidenceDossier.tsx`, `ScoreBars.tsx` keep
  their current structural approach (progressive disclosure via
  `<details>`, per-dimension status pills) — this is already the right
  pattern for evidence-heavy content.
- Add a persistent, short explainer strip (not a modal, not a tour) near
  the FRIES score: "FRIES confidence reflects how much verified evidence
  supports this result — not model accuracy." Status-pill meanings
  (`Evaluated`, `Not applicable`, `Insufficient evidence`, `Withheld`,
  `Proxy`) get a one-line legend accessible via a small always-visible
  key, not hidden in a tooltip (per your "inline over tooltip" choice).

### Shared components (buttons, forms, cards, badges)
- `.btn` family: consolidate to the 3-radius scale above; hover/focus
  states get a visible 2px outline in `--accent` for keyboard focus
  (currently only `outline: 2px solid var(--accent-soft)` on form
  inputs — extend visible focus rings to all interactive elements:
  buttons, tabs, choice cards, contract cards).
- Form inputs: live validation — error text appears under the specific
  field on blur (new behavior for forms that currently only show a
  top-of-form `ErrorNotice`), in addition to the existing top-level
  notice for request-level errors.
- Transitions: 150–200ms ease on wizard step change, `<details>`
  expand/collapse, tab switch, button/card hover — no page-load
  fade-ins or staggered reveals.

## Non-goals

- No new component logic, no new API calls, no data-flow changes.
- No dark mode (out of scope for this pass).
- No onboarding tour/modal — explanation lives inline in the UI itself,
  per your answer.
- Existing accessibility patterns (`.skip-link`, `.visually-hidden`,
  `aria-*` already in components) are preserved and extended, not
  replaced.

## Testing

- Existing component/page tests (`*.test.tsx`) must continue to pass —
  copy additions and class-name changes should not break text-based
  test assertions; where a test asserts old copy, update the assertion
  to match new copy in the same commit as the copy change.
- Visual check: run the dev server and walk the full create-evaluation
  flow + evaluation detail/report view at desktop and ~400px mobile
  width, both to confirm layout doesn't break and to confirm every
  interactive element has a visible focus ring.
