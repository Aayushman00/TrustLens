# TrustLens final audit (2026-10-28) — summary, logs, tables

Build: `scripts/audit/build_report.sh` (Docker texlive, 4 passes) -> **67 pages, 0 LaTeX errors, 0 undefined refs, 17 minor Overfull hbox (<=7 pt)**. `multirow` is dropped in the scratch copy only (not in the image). Cover and certificate date fields confirmed blank. Admin details unchanged. Nothing committed.

## Edits made (4)
| # | Where | Change | Why |
|---|---|---|---|
| 1 | Ch8 Limitations (LLM comparison) | "up to three weeks later" -> "on 28 October, nearly four weeks later" | 2 Oct -> 28 Oct = 26 days |
| 2 | Ch8 Internal validity | "three hypotheses" -> "H1-H3 and a descriptive H4" | Ch6/Ch7 define four |
| 3 | Ch4 Later evidence guards | D width: for Robustness it is the clean-accuracy CI, not the drop CI | `osd/agent.py::_robustness_band` |
| 4 | App. B.1 | 5 of 60 runs (all P01) had the prompt truncated by the card/details cuts | `analysis.json: llm_prompt_truncated=5`; was unreported |

## Verification table
| Claim | Evidence | Status |
|---|---|---|
| 60/60 valid, 22 first + 38 later; providers B41/A15/C4 | `l2_completion_audit.py` rerun; 0 unresolved, 0 schema violations, 1 prompt hash per packet | Supported |
| Status 11/36; definite 11/25; S exact 6/36; triple 4/36; MAE 2.08 (v9) / 2.14 (v3) | audit rerun + `completion_audit_baseline_v3/v9.json` (2.1389/2.0833) | Supported |
| Table 7.6 all provider cells; packets with answer 7/12, 12/12, 2/12; first22 5/18, later38 7/24 | audit strata + `llm_runs.json` | Supported |
| Per-dimension 1/12, 10/12, 0/12; det uncertain 11 | `analysis.md` per-dimension | Supported |
| Mean O Integrity 5.33 vs 2.59 | `analysis.json` provider_variation | Supported |
| Hub table (drop, TPR gap CI, FNR, FPR, widths, ratings) | `tables_generated.tex` from `external_hub_validation_20261003_v9r`; SHA256SUMS OK | Supported |
| Formulas: cbrt+veto, eps 0.02, widths 0.15/0.20, FPR ceiling 0.30, anchors, D rule | `scoring/fries.py`, `probes/*`, `osd/agent.py` | Supported (edit 3) |
| Suite repeatability, detection tables, severity sweeps, fairness confirmation, human-review stats | Not recomputed this session (stored-file spot checks only) | **Unverified by me** |
| Test counts (911/9/275, ruff) | Not rerun | **Unverified** |

## Citations
All `\cite` keys resolve; no uncited bib entries; all `\ref` resolve. Online checked: HELM maintenance mode (1 Jun 2026, policy text matches), Fairlearn `MetricFrame` `n_boot`/`ci_quantiles` (0.16.0.dev0 docs), lm-eval README ("over 60 benchmarks", transformers + vLLM). DOIs for Rutinowski, Manzano, Mattioli resolve (HTTP 200); HF pickle page, model-transparency, arXiv 2402.05160 / 1810.01943 resolve. Zenodo DOI returned 403 to curl (bot block) — not verified. Page numbers/venues of older papers not checked against publishers.

## Provenance
* All Appendix C.3 folders and scripts exist. All but `l2_det_vs_llm_20261029_r5` are tracked on `feat/ui-shell` (= origin); none are on `Main`. **`_r5` and `scripts/audit/l2_completion_audit.py` are untracked** (report already says "not yet committed"). Commit before submission or the examiner cannot reach the reported LLM data.
* Only external-audit `run_log.json` records git revisions (`0103344`, `4f58db9`); other "first commit" values are upper bounds — as the report states.
* `analysis.md` in `_r5` still says "v3 HeuristicOSDAgent" (stale; documented in FINDINGS.md and the reproduction guide; folder left unedited by design).
* Controlled-model weights not committed — cannot be reproduced bit-for-bit from the repo; stated in report.
* `fairness_mention_20261025` eval never completed; correctly absent from the report.

## Writing/relevance
Chapters read: 1, 2, 4, 6, 7, 8, 9, 11, App. A-C. Abstract/limitations/negative results (withheld robustness sweep, post-hoc labelling, O=S by construction, inconclusive LLM, integrity scope, human-review caveats, descriptive Hub audit) are preserved and consistent. No rewrite was justified; no generic filler found. Ch3, 6b, 7b and frontmatter were not read line by line.

## Visual check
Rendered and inspected pages 1 (cover), 12 (Table 2.1), 43 (Table 7.6). Other pages, equations and figures were not all inspected visually; text extraction only.

## Unresolved
Commit/preserve `_r5`; unverified items above; Zenodo DOI; Overfull boxes (cosmetic).
