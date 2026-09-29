# TrustLens UI/UX Redesign — Design Brief & Specification

- **Status:** Deliverable 1 — awaiting approval
- **Branch:** `feat/ui-redesign` (from `5ed31e9`)
- **Date:** 2026-09-29
- **Scope decision (locked):** Option C — truth-only on the current `/v1` API now; richer live probe
  telemetry is a future backend extension, documented separately in
  [`2026-09-29-theatre-progress-events-proposal.md`](2026-09-29-theatre-progress-events-proposal.md)
  and **not implemented** in this iteration.

---

## 0. Thesis

**"Show your work."** TrustLens is an instrument, not a scoreboard. The interface makes an audit
visible, inspectable and reproducible — calm, rigorous, quietly beautiful. One visual idea carries
the whole product:

> **Three materials for three layers.** Evidence, Risk assessment and FRIES score are rendered in
> three physically distinct *materials*, so the layers can never visually blur — and a single
> *trace thread* is the only thing allowed to cross between them.

| Layer | Material | Looks like | Colour rule |
|---|---|---|---|
| **Evidence** (raw metrics, hashes, refs) | **Specimen paper** | Mono type, hairline ruled slips, no fills, no glow | Neutral greys only. Never the score ramp. A DPD of 0.31 is ink on paper, not a colour. |
| **Risk assessment** (O/S/D, T) | **Instrument** | Dials, needles, tick scales, engraved labels | Score ramp on the **T** value and dial arcs only |
| **FRIES score** (aspect + weighted total) | **Lens** | Display serif numerals, the pentagon, soft UV glow | Score ramp + the single UV accent halo |

Everything else (navigation, forms, chrome) is quiet structural ink.

---

## 1. What exists today (audited, not assumed)

| Fact | Source |
|---|---|
| Stack: React 19, Vite 6, react-router 7, TS 5.7, vitest + Testing Library. Only runtime dep is react-router. One 46 KB `index.css`. | `frontend/package.json`, `frontend/src/index.css` |
| 11 routes: `/`, `/models`, `/models/import`, `/models/:id`, `/evaluations`, `/evaluations/new`, `/evaluations/:id`, `/evaluations/:id/review`, `/reports/:evaluationId`, `/documentation`, `/settings` | `frontend/src/App.tsx:21-33` |
| Evaluation detail polls `GET /v1/evaluations/{id}` + `/events` every **500 ms** while status is active | `EvaluationDetailPage.tsx:34,68,80` |
| Exactly **10 event types**: `evaluation_created`, `evaluation_requeued`, `evaluation_started`, `probes_completed`, `agent_completed`, `evaluation_failed`, `awaiting_review`, `human_review_submitted`, `evaluation_finalized`, `report_generated` | `backend/app/db/repositories/evaluation_event.py:24-33` |
| **No per-probe start / batch / row events.** Probe progress = `count(probe rows) / 5`. A lane is either *not landed* or *landed*. | `evaluation_service.py:274` |
| Per-probe landing time **is** knowable: `evidence_refs[].created_at` | `eval_results_v2/*.json` |
| Safety probe = documentation-coverage check (`checks_present`, `checks_required`, `coverage_ratio`). **Runs no prompts.** | probe `metric_values` keys |
| Explainability probe = model-card sections (`sections_present`, `sections_required`, `contradictions`). **No SHAP/LIME.** | probe `metric_values` keys |
| Robustness = one attack: `clean_accuracy`, `robust_accuracy`, `accuracy_drop`, `attack_success_rate`, `perturbation_coverage`. **No per-perturbation-type breakdown.** | probe `metric_values` keys |
| Fairness: `demographic_parity_difference`, `equalized_odds_difference`, `subgroup_f1_spread`, CIs (`dp_ci`, `eo_ci`, `f1_ci`), `groups`, `excluded_groups`, `min_group_n`, `min_group_n_observed` | probe `metric_values` keys |
| Scoring: `Pi = ∛(O·S·D)`, veto if any component is 0, aspect `Ti` = mean of its risks' `Pi`, `T = Σ ωᵢTᵢ`, default equal weights **over the aspects present**, each ω ≥ 0.1, Σω = 1. `fries_score` may be `null` when `scoring_withheld`. | `backend/app/scoring/fries.py:1-17,89-112` |
| `overall_confidence` is a **scalar 0–1**, not an interval on the score. | `FinalScoreRead` |
| Drafts: `incomplete / validated / consumed / stale`. The only stale cause: *model revision changed since intake*. Terminal — never transitions back. | `evaluation_service_v2.py:10,132-138`, `db/models.py:124` |
| Publish/unpublish exist. **No** compare/leaderboard endpoint, **no** report-version list (only latest `GET /v1/reports/{id}`), **no** draft list, **no** "can this run here" import pre-check. | `backend/app/routers/v1/*` |
| Replay seed data: full `EvaluationRead` snapshots for 7 runs, all `AI_AUTONOMOUS`, no event arrays. | `results/flawed_model_suite/eval_results_v2/` |
| Prior art: Stitch "Precision Scientific Laboratory" mockups (light, teal). Treated as reference only. | `stitch_trustlens_platform_ui/` |

