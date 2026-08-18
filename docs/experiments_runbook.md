# TrustLens Phase 25 — Benchmark Experiments Runbook

Protocol source: `implementation/docs/experiments.md` + `research_questions.md`
(RQ1–RQ6). This runbook pins everything needed to reproduce the Mode A/B/C
benchmark: versions, probe config, dataset revisions, seeds, model set, and
the exact commands. Machine-readable twin:
[`configs/experiments_v1.yaml`](../configs/experiments_v1.yaml) — the runner
reads that file; this document explains it. Change both together.

## What the three modes are

| Mode | What runs | Human role | Product path |
|------|-----------|------------|--------------|
| A — manual FRIES | Paper rubric only (no TrustLens pipeline) | Human scores O/S/D per aspect from the model card/docs | none (research baseline) |
| B — AI-Assisted | Probes → agent O/S/D → `AWAITING_REVIEW` | Reviewer accepts/edits O/S/D, then finalizes | `AI_ASSISTED` |
| C — AI-Autonomous | Probes → agent O/S/D → auto-finalized FRIES | none | `AI_AUTONOMOUS` |

## Pinned environment

| Item | Value |
|------|-------|
| TrustLens API / worker | **0.20.1** (stamped into `evaluations.trustlens_version`) |
| Probe config schema | `v1` (`backend/app/schemas/probe_config.py`) |
| Dataset pins | `configs/datasets_v1.yaml` — `adult_fairness` (scikit-learn/adult-census-income) @ `fbeef6ec…`, `sentiment_fairness` (stanfordnlp/sst2) @ `8d51e7e4…`, `ag_news_robustness` (fancyzhx/ag_news) @ `eb185aad…` (full SHAs in the YAML; re-pinned to namespaced repos in Phase 25 — canonical ids no longer load) |
| Fairness probe | Adult census, `sensitive_attribute=sex`, 256 rows, `min_group_n=30`, proxy `LogisticRegression(max_iter=500, random_state=seed)` |
| Robustness probe | char-swap attack, `attack_budget=0.03`, 64 rows, CPU inference |
| O/S/D agent | `HeuristicOSDAgent` — deterministic metric→band rules, always `PROPOSED_REQUIRES_VALIDATION` |
| Scoring | Original FRIES (`Pi = cbrt(O*S*D)`, equal weights); see `backend/tests/SCORING.md` |

### Pinned `probe_config` (per evaluation)

```json
{
  "schema_version": "v1",
  "datasets": {"fairness": "adult_fairness", "robustness": "<per-model, see table>"},
  "attack_budget": 0.03,
  "slice_definitions": {"sensitive_attribute": "sex"},
  "extra": {"seed": <per-run seed>}
}
```

`extra.max_samples` is deliberately unset so each probe keeps its own pinned
default (fairness 256 / robustness 64).

## Seed list and repeat design

- **Seeds: `42, 1337, 2025`** — one Mode C run per seed per model (3 repeats).
  The seed drives dataset subsampling, the fairness LR `random_state`, and the
  robustness attack RNG via `probe_config.extra.seed`.
- The whole pipeline is otherwise deterministic (heuristic agent, pinned
  dataset revisions, argmax CPU inference), so **std across seeds measures
  seed/sampling sensitivity** — that is the repeatability statistic (RQ6).
- **Determinism check**: one extra run of `philschmid/tiny-bert-sst2-distilled`
  at seed 42 (`repeat=det-check`). Expected: identical O/S/D, FRIES, and
  metrics to the first seed-42 run; any diff indicates nondeterminism in the
  stack and is reported next to the std table.

## Model set (6)

Small HF text classifiers that finish on CPU, plus two deliberate
skip-contrast models. Fairness note: the Adult fairness probe **never runs the
HF model** (proxy LR on tabular data) — it produces identical fairness
evidence for every model at a fixed seed; only the seed varies it. This is a
documented MVP limitation, not a bug.

