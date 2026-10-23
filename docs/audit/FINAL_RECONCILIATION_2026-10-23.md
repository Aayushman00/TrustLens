# Final reconciliation, 2026-10-23

## L2 fractions: definitions and arithmetic

Unit = packet-by-dimension pair (12 packets x 3 dimensions = 36 possible). LLM side = modal risk answer over the valid
runs of the stratum. "Status agreement" = modal LLM risk answer equals the deterministic risk answer (YES/NO/UNCERTAIN).
Source: `results/l2_det_vs_llm_20261022_r4/{deterministic,llm_runs}.json`, recomputed with the original `compare()`
(`scripts/audit/l2_stratified.py`; test `backend/tests/test_report_claims.py::test_l2_strata_reconcile_by_overlap`).

| Block of pairs | Packets | Evaluators with answers | Pairs | Agreeing |
|---|---|---|---|---|
| A | P01-P04 | providers only | 12 | 4 |
| B | P05, P09 | 1 provider run + 4 supplementary runs each | 6 | 1 |
| C | P06-P08, P10-P12 | supplementary only | 18 | 6 |

* Providers-only stratum = A + B = 18 pairs, 5 agreeing.
* Supplementary-only stratum = B + C = 24 pairs, 7 agreeing.
* Pooled = A + B + C = 36 pairs, 11 agreeing.
* Strata are **not disjoint**: they overlap on block B (6 pairs, 1 agreeing).
  Inclusion-exclusion: 5 + 7 - 1 = 11 and 18 + 24 - 6 = 36. Mathematically compatible.
* On every block-B pair the provider-only, supplementary-only and pooled modal answers are identical (per-pair check), so
  pooling changed no outcome. An earlier sentence in the report claiming that pooling changes the modal answer on
  P05/P09 was wrong; it was replaced. No published number changed.
* Separate issue (not an arithmetic one): O/S/D error metrics depend on the deterministic baseline file; the 2026-10-22
  file differs from the 2026-10-03 file in 7 cells. Status agreement does not depend on those cells.

Verdict: compatible after clarifying the denominator; the Ch7 table caption now states the unit and the overlap.

## Reference list

Citation keys: 24 cited, 24 defined. Bibliographic content: the six 2024-25 trust-metric references were looked up online
(Rutinowski xAI 2024; Manzano SoftwareX 26:101740; Vashistha and Farahi AISTATS 2025 PMLR 258 and arXiv 2401.02062 [also
AAAI 2024]; Kemmerzell ACM CSUR 2025; Mattioli AI and Ethics 4(1):15-25, DOI resolves to that title) and match. The other
eighteen (Hardt, Borkan, Mehrabi, HotFlip, CheckList, BadNets, Jiang, BERT, Transformers, Efron, Wilson, Spearman, Cohen,
Fleiss, Krippendorff, Mitchell, Gebru, NIST AI RMF) were checked against background knowledge only, not looked up.

## Clean-checkout PDF build

* Source: detached worktree at commit `6f44479` (outside the repository, removed afterwards).
* Command: `bash scripts/audit/build_report.sh` (Docker `texlive/texlive:latest-medium`, 4 `pdflatex` passes).
* Result: 65 pages (limit 65), 0 LaTeX errors, 0 undefined references; two overfull boxes of about 2 pt (Table 4.3, Table 7.13),
  nothing clipped.
* Text of the built PDF contains: 5/18, 7/24, 11/36, "5 + 7", 913 test items, 911 passed, the v11 version-table row,
  `G-ROB-CI-WIDE`, "Conditions of the review", "near-uniform YES", and the dataset-revision caveat.
* Pages rendered and read in this pass: human-study discussion (p. 38), limitations 10.4 (p. 51), bibliography (p. 54);
  earlier pass: abstract, equations, version table, artifact table, L2 table, hub tables. Cosmetic only: the bibliography
  page heading renders as "Bibliography" while the table of contents says "References"; Table 7.10 row labels
  repeat Q1-Q3 with a hyphenated "suffi-cient".
* Not rendered page by page: the remaining ~50 pages (text-scanned for control characters and stray `\command` strings only).
* Fresh runs on the tree before this commit: backend pytest 911 passed, 2 skipped (exit 0), 913 collected; ruff clean.
  Worker and frontend suites were not source-changed since the previous gate run and were not re-run in this pass.