### 1.1 Spec ↔ reality reconciliation (what the UI will honestly do instead)

| Requested | Honest treatment in this iteration |
|---|---|
| Rows streaming through the model, live group bars | Lane shows **Awaiting evidence** while `RUNNING` and no row exists. When the probe row lands, its instrument **draws once from the persisted `metric_values`** (one 400 ms settle, labelled with landing time). No per-row animation. |
| Per-lane `running` state | Not knowable. Lane states are `awaiting` / `landed:<ProbeStatusValue>` / `not produced` (evaluation failed before landing). The *evaluation* shows RUNNING; lanes never claim to be individually running. |
| Batch counter, throughput | Shown as `—` with tooltip "Not reported by backend (methodology v…)". Slot reserved for the future event contract. |
| Per-lane elapsed time | `landed +38.2 s after evaluation_started` (from `evidence_refs[].created_at` − event timestamp). |
| Safety: prompts, unsafe rate, flagged examples | Lane shows **safety-documentation coverage** (checks present / required). A clearly marked slot reads *"Behavioural safety probing — not measured by this methodology version."* No blurred example UI is built (nothing to blur). |
| SHAP/LIME token highlights | Same treatment: "Feature attribution — not measured by this methodology version." |
| Per-perturbation-type breakdown | Single-attack readout: clean vs robust accuracy, drop, attack success rate, coverage, attack name/ε. |
| Integrity hashing animation | No live hashing occurs client-side. Seal renders from persisted `checks`/`identity` and evidence hashes. Verified/mismatch seal is **static** and derived only from backend fields. |
| Uncertainty band on overall score | Score shown with **confidence meter** (scalar) and, where metrics carry CIs (`dp_ci` etc.), CI whiskers on the *evidence* layer. No fabricated ± interval on FRIES. |
| Missing dimensions "hollow, never zeroed or averaged in" | Pentagon vertex hollow + dashed. **Plus explicit disclosure** that the backend renormalises default weights over present aspects (`fries.py:99-100`): "Computed over 4 of 5 dimensions — weights 0.25 each." |
| Weight-profile toggle | Client-side **what-if preview** reproducing `fries_total` constraints (ω ≥ 0.1, Σ = 1). Rendered in a hatched "PREVIEW — not the recorded score" frame. Recorded score never changes. |
| Report versions (append-only) list | Show current `version`, `json_hash`, `pdf_hash`, `generated_at`. Version history = gap (proposal G4 below). |
| Compare / Leaderboard | Client-side grouping of `GET /v1/evaluations` by comparability key. No new endpoint. |
| Import "can it run here" check | Show what import returns (pinned revision, checksum, metadata). Memory/device estimate = gap (proposal G2). |
| Human review stage in fixtures | Fixtures are `AI_AUTONOMOUS`; Theatre shows the stage as **"Not required — AI_AUTONOMOUS mode"** with the mode disclosure, never a fabricated review. |

---

## 2. Mood board (described)

1. **Forensic light table at night.** Dark room, a single ultraviolet lamp making specific marks
   fluoresce. → Dark ink canvas; the UV accent only ever marks *what you are inspecting*.
2. **Letterpress lab notebook.** Hairline rules, marginal annotations, specimen numbers stamped in
   mono. → Evidence slips, marginalia explaining methodology inline.
3. **Analogue instrument panels** (Braun/Rams, Tektronix scopes). Engraved tick scales, restrained
   needles, no chrome. → O/S/D dials.
4. **Editorial data journalism** (FT, The Pudding). Big serif numerals, generous whitespace,
   annotations sitting *on* the chart. → Score typography, pentagon annotations.