| # | Model | Task | Robustness dataset | Expected probe behavior |
|---|-------|------|--------------------|-------------------------|
| 1 | `distilbert-base-uncased-finetuned-sst-2-english` | sentiment (binary) | `sentiment_fairness` (SST-2) | all 5 probes produce metrics |
| 2 | `philschmid/tiny-bert-sst2-distilled` | sentiment (binary) | `sentiment_fairness` | all 5; fastest (tiny) |
| 3 | `textattack/roberta-base-SST-2` | sentiment (binary) | `sentiment_fairness` | all 5; RoBERTa architecture contrast |
| 4 | `textattack/bert-base-uncased-ag-news` | news (4-class) | `ag_news_robustness` | all 5; 4-class labels match head |
| 5 | `prajjwal1/bert-tiny` | fill-mask LM | — (default) | robustness **soft-skips** (`unsupported_modality`: not text-classification); card probes run |
| 6 | `google/vit-base-patch16-224` | image classification | — (default) | robustness **soft-skips**; card probes run |

Pairing rule: the robustness dataset must have labels compatible with the
model head (binary SST-2 heads are scored on SST-2, the 4-class head on
AG News). Mismatched labels are skipped sample-by-sample by the runner and
would make accuracy meaningless.

If a model fails import or the pilot (e.g. gated, renamed), swap it for a
same-task alternative (`textattack/bert-base-uncased-SST-2`,
`lvwerra/distilbert-imdb` + `sentiment_fairness`) and update
`configs/experiments_v1.yaml` + this table.

## How to run

Prereqs: Docker Compose stack up, migrated, seeded; backend deps available
natively (the scripts run on the host and talk to `127.0.0.1`).

```powershell
docker compose up --build -d
docker compose exec api alembic upgrade head
make seed-users        # researcher/reviewer dev logins (re-run after test suites)

# Mode C batch (3 seeds x 6 models + determinism check), resumable:
cd backend
python -m app.scripts.run_experiments --mode c

# Mode B batch (3 assisted evaluations), then the reviewer pass + finalize:
python -m app.scripts.run_experiments --mode b

# Export CSVs (reads Postgres directly; DATABASE_URL defaults to the Compose DB):
python -m app.scripts.export_experiment_results
```

- The runner logs in via `POST /v1/auth/login` as the seeded researcher
  (override with `TRUSTLENS_RESEARCHER_EMAIL` / `TRUSTLENS_RESEARCHER_PASSWORD`;
  reviewer equivalents for the Mode B review step).
- Every created run is appended to `results/manifest_v1.jsonl`
  (evaluation_id, model, mode, repeat, seed, wall seconds, terminal status).
  Re-running skips (model, mode, repeat) tuples already present — delete a
  line (or the file) to redo a run.
- **Wall time** is measured client-side from just before
  `POST /v1/evaluations` until the poller observes the terminal status
  (5 s poll interval; includes queue wait). The DB has no duration columns;
  the export also derives `db_duration_s` = `final_scores.created_at −
  evaluations.created_at` for finalized runs. First run per model includes the
  HF model download — treat it as an outlier for timing (repeat 2/3 are warm).

## Mode C protocol (AI-Autonomous)

One evaluation per (model, seed): create with the pinned `probe_config`,
`evaluation_mode=AI_AUTONOMOUS`, wait for `FINALIZED` (or `FAILED` — recorded,
not retried silently). Outputs per run: FRIES score, per-aspect O/S/D +
`Ti`, per-aspect and overall confidence, wall time, probe skip flags.

## Mode B protocol (AI-Assisted)

Subset: models 1, 4, 5 at seed 42 — create as `AI_ASSISTED`, wait for
`AWAITING_REVIEW`, then a reviewer pass:

- Model 1: `accept_all` (agent evidence judged sufficient).
- Models 4 and 5: per-aspect edits with written rationale (which aspects and
  why is decided from the actual evidence at review time and recorded in
  `review_rationale`).

Then `POST /{id}/finalize` → FRIES from the human-approved O/S/D with
`human_reviewed=true`. Recorded: `accept_all`, `human_changed`, agent vs
approved O/S/D deltas, final FRIES.

**Provenance label**: reviewer passes executed by an AI assistant are recorded
with `review_rationale` prefixed `[ai-provisional]`. They are placeholders for
real human reviews — redo via the Phase 23 UI (reviewer login) or the API and
re-export to replace them; the protocol and CSVs stay identical.

## Mode A protocol (manual FRIES — research baseline, not a product mode)

Subset: same models as Mode B (1, 4, 5), scored with the original FRIES paper
rubric (see `implementation/phase0/fries_formula.md`): per aspect, assign
O/S/D in 0–10 (higher = safer; 0 = veto) from the model card and public docs
only — no TrustLens output in view (blind to Mode B/C results).

