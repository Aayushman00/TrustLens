# v2 bug ledger

Status: `open`, `fixed`, `not-a-bug`, `documented`. Severity S1 (decision-affecting) to S4 (cosmetic).
K-items are defined in `01-v1-baseline-and-known-issues.md`. Tasks that fix a row flip it to `fixed` with the test name in the same commit.

| ID | Severity | Status | Test name | Notes |
|----|----------|--------|-----------|-------|
| K1 | S2 | open | | Two evaluation services (`evaluation_service`, `_v2`) can drift; behaviour depends on which a router calls |
| K2 | S2 | open | | Confidence is not monotone in sample size at boundaries (data_quality steps at n=16/100/200) and ignores CI width except via gates |
| K3 | S2 | open | | `D` hard-coded to 8 for "directly measurable" dimensions inflates Π and makes dimension scores insensitive to detectability |
| K4 | S2 | fixed | `test_llm_v1_engine_falls_back_to_deterministic` | LLM-assisted O/S/D was non-deterministic across providers and unvalidated. Removed (M0); `llm_v1` now resolves to `deterministic`. Last `llm_client.py` diff archived in `archive/v1/legacy/` |
| K5 | S1 | open | | Veto rule maps any 0 to Π=0 but heuristics never propose 0, so a vetoed risk can only come from a human. Decision: ADR 0014, Tier A integrity findings force `REJECT` |
| K6 | S2 | open | | Explainability and the Safety card part can be gamed by pasting headings into a model card (rule-based matcher, `MIN_BODY_CHARS`) |
| K7 | S2 | open | | Fairness only defined when user supplies a sensitive column; label mapping errors silently change the positive class |
| K8 | S3 | open | | Single-seed runs: sensitivity to the sample draw is not reported per probe |
| K9 | S4 | open | | Docs and README drifted from code (docs layout fixed in v2 cleanup; CI claim-to-code check pending, spec 06) |
| K10 | S4 | open | | Repo hygiene: large untracked artefacts at the root (moved to `archive/v1/legacy/`) |
| K11 | S1 | open | | EOD/F1 spread is max − min over groups, biased upward: truth 0, estimate 0.23, 0 % coverage at k = 4 (S3-C); `probes/fairness_metrics.py:132` |
| K12 | S2 | open | | `bootstrap_gap_ci` drops replicates where `stat_fn` returns None, so the CI is conditional on every group surviving resampling; `probes/fairness_stats.py:209-213` |
| K13 | S1 | open | | Percentile bootstrap used for small-n rates: 0.39 coverage at n = 10, p = 0.05 (S3-A) |
| K14 | S1 | open | | No pickle-content scan anywhere (only hash checks) |

## Baseline suite runs (branch `v2/m0-m1`, clean checkout)

Backend: `pytest -q -m "not integration"`; worker: `pytest -q`.

| Run | Backend | Backend time | Worker | Worker time |
|-----|---------|--------------|--------|-------------|
| 1 | 685 passed, 0 failed, 227 skipped | 72.02 s | 9 passed, 0 failed, 0 skipped | 0.63 s |
| 2 | 685 passed, 0 failed, 227 skipped | 70.48 s | 9 passed, 0 failed, 0 skipped | 0.47 s |
| 3 | 685 passed, 0 failed, 227 skipped | 69.62 s | 9 passed, 0 failed, 0 skipped | 0.44 s |

No failing or flaky tests across the three runs, so no `B` rows.