5. **Wax seals and chain-of-custody tags.** → Integrity seal, human-review seal, hash badges.

Anti-references: neon cyberpunk dashboards, gradient KPI tiles, gauges with red/amber/green bands,
confetti on completion.

---

## 3. Colour

### 3.1 Canvas (dark primary)

| Token | Hex | Use | Contrast on `ink-0` |
|---|---|---|---|
| `ink-0` | `#0B0D12` | app background | — |
| `ink-1` | `#12151C` | surfaces / cards | — |
| `ink-2` | `#1A1E27` | raised / popovers | — |
| `line-1` | `#262C38` | hairlines | 1.5:1 (decorative only) |
| `line-2` | `#606A7E` | control borders | 3.6:1 / 3.4:1 on `ink-1` (non-text UI ✔) |
| `text-1` | `#E8EAF0` | primary text | 16.2:1 ✔ |
| `text-2` | `#A3ABBA` | secondary text | 8.4:1 ✔ |
| `text-3` | `#7A8394` | tertiary / captions | 5.1:1 (4.8:1 on `ink-1`) ✔ AA body |

Light theme mirrors roles: `ink-0 #F6F5F1` (warm paper), `ink-1 #FFFFFF`, `text-1 #14161B` (16.6:1),
`text-2 #4A5160` (7.3:1), `text-3 #636B7A` (4.9:1), lines `#D9D7D0` (decorative) / `#7E8490`
(controls, 3.4:1). Ratios above computed with the WCAG 2.x formula; all pairs re-verified in
Deliverable 2 by an automated contrast test (see §10).

### 3.2 The one accent — Ultraviolet

`uv-400 #A594FF` (dark, 7.7:1 on `ink-0`) / `uv-600 #5B45E0` (light, 5.7:1 on paper).
**Interaction and attention only:** focus rings, current pipeline stage, active trace thread,
selected row, primary button. **Never encodes data.**

Dimension hues measured: dark 6.3–8.4:1 on `ink-1`; light 4.6–5.3:1 on paper — all ≥ AA for text.

### 3.3 FRIES identity hues (Okabe–Ito derived, CVD-safe)

Identity only — a hue says *which dimension*, never *how good*. Always paired with a **glyph shape**
and a **letter monogram**, so colour is never the sole channel.

| Dim | Hue (dark) | Hue (light) | Glyph | Monogram |
|---|---|---|---|---|
| Fairness | `#E6A23C` amber | `#9A5F00` | ● circle (balance point) | **F** |
| Robustness | `#5DB8EC` sky | `#0A6AA6` | ■ square (block) | **R** |
| Integrity | `#E57A5A` seal-wax | `#B0452A` | ⬢ hexagon (seal) | **I** |
| Explainability | `#D286B6` orchid | `#A0467F` | ◆ diamond (lens) | **E** |
| Safety | `#35C29A` jade | `#0B7F5E` | ▲ triangle (guard) | **S** |

Used consistently for: lane headers, pentagon axis labels/ticks, chip borders, timeline nodes.
Pairwise distinguishability checked under deuteranopia/protanopia/tritanopia simulation in
Deliverable 2 (ΔE₀₀ ≥ 10 target between any two hues).

### 3.4 Trust ramp (score layer only)

Perceptually uniform, CVD-safe sequential ramp derived from **cividis**, clipped so the low end
stays visible on dark ink (≥ 3:1 against `ink-1`; lowest stop 4.3:1). **Low trust = dim
slate-blue, high trust = luminous straw** ("trust glows"). Anchor stops (luminance strictly
increasing):

```
0 #5E7AB0 (4.3:1)  3 #7D8290 (4.8:1)  5 #8E8A7E (5.3:1)  7 #A89A70 (6.5:1)  8.5 #C6AE5E (8.4:1)  10 #F2D65A (12.7:1)
```
(ratios vs `ink-1`; intermediate values interpolated in OKLCH. Light theme uses a separate,
darkened ramp with the same hue path, tuned in Deliverable 2.)

Rules: ramp colour is **always** accompanied by the numeral; no red/green; veto (Pi = 0) gets a
distinct **hatched** fill + "VETO" label, not just the darkest colour.

### 3.5 Status colours

