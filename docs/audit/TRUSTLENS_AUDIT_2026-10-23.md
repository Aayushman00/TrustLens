# TrustLens research audit, 2026-10-23 (branch `docs/report-final`)

Scope: verify report claims against frozen artifacts, harden what is genuinely defective, keep frozen
evidence untouched. **Not done:** no new LLM, fairness or Hub experiment was run (no provider access was
used; nothing was simulated); no new methodology version was created. Items marked *unverified* were not
independently recomputed.

## 1. Issue register

| # | Sev | Issue | Evidence | Root cause | Disposition |
|---|---|---|---|---|---|
| 1 | High | L2 provider-only O/S/D errors (MAE 1.78 / 2.17 / 1.78 / 2.22) and the 2026-10-22 pooled errors (2.19 / 1.86 / 2.19 / 2.31) use **different deterministic baselines** | `results/l2_det_vs_llm_20261003/deterministic.json` vs `..._20261022_r4/deterministic.json` differ in 7 cells (P03 Integrity 7/7 to 1/1; Safety D 8 to 6 for six packets) | r4 re-ran the deterministic side under the v9 agent; its `analysis.md` header still says "v3" | Stated in report (Ch7, Table 7.9 text); frozen folder untouched. Provider stratum re-run against the 2026-10-03 baseline reproduces the official numbers exactly |
| 2 | High | "LLM triple never repeats (0/36)" pools three evaluators | `scripts/audit/l2_stratified.py`: providers 0/12; supplementary Claude alone 3/24 | Modal pooling of heterogeneous runs | Report qualified (Ch7, Ch8 RQ4 and discussion) |
| 3 | Med | "Possible tool assistance" limitation inferred AI use from prose style | Ch10 | Style is not evidence | Replaced by "conditions of the review are unverified" |
| 4 | Med | Report version table stopped at v10; code is `v11-empty-card-abstain-2026` (uncommitted); Ch4 said empty card gives (2,2,3) | `methodology_version.py`, `osd/agent.py` diff | Report lagged working tree | v11 row and Ch4 bullet fixed; all experiments predate v11 |
| 5 | Med | `score_from_finalized_osd` would silently re-weight (1/n) if fewer than 5 dimensions were passed | `fries.py`, `fries_total` default weights | Completeness guard lived only in callers (they do withhold) | Defense-in-depth guard added; formula unchanged; no historical result affected |
| 6 | Med | Ch9 said Civil Comments is "pinned"; stored data manifests record no revision (pin added to code 2026-10-03, commit `72ccbd9`, after the 10-02 eval set) | `eval_set_manifest.json` has no revision; no `results/**/*.json` contains the hash | Provenance gap | Claim weakened in Ch9. **Unresolved**: dataset revision of earlier runs is unrecorded |
| 7 | Low | Rendering bug: a TAB swallowed the backslash of `\textbf`, printing "extbf0/36" | visual inspection of p.37 | Escape damage in an earlier edit | Fixed; all chapters scanned for control characters |
| 8 | Low | Calibration text did not say the v4 range is partly by construction | anchors are fitted to the injected span | n/a | Caveat added (Ch7) |
| 9 | Low | Abstract: sufficiency agreement 93 % is prevalence-inflated (kappa 0.59) | `agreement.json` | n/a | Abstract qualified |
| 10 | Low | Test counts stale (895 / 893 / 268 s) | pytest | n/a | Updated: 912 collected, 910 passed, 2 skipped |
| 11 | Info | `multirow` is declared in `main.tex` but never used | grep | n/a | Left as is |

## 2. FRIES mathematical verification

| Report (Ch4, Eq. 4.1-4.2) | Implementation (`scoring/fries.py`) | Status |
|---|---|---|
| Pi = cbrt(O S D); 0 if any component is 0 | `risk_pi`; explicit 10/10/10 gives 10.0 | matches |
| T_a = mean Pi over a dimension's risks | `aspect_score`; empty list gives 0.0 (pure function only; `_parse_risks` rejects an empty `risks` list) | matches; numerical zero is distinct from missing (callers withhold) |
| FRIES = sum w_a T_a, default w = 0.2 | `fries_total`: 1/n; custom weights each >= 0.1, sum 1 (tol 1e-6) | matches for n = 5; n != 5 now rejected by `score_from_finalized_osd` |
| components are integers 0..10 | `_validate_component` rejects bool, float, out-of-range | matches |
| rounding | per-risk Pi, dimension and total rounded to 4 dp | consistent |

Worked examples: (1,2,2) gives 1.59; (9,9,8) gives 8.65; fixtures 1-10 (golden Table 8) pass. New tests in
`backend/tests/test_fries_scorer.py` (+12 cases): partial dimension set rejected, empty risks error,
veto inside a mean (4.5), multi-risk with custom weights and rounding, order/case invariance, invalid
components. Rendered equations (PDF p.21) are legible. **Historical results affected: none.**

## 3. Experiment verification

