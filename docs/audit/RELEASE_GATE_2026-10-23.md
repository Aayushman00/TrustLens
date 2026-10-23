# TrustLens release gate, 2026-10-23

Companion to `TRUSTLENS_AUDIT_2026-10-23.md`. Commit hash of the gated state: see the last section.

## 1. Fresh runs (this gate, after the final source edits)

| Check | Command (cwd) | Exit | Result |
|---|---|---|---|
| Backend tests | `python -m pytest -q -p no:cacheprovider` (`backend/`) | 0 | 910 passed, 2 skipped, 1 warning, 156 s; 912 collected |
| Backend lint | `python -m ruff check .` (`backend/`) | 0 | all checks passed |
| Worker tests | `python -m pytest -q -p no:cacheprovider` (`worker/`) | 0 | 9 passed |
| Worker lint | `python -m ruff check .` (`worker/`) | 0 | all checks passed |
| Frontend types | `npx tsc -b` (`frontend/`) | 0 | no output |
| Frontend tests | `npx vitest run` (`frontend/`) | 0 | 29 files, 275 tests passed |
| Report build | `bash scripts/audit/build_report.sh` | 0 | 65 pages, 0 undefined references, 0 LaTeX errors |
| L2 recomputation | `python scripts/audit/l2_stratified.py`; `l10_recompute.py` | 0 | match stored analyses |

The backend count (912 collected / 910 passed / 2 skipped) belongs to the backend suite only; the worker (9) and
frontend (275 tests in 29 files) are separate suites and are reported separately in Ch9.

## 2. PDF findings

65 of 65 allowed pages. Two overfull boxes of about 2 pt (Table 4.3 "UNSUPPORTED" cell, Table 7.13): text is not
clipped. Rendered and inspected: abstract, equations (p. 21), version table (p. 22), artifact-status table,
L2 stratified table, hub tables, limitations. `report/main.pdf` is git-ignored in this repository; it is rebuilt from
the committed source by `scripts/audit/build_report.sh`, so it cannot be committed without overriding `.gitignore`.
The PDF was built after the last source edit (ch9 timing sentence) and its page count was read from the file.

## 3. Material claims

| Claim | Status | Evidence |
|---|---|---|
| FRIES formula, 0..10 integer validation, veto, 0.2 weights, weight floor | verified | `fries.py` vs Ch4; fixtures 1-10 and 12 new tests |
| Five-dimension guard; empty `risks` rejected; formula unchanged | verified | `test_fries_scorer.py`; guard only adds a ValueError |
| v11 empty-card abstention; version table and Ch4 prose agree | verified | `agent.py`, `methodology_version.py`, `test_report_claims.py` |
| L2 pooled 11/36 (0.3056), provider-only 5/18 (0.278), Claude-only 7/24 | verified | `l2_stratified.py` using original `compare()` |
| "Triple never repeats": 0/36 pooled, 0/12 providers, 3/24 supplementary alone | verified | same |
| L2 baseline differs by 7 cells between folders | verified | direct cell diff of the two `deterministic.json` |
| Human study: 7 submissions, 6 share code R0, agreement statistics | verified | `l10_recompute.py` (independent code) matches `agreement.json`; CSV sha256 prefix `da680bbc` |
| Reviewer independence | unresolved by design | report says independence is unestablished; no claim made |
| Fairness rule constants (eps 0.02, width 0.15, B 1000, min group 30, one positive), discard of undefined bootstrap replicates | verified | `fairness_stats.py` |
| Fairness H1 failure, clean-control width 0.1529 | verified | `analysis.json` |
| Fairness rule chosen post hoc, not confirmed on fresh data | verified (as disclosed) | Ch4, Ch7, Ch10 |
| Safety v10 rule (0.50 / 0.30, min 30 severe), v9 floor 0.30 post hoc | verified | `safety_stats.py`, `safety_behavior.py`, `methodology_version.py` |
| Wilson interval implementation | verified | formula read against the standard form |
| Robustness gates (100 samples, clean floor 0.20, coverage 1.0, CI width 0.20, drop eps 0.05) | verified; Ch4 previously omitted the CI-width gate, now added | `robustness_stats.py`, `robustness_eval.py` |
| v3 range 1.3-1.7; held-out 0.68-1.18 to 4.60-6.65 | verified | `FINDINGS.md` and hand recomputation of Pi |
| v4 range is partly by construction; not calibration to harm | verified (wording) | Ch7 "What score calibration does not show", Ch4 |
| Civil Comments dataset pin | partially verified | pinned in code since commit `72ccbd9` (2026-10-03); eval-set manifest records no revision |
| Hub table (7 models) metrics and revisions | verified | all values match `evaluations/*.json` |
| Hub dataset revision / eval-set hash recorded in v9r artifacts | unsupported | evaluation records carry `dataset: null`; not invented |
| Test counts by suite | verified | section 1 |
| Citation keys: 24 cited, 24 defined, none orphaned | verified (structure) | script over `\cite`/`\bibitem` |
| Bibliographic accuracy of the 24 references; Ch2 literature characterisations | not checked | no external lookup performed |
| Robustness perturbation generator beyond `char_swap_attack` signature and gates | partially verified | read, not unit-audited |
| Per-model Hub label mappings, head selection | not checked | |
| Calibration generalisation, FRIES construct validity | not claimed | report states none |

## 4. Remaining limitations, by severity

1. High: dataset revision of the 2026-10-02 evaluation set and the Hub audit is unrecorded in the stored artifacts.
2. High (scientific): post-hoc rules (v6 fairness, v9 safety floor) lack fresh-data confirmation; v10 is exploratory.
3. Medium: human review has seven submissions, six under one shared code; independence unresolved.
4. Medium: LLM comparison pools heterogeneous evaluators; no single-provider rerun.
5. Low: reference bibliography content and per-model label mappings not independently verified.
6. Low: two 2 pt overfull boxes; `main.tex` declares an unused package that some TeX installs may lack.

## 5. Verdict

**READY WITH DOCUMENTED LIMITATIONS.** Software correctness and report/artifact consistency are verified by fresh runs.
That does not establish scientific validity: the FRIES score is an unvalidated heuristic summary, the thresholds were
partly chosen after seeing data and are not shown to generalise, and the human and LLM comparisons are descriptive.

## 6. Gated commit

Gated commit: `9e8e5ee` (all section 1 results were produced on exactly this tree; the only later commit adds this hash).