Status uses **shape + word first**, colour second: `EVALUATED ✓`, `INSUFFICIENT_EVIDENCE ◐`,
`NOT_APPLICABLE ⊘`, `SKIPPED ⤼`, `FAILED ✕`, `PROXY ≈`, `awaiting ○`. Failure uses
`#FF8A7A` text + ✕ icon + word; never colour alone.

---

## 4. Typography

All faces OFL, **self-hosted** (local-first: no Google Fonts CDN at runtime) via `@fontsource`
packages.

| Role | Face | Why | Specimen use |
|---|---|---|---|
| Display | **Fraunces** (variable, opsz + SOFT axes) | Editorial, confident, reads as "published finding"; big numerals have presence | FRIES total `4.08`, page titles, aspect scores |
| UI sans | **IBM Plex Sans** | Engineered, highly legible, `tnum` support, scientific lineage | All UI text, tables, forms |
| Mono | **IBM Plex Mono** | Same family metrics as UI sans; hashes, evidence IDs, metric keys | `sha256:86ad1c…`, `demographic_parity_difference` |

Scale (1.250 major third, rem): `12 · 14 · 16 (base) · 20 · 25 · 31 · 39 · 49 · 61 · 76`.
`font-variant-numeric: tabular-nums lining-nums` on every numeric element via a `.num` utility and
on all Plex text in tables. If Fraunces' `tnum` proves inadequate for aligned columns, score
*tables* fall back to Plex Sans; Fraunces stays for hero numerals only.

Specimen (rendered in the Deliverable 2 gallery):

```
Fraunces 61/opsz 72   4.08            FRIES · traceable aggregation, not a safety guarantee
Plex Sans 16          Demographic parity difference across 6 identity groups
Plex Mono 13          ev_c8b8f84a  application/json  sha256:86ad1cd3…a149  ⧉
```

---

## 5. Spacing, grid, elevation

- 4 px base; tokens `space-1…12` = `4 8 12 16 24 32 40 48 64 80 96 128`.
- 12-column grid, 24 px gutters desktop, 16 px tablet; max content width 1440 px; Theatre is
  full-bleed.
- Breakpoints: `≥1280` full, `1024–1279` compact, `768–1023` tablet (lanes stack). Below 768 is
  out of scope (read-only fallback: single column, no Theatre animation).
- Elevation is **not** drop shadow (lost on dark). Levels are: surface step (`ink-0→1→2`) +
  hairline + optional 1 px inner top highlight. Only the score *lens* gets a soft UV glow.
- Radius: 2 px slips (paper), 8 px cards, 999 px chips. Deliberately small — instruments, not bubbles.

---

## 6. Motion

**Principle: motion only ever reports a real state change.** Nothing moves unless backend state
changed (or the user acted).

| Token | Duration | Easing | Used for |
|---|---|---|---|
| `motion-micro` | 150 ms | `cubic-bezier(.2,0,0,1)` | hover, focus, chip toggle |
| `motion-std` | 240 ms | spring approximation via CSS `linear()` (critically damped) | panel open, dial needle settle |
| `motion-land` | 400 ms | spring `linear()` (slight overshoot ≤ 4 %) | evidence landing, pentagon vertex grow |

- Implementation: CSS transitions + WAAPI; springs as precomputed `linear()` easings. **No
  animation library.** Only `transform`/`opacity`/SVG `stroke-dashoffset` animated (compositor-friendly).
- **Pulse** on the current spine stage: 2 s opacity breathing on a ring, *only* while
  `evaluations.status` is an active status. Stops the instant status changes.
- **Evidence landing**: when a probe row first appears, its evidence slips slide 8 px + fade in,
  and a single trace thread draws from lane → the relevant risk card (400 ms). Once per real event.
- **Burst handling:** if several state changes arrive in one poll (e.g. three doc probes land
  within 20 ms, as in real runs), landings are **staggered 80 ms** for legibility, each still
  labelled with its true timestamp. Stagger never delays information beyond 400 ms total.
- **Reduced motion** (`prefers-reduced-motion: reduce` or in-app toggle): all durations → 0; pulse
  replaced by a static `● ACTIVE` label; thread drawn instantly; stagger removed. Every animated
  element has an identical static end-state (tested, §10).

---

## 7. Design-system layer (Deliverable 2 preview)

Location: `frontend/src/ds/` — `tokens.css` (CSS custom properties, both themes), `primitives/*.tsx`,
`gallery/GalleryPage.tsx` at route `/gallery` (dev + prod, it doubles as living docs).