Worksheet: `results/mode_a_manual.csv` — one row per (reviewer, model,
aspect): `reviewer,model,aspect,O,S,D,Pi,rationale,minutes_spent` where
`Pi = cbrt(O*S*D)` (one selected risk per aspect), plus one summary row per
(reviewer, model) with `aspect=FRIES` carrying `T = mean(Pi)` over the five
aspects (equal weights) — the same formula the product uses. Rows from the AI
assistant use `reviewer=ai-provisional` and were scored before inspecting any
TrustLens output for these models; human reviewers append their own rows
(target ≥2 reviewers for agreement stats in Phase 26).

## Outputs (`results/`, committed)

| File | Contents |
|------|----------|
| `manifest_v1.jsonl` | Runner ledger: one JSON line per created evaluation |
| `mode_c_runs.csv` | One row per Mode C run: model, revision, evaluation_id, repeat, seed, fries, per-aspect O/S/D + Ti + confidence, overall confidence, wall_s, db_duration_s, skip flags |
| `mode_c_summary.csv` | Per model: n runs, mean/std FRIES, per-aspect O/S/D std, determinism-check verdict |
| `mode_b_reviews.csv` | One row per assisted run: agent vs approved O/S/D per aspect, accept_all, human_changed, final FRIES, rationale |
| `mode_a_manual.csv` | Manual rubric worksheet (see Mode A protocol) |

Repeatability (roadmap DoD): `mode_c_summary.csv` carries std dev across the 3
seeded runs per model; Phase 26 computes the comparison tables from these CSVs.

## Honest limitations (carry into the write-up)

- Fairness evidence is model-independent (proxy LR on Adult) — identical
  across models at fixed seed; fairness O/S/D variation across models is zero
  by construction in this MVP. Visible in `mode_c_runs.csv`: every model has
  the same fairness triple per seed.
- Agent O/S/D comes from documented heuristics
  (`PROPOSED_REQUIRES_VALIDATION`) — the experiment measures the pipeline, not
  a validated metric→O/S/D science. Concrete instance found during the Mode B
  pass: the card-coverage heuristic maps missing section **headers** to a
  uniform low O/S/D triple, conflating absent documentation with extreme
  severity (both thin-card models scored coverage 0.00 despite cards that do
  document task/training/provenance) — the reviewer overrides in
  `mode_b_reviews.csv` correct exactly this.
- Mode A/B human passes labeled `ai-provisional` were produced by an AI
  assistant and must be replaced by real human passes for the final thesis
  numbers. The Mode A pass was done card-only, before inspecting TrustLens
  output for those models.
- Wall time includes container queue wait and (first run per model) HF
  download; per-probe timing is not recorded (no DB duration columns). Treat
  each model's first run as a warm-up outlier.
- Small N (6 models, 3 seeds) — std is indicative, not inferential.

## Execution record (v1, 2026-08-13)

- Stack: Compose images built from 0.20.1 sources; worker rebuilt after the
  Phase 25 dataset re-pin (the pilot caught `glue`/`ag_news` canonical ids no
  longer loading — see `configs/datasets_v1.yaml` header note).
- Mode C: 19/19 runs `FINALIZED`, no failures or retries; determinism check
  identical to its seed-42 twin. Per-model FRIES std 0.08–0.22 across seeds.
- Mode B: 3/3 reviewed + finalized via `results/mode_b_review_plan.json`
  (accept-all on distilbert reproduced the autonomous FRIES exactly; the two
  edited reviews set `human_changed=true`).
- Mode A: one `ai-provisional` reviewer row set per subset model in
  `results/mode_a_manual.csv`.

## Out of scope (Phase 25)

Attack scenarios (Phases 20–21), FRIES2, probe algorithm changes, UI changes,
schema changes. Phase 26 does the statistics/write-up from these CSVs.

## Phase 26 outputs

Analysis (regenerates `results/analysis/` tables T1–T7 + figures F1–F5 from
the CSVs above; does **not** re-run evaluations):

```powershell
cd backend
python -m app.scripts.analyze_experiments
```

T1 means/stds are asserted against `mode_c_summary.csv`. Write-up:

- [`docs/results_chapter.md`](results_chapter.md) — RQ1–RQ6 results chapter
- [`docs/RESULTS_SUMMARY.md`](RESULTS_SUMMARY.md) — supervisor one-pager
- [`results/analysis/TABLES.md`](../results/analysis/TABLES.md) — concatenated tables