| Result | Method | Outcome |
|---|---|---|
| L2 exact status 0.3056 (11/36); 60 runs, 0 fallbacks | `scripts/audit/l2_stratified.py` (reuses original `compare()`) | verified |
| L2 provider-only 5/18 = 0.278; severity MAE 1.78; O/S/D MAE 2.17 / 1.78 / 2.22 | same, with the 2026-10-03 baseline | verified (see issue 1) |
| L2 supplementary Claude alone: 7/24 status, 3/24 identical triples, 21/24 risk-identical | same | new; `results/l2_stratified_audit_20261023_baseline_v{3,9}/` |
| L10: 7 submissions, 6 share R0; Q1-Q3 mean pairwise, Fleiss kappa, Q4 Krippendorff alpha, pair counts | `scripts/audit/l10_recompute.py` (independent statistics code) | matches `agreement.json` for all 7 and R0-only; CSV sha256 `da680bbc...` confirmed |
| Fairness confirmation: H1 fails, H2 holds, H3 rho = 1; clean-control CI width 0.1529 > 0.15 gate | `analysis.json`, `analysis.md` | verified; report frames H1 failure as a real observed TPR gap (0.145), not as a validated control |
| v3 range 1.3-1.7 (original sweeps), held-out v3 0.68-1.18, v4 4.60-6.65 | FINDINGS.md; Pi recomputed by hand (6/6/8 = 6.60, 4/4/8 = 5.04, 1/1/8 = 2.00) | verified; the two v3 ranges are different data and the report labels them |
| Hub table (7 models; accuracy, severe FNR, benign FPR, severe n = 282, pinned revisions, FINALIZED) | `profiles.json`, `evaluations/*.json` | all seven severe-FNR / benign-FPR values match; Safety O/S/D confirmed heuristic (v4 map), LLM gave only a card judgment |
| Backend pytest | full run | 910 passed, 2 skipped, 1 warning (912 collected); ruff clean |
| Worker / frontend | run | 9 passed / 275 passed (29 files) |

*Unverified here:* robustness character-swap generator internals, bootstrap-discard code path, Wilson-interval
implementation, per-model label mappings, per-reviewer rationale statistics, the bibliography, Chapters 2-3.

## 4. Claim ledger (headline claims)

| ID | Claim | Source | Status | Action |
|---|---|---|---|---|
| C1 | v3 score range 1.3-1.7 | Table in Ch7, FINDINGS | verified | none |
| C2 | held-out v4 range 4.60-6.65 | FINDINGS | verified; partly by construction | caveat added |
| C3 | H1 failed (reference flagged) | fairness_confirm | verified | none (already transparent) |
| C4 | 22/60 provider, 38 supplementary | `llm_runs.json` (9 + 13 + 38) | verified | none |
| C5 | agreement 0.31 over 36 pairs | analysis.json | verified, pooled/heterogeneous | stratified table |
| C6 | triple non-repeat 0/36 | recomputed | true only pooled; 3/24 for one evaluator | qualified |
| C7 | 7 submissions, 6 share R0 | CSV | verified | none |
| C8 | agreement statistics | recomputed | verified | prevalence caveat in abstract |
| C9 | 895 tests, 893 passed / 2 skipped | pytest | superseded | 912 / 910 / 2 |
| C10 | Civil Comments pinned | repo | partially true | weakened |
| C11 | Hub metrics; 2 abstentions (toxic-bert CI width 0.154; bert-tiny FPR 0.367 > 0.30) | profiles | verified | none |

## 5. Methodological position

* **Fairness:** the TPR-gap rule is a disparity screen. Its 0.02 tolerance is far below the typical CI half-width
  (about 0.07 with 500 minority-group rows), so any real gap of roughly 0.1 or more is flagged. Recommendation:
  retain as screening evidence only (the report already says so); do not tune on the confirmation data; any revised
  rule must be a new methodology version evaluated on untouched data. Not changed.
* **O/S/D mapping:** monotone and discriminative on synthetic severity only; not calibrated to real-world harm.
* **L2 and human study:** descriptive; R0 independence unresolved; no validation claim.
* **Integrity:** hash match means equality with a reference manifest, not safety or authenticity (stated in Ch4).

## 6. Build and reproduction

The report builds with `pdflatex` run four times: 65 pages, 0 undefined references, two overfull boxes of about 2 pt.
No TeX is on the host PATH; the build used `texlive/texlive:latest-medium` (Docker) with `titlesec.sty` copied from
CTAN and a scratch copy of `main.tex` without the unused `multirow` package (`tlmgr` in the image cannot update).
`main.tex` itself is unchanged by this audit. The hard limit is 65 pages (`\PageLimit` in `main.tex`); the L2
additions were paid for by shrinking two figures and trimming the first-supplementary paragraph. Pages 21, 22, 37
and the abstract were rendered and inspected.

## 7. Submission readiness

Submittable with these remaining risks, highest first:
1. Dataset revision unrecorded for the 2026-10-02 runs.
2. Post-hoc rules (v6 fairness, v9 safety floor) have no fresh-data confirmation.
3. Reviewer study: seven submissions, six under one shared code; independence unresolved.
4. LLM comparison is heterogeneous; no single-provider rerun (future work).
5. The v11 change, the report edits and this audit are uncommitted in the working tree.