| Primitive | Layer | Notes |
|---|---|---|
| `Card`, `Slip` | chrome / evidence | Slip = hairline specimen paper |
| `StatusChip` | any | glyph + word + optional colour |
| `DimensionMark` | identity | glyph + monogram + hue |
| `HashBadge` | evidence | short hash, full on hover/focus, copy button, `aria-label` with full hash |
| `EvidenceChip` | evidence | evidence_id, content type, short hash; clickable → TracePanel |
| `Gauge` | evidence | linear metric readout with CI whiskers; neutral ink only |
| `Dial` | assessment | O/S/D 0–10 engraved dial; "higher = safer" affordance |
| `ScoreRing` | score | T or aspect score, ramp colour + numeral; hatched VETO state |
| `Pentagon` | score | 5 axes, 0–10; hollow dashed vertices for missing; data-table toggle |
| `Timeline` | chrome | events list, glyph nodes, wall-clock + relative time |
| `TracePanel` | cross-layer | side sheet: Score → Aspect → Risk (O/S/D) → Evidence → raw JSON |
| `Spine` | chrome | pipeline stages, locked timestamps |

Every chart primitive ships: `<title>`/`<desc>`, an `aria-describedby` text summary, and a
"Show as table" toggle rendering the same data in a `<table>`.

---

## 8. The Live Evaluation Theatre

### 8.1 Data architecture — one contract, three sources

```
                 ┌──────────────────────┐
 PollingSource ──┤                      │
 ReplaySource  ──┤  TheatreSource        │── Snapshot ──► deriveTheatre() ──► TheatreModel ──► components
 (future) SSE  ──┤  subscribe(onSnap)    │   (pure)        (pure, memoised)     (per-lane React.memo)
                 └──────────────────────┘
```

```ts
/** Everything the Theatre may know. Identical shape for live, replay and future SSE. */
interface TheatreSnapshot {
  origin: "live" | "simulation";
  evaluation: EvaluationRead;            // authoritative (status, probes, osd_agent, final_score, …)
  events: EvaluationEventRead[];         // ordered by id; audit trail, never used to derive scores
  observedAt: string;                    // wall clock of this snapshot (replay: virtual clock)
}

interface TheatreSource {
  subscribe(onSnapshot: (s: TheatreSnapshot) => void, onError: (e: Error) => void): () => void;
}
```

- **`PollingSource`** — reuses today's loop (`GET /v1/evaluations/{id}` + `/events`, 500 ms while
  `ACTIVE_STATUSES`, stop on terminal). Exponential back-off to 5 s on network error, surfaced as a
  designed "connection lost — showing last known state from HH:MM:SS" banner.
- **`ReplaySource`** — plays a fixture's frames on a virtual clock: 0.5×/1×/2×/4×/8×, pause, scrub,
  step-by-frame. Emits the *same* `TheatreSnapshot`s with `origin: "simulation"`.
- **`deriveTheatre(snapshot) → TheatreModel`** — pure function; the only place that interprets
  data. Lane state, spine stage, per-risk values. Unit-tested against all fixtures.
- **Future-proofing:** `deriveTheatre` already has a code path keyed on the *optional* future event
  types (`probe_started`, `probe_progress`, `probe_completed`, see proposal doc). With today's
  backend those events never appear, so the path is dormant; unknown event types render generically
  in the timeline (matches the existing `EvaluationEventRead.event_type: string` contract). Adding
  SSE = a new `SseSource` class; no component changes.
- **Re-render budget:** each lane is `React.memo` keyed on its probe row's evidence hash; the
  pentagon on `final_score` identity; the timeline appends only. A poll that changes nothing
  re-renders nothing (structural equality check on snapshot parts).

### 8.2 Truth table — spine stages (derived only from real state)

| Stage | Done when | Timestamp from |
|---|---|---|
| Draft | evaluation exists | `evaluation_created` |
| Dataset validated | evaluation exists (v2 contract requires confirmed draft) | `evaluation_created` (shared, labelled) |
| Probes | status ≥ `PROBES_COMPLETED` | `probes_completed` |
| O/S/D proposal | `osd_agent` present | `agent_completed` |
| Human review | `human_review` present **or** mode `AI_AUTONOMOUS` → "Not required" | `human_review_submitted` |
| Final score | `final_score` present | `evaluation_finalized` |
| Report | report exists | `report_generated` |

Current stage = first not-done stage while status active. `FAILED` → spine freezes at the stage
that failed, marked ✕ with `evaluation_failed.detail.reason_code`.

### 8.3 Lane states

`awaiting ○` (status active, no row) · `landed` with semantic `ProbeStatusValue` (EVALUATED /
INSUFFICIENT_EVIDENCE / NOT_APPLICABLE / SKIPPED / FAILED / PROXY) · `not produced ✕`
(evaluation failed, no row). Each landed lane shows: status chip, landing offset, `n_evaluated`,
confidence meter, current metric values (evidence material), evidence ledger (id, type, short hash,
copy), and the lane-specific instrument:

- **Fairness** — per-group bars from `groups` (n + rate), small-group warning glyph for groups with
  n < `min_group_n` or listed in `excluded_groups`; DPD / EOD / F1-spread gauges with CI whiskers.
- **Robustness** — clean vs robust accuracy paired bars, drop meter, attack success rate, coverage,
  attack name / ε / max_changes as specimen text.
- **Integrity** — static seal (verified / mismatch / not checked) from `checks`/`identity`;
  reproducibility fingerprint: model revision, dataset content hash, TrustLens version,
  methodology version (each a HashBadge, "—  not recorded" when null, as `trustlens_version` is in
  the real fixtures).
- **Explainability** — model-card section checklist (`sections_present` vs `sections_required`,
  bonus sections), documentation source + retrieval status, contradictions list; "Feature
  attribution — not measured" slot.
- **Safety** — safety-check coverage checklist (`checks_present` vs `checks_required`),
  high-impact claims; "Behavioural safety probing — not measured" slot.

### 8.4 Evidence → Risk → O/S/D

When `osd_agent` appears, risk cards materialise under the lanes, one per aspect (MVP: one risk per
aspect, matching `score_from_finalized_osd`). Trace threads connect each card to the evidence it
cites (`evidence_used` / `scored_risk_id` / `risks_triggered`). Card = three `Dial`s (O, S, D, with
`*_source` shown), AI rationale, confidence, and:

```
T = ∛(O × S × D) = ∛(6 × 6 × 8) = 6.60        ⓘ higher = safer (inverted FMEA)
```

- Before finalisation, T is a **display computation from proposed values**, labelled "proposed".
- After finalisation, T and aspect scores show the **backend's** `final_scores` values; the client
  computation is only used for the Learn page and what-if preview. A dev assertion warns if they
  ever disagree (> 1e-4).

### 8.5 FRIES lens (pentagon + score)

Pentagon fills vertex by vertex as `final_score.dimension_scores` exist (with proposed-value ghost
outline during review). Hollow dashed vertex = dimension absent. Centre: Fraunces numeral, ramp
colour, confidence meter, mode badge (`AI_AUTONOMOUS · not human-reviewed` or seal), and the fixed
caption: *"Traceable aggregation of risk assessments — not an absolute safety measure."*
`fries_score = null` (withheld) → designed "Score withheld" state with `score.note`.
Weights shown under the pentagon; weight-profile what-if in hatched PREVIEW frame.

### 8.6 Timeline drawer, TracePanel, hardware strip

- **Timeline** (bottom drawer, `role="log"`, `aria-live="polite"`): real events, wall-clock + `+Δs`,
  filter by type, each row links to what it concerns (probe lane, risk card, report).
- **TracePanel**: every number is a `<button>`; opens side sheet with the chain Score → Aspect →
  Risk O/S/D (+ sources, AI vs human) → evidence refs (uri, hash, created_at) → metric definition →
  "Raw JSON" disclosure (progressive disclosure: summary, 1 click evidence, 2 clicks JSON).
- **Hardware strip**: from `execution_metadata` (device, gpu_name, backend, dtype, batch_size,
  fallback_reason). `null` → *"No local inference recorded for this evaluation."*

### 8.7 Three layout sketches

**Sketch A — "Bench" (recommended).** Spine top, lanes centre as a 5-row bench, lens right. Reads
left→right exactly like the causal chain.

```
┌─ SIMULATION ─ Spine: Draft ━ Dataset ━ Probes ◉ ─ O/S/D ─ Review ─ Final ─ Report ─── hw strip ┐
├──────────────────────────────────────────────────────────┬───────────────────────────────────┤
│ F ● Fairness      landed +38.2s  ▮▮▯▮ groups  DPD 0.31 ⟷ │                                   │
│ R ■ Robustness    landed +76.7s  clean 0.91 / rob 0.88   │          ⬠  FRIES lens            │
│ I ⬢ Integrity     awaiting ○                             │            4.08                   │
│ E ◆ Explainability awaiting ○                            │     conf ▮▮▮▮▯ 0.95               │
│ S ▲ Safety        awaiting ○                             │  weights .2 .2 .2 .2 .2  [what-if]│
├────────────── risk cards (O S D dials · T) ───────────────┤                                   │
├──────────────────────────────── ▲ timeline drawer (10 events) ────────────────────────────────┤
```

**Sketch B — "Column of custody."** Vertical spine left rail; lanes as a 5-column grid; risk row;
lens pinned bottom-right. Good on ultrawide, cramped on 1280.

```
│Draft ✓│ [F][R][I][E][S]  ← lane columns
│Data  ✓│ ───── risk row ─────
│Probes◉│                  ⬠ 4.08
│O/S/D  │ ───── timeline ─────
```

**Sketch C — "Lens first."** Pentagon hero centre-top, lanes orbit radially at each axis. Most
dramatic, but radial lanes cannot hold ledgers/tables legibly and tablet collapse is poor.

**Recommendation: A.** The spatial order *is* the methodology order (evidence → risk → score),
which teaches the chain; collapses to tablet by stacking lens above lanes.

### 8.8 Simulation mode

- Route `/simulate/:fixture` and a toggle on any Theatre. Persistent diagonal-hatched
  **SIMULATION** banner + UV-less grey chrome tint + page title prefix `[SIMULATION]`; banner is
  not dismissible. Reports and publish actions are disabled in simulation.
- Fixtures in `frontend/src/theatre/fixtures/`, built by a small script from real snapshots:
  1. **healthy** ← `trustworthy_unitary_toxic-bert.json`
  2. **fairness-flaw** ← `variant1_fairness.json`
  3. **compound-flaw** ← `variant6_compound.json`
- Frame reconstruction: `created → started → each probe lands at its evidence created_at → probes_completed → agent_completed → finalized`. Because source runs have no stored events, each fixture is marked
  `"provenance": "reconstructed-from-snapshot"` and the replay UI says so. Fixture format:
  `{ fixture_version, provenance, source_file, frames: [{ t_ms, snapshot }] }`.

---

## 9. Other screens

Every screen specifies **empty / loading / error / partial / stale** states; failure states are
designed screens with cause + next action, never toasts.

1. **Home / Registry** (`/`, `/models`) — model rows with mini pentagon of latest *finalised* eval
   (hollow when none), comparability line: `task · dataset · config · model_revision ·
   methodology_version` (mono). Empty: "Import your first model" with 3-step methodology teaser.
2. **Import model** (`/models/import`) — repo id / URL + optional revision. Shows result: pinned
   revision (HashBadge), checksum, metadata. "Runs on this machine?" panel honestly reads *"Not
   checked before import — device is recorded at evaluation time"* (gap G2).
3. **Draft wizard** (`/evaluations/new`) — left checklist per dimension with progress chips
   (`incomplete ◌ / validated ◐ / consumed ● / stale ⚠`); steps: intake (file/URL, sniffed columns,
   types, row count, content hash) → column roles (text, target, sensitive, label mapping from
   `model_label_snapshot` only, positive label, min_group_n with live group preview flagging
   under-n groups) → validation feedback (errors listed verbatim) → confirm. Stale screen: *"Model
   revision changed since this draft was validated. Drafts are frozen to a revision; create a new
   draft."* Preserves the existing gate: *Continue to review* disabled until a dimension is
   configured and confirmed.
4. **Theatre** (`/evaluations/:id`) — §8.
5. **Human review console** (`/evaluations/:id/review`) — per aspect: AI column (O/S/D dials,
   rationale, cited evidence chips, confidence) ↔ Human column (editable dials). Changed values
   get a diff marker (`4 → 6`, UV underline + "changed" word). Notes **required** when any value
   changes. Submit → review seal: "Human reviewed · 2026-09-29 14:03:11". Until a
   `human_review` row exists, the score area reads "Not final — awaiting human review".
6. **Results & Report** (`/reports/:id`) — aspect breakdown, risk table (O, S, D, T, sources, AI vs
   human), evidence appendix (all refs, hashes), methodology stamp, report `version` + hashes,
   JSON/PDF download. Keeps the existing "never recompute" rule from `ReportPage.tsx`.
7. **Compare & Leaderboard** (`/compare`, new route) — pick evaluations; comparability key =
   `(task, dataset, config, per-dimension probes[].methodology_version,
   evaluation_contract.dataset_content_id)`. Methodology version is per probe and can be null
   (real compound run: Fairness `null`, others `tl-*-v1.0`) — null never matches anything.
   Mismatch → loud full-width banner listing each differing field; overlaid pentagons disabled
   until the user explicitly acknowledges. Leaderboard view lists `is_published` only.
8. **Methodology / Learn** (`/learn`, replaces `/documentation` content, route kept as alias) —
   interactive O/S/D sliders → live T with veto demo; geometric vs arithmetic mean comparison;
   weights sliders enforcing ω ≥ 0.1, Σ = 1; worked examples are the frozen test vectors.

---

## 10. Accessibility, performance, testing

- **A11y:** WCAG 2.2 AA. Visible 2 px UV focus ring (offset 2 px) on everything; full keyboard
  path through Theatre (lanes are a roving-tabindex list; `T` opens timeline, `Esc` closes trace);
  `aria-live="polite"` announcer summarises state changes ("Fairness evidence landed, status
  evaluated"), throttled to 1 message / 2 s during bursts; every chart has text summary + table
  toggle.
- **Performance:** 60 fps target — compositor-only animations; lists up to 200 rows use CSS
  `content-visibility: auto` (no virtualisation library; add one only if profiling shows need —
  ledgers are ≤ ~10 refs, timelines ≤ ~15 events).
- **Tests:**
  - vitest + Testing Library for each primitive (render, a11y roles, reduced-motion static state,
    table toggle).
  - `deriveTheatre` unit tests over every fixture frame.
  - Scoring-display unit test: client `risk_pi`/`aspect`/`weights` preview reproduces **every**
    case in `shared/scoring/fixtures/fries_test_vectors.json`.
  - Automated contrast test over token pairs (both themes).
  - **Playwright** (new devDependency `@playwright/test`): plays `compound-flaw` fixture at 8× to
    the end, asserts pentagon vertices + FRIES total equal the fixture's `final_score` (4dp:
    F 6.6039 · R 9.0 · I 2.2894 · E 1.2599 · S 1.2599 · total 4.0826), and that each risk card's
    displayed T equals ∛(O·S·D) of its displayed dials (e.g. Fairness (6,6,8) → 6.6039). It also
    loads `fries_test_vectors.json` and checks the Learn page reproduces vectors #2, #3 and #6
    (fixture runs contain no veto or multi-risk case, so those are covered via Learn).

## 11. Dependencies added

| Package | Kind | Why |
|---|---|---|
| `@fontsource-variable/fraunces`, `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono` | runtime (static assets) | self-hosted fonts, local-first |
| `@playwright/test` | dev | required Theatre E2E test |

No chart, animation, state or virtualisation libraries.

## 12. Backend gaps (proposed, not implemented)

| ID | Gap | Proposal |
|---|---|---|
| G1 | No live per-probe progress | See [progress-events proposal](2026-09-29-theatre-progress-events-proposal.md) |
| G2 | No pre-import "can it run here" check | `GET /v1/models/preflight?repo_id=&revision=` → size, param count, dtype, memory estimate, local device |
| G3 | Stale reason only in a 409 message | add `status_reason` to `EvaluationDraftRead` |
| G4 | No report version history | `GET /v1/reports/{id}/versions` (append-only list: version, hashes, generated_at) |
| G5 | No draft list | `GET /v1/evaluation-drafts?model_id=` for registry "in-progress drafts" |
| G6 | `trustlens_version` null in real runs | populate at evaluation creation (reproducibility fingerprint) |

## 13. Delivery plan (after approval)

1. ✅ This brief.
2. Tokens + primitives + `/gallery` → **pause for approval.**
3. Static hi-fi screens (all 8) wired to real reads where the endpoint exists.
4. Theatre: `TheatreSource`, `deriveTheatre`, `PollingSource`, `ReplaySource`, 3 fixtures, Playwright.
5. A11y audit + polish.

Existing pages are rewritten in place on the same routes; `api/`, `lib/contract.ts`, `lib/report.ts`,
`lib/format.ts` are reused; existing behaviour tests are ported, not deleted.
