# Reproducing the thesis results

Companion to the report in `report/` (Chapter 10, "Testing and Reproducibility", and Appendix C). It holds the
detail that was moved out of the report so that it stays a research document:
the result-folder map, the pre-declaration plans, the experiment commands, the L1-L10 work-item
mapping, method-version history, per-experiment configuration, hashes, the main-suite tables and
the review-packet list.

## 1. Provenance of the results

* Result files are preserved unchanged after each experiment. A rerun goes into a new folder
  (`_v9`, `_v9r`, `_r3`, `_r4`, `_a2`); earlier folders are never edited. See `results/README.md`.
* The external-audit folders carry a `SHA256SUMS` file. The human-review analysis script
  regenerates its report byte for byte from the raw form export.
* Not every experiment was pre-declared. Plans written *before* the run (see section 3) exist
  for score calibration, the LLM comparison, fairness confirmation, severity sweeps and the
  independent review. Decisions taken after seeing data are listed in the report (Table 5.4,
  "Status of each experiment and of the decisions taken after seeing data").

## 2. Result folders (all under `results/`)

| Folder | Content | Report section |
|---|---|---|
| `flawed_model_suite/eval_results*` | Pilot runs 1-3 | Pilot |
| `flawed_model_suite/final_20261002_*` | Main controlled suite, five runs per model; analysis in `final_20261002_analysis*` | Controlled suite |
| `flawed_model_suite/sweep_20261002_*` | Severity-sweep models, three runs each | Evidence against severity |
| `flawed_model_suite/hub_final_*` | Earlier 15-model Hub run (v3 methodology) | External audit |
| `flawed_model_suite/l3_replay_20261003` | Offline replay of the disclosure-gap change | Disclosure gaps |
| `flawed_model_suite/ground_truth.json` | Detection rules and hidden labels, written before the runs | Detection rules |
| `osd_calibration_20261003` | O/S/D mapping: fit, anchors fixed in advance, analysis on reserved evidence | O/S/D mapping |
| `fairness_confirm_20261003` | Fairness confirmation run | Fairness |
| `defect_severity_20261003`, `_a2` | Severity sweeps as specified, and with deviation A2 | Severity sweeps |
| `l2_det_vs_llm_20261003` (+ `_r3`) | LLM comparison, provider run (22 of 60 answers) | LLM comparison |
| `l2_det_vs_llm_20261029_r5` | **Reported LLM comparison: 60/60 valid runs** (copy of `_r3` + re-attempts of the 38 missing runs with the same provider chain; `FINDINGS.md`, `completion_audit_baseline_v9.json`, `scripts/audit/l2_completion_audit.py`). **The `20261029` in the name is a label, not a run date**: `llm_responses.jsonl` timestamps (UTC) are 2 Oct (22 answers: providers A 9, B 13), 3 Oct (4 provider C answers, logged in `_r3` but not counted valid in its summary) and 28 Oct (34 answers: B 28, A 6); result files were written 28 Oct 22:07-22:24 +05:30. The name is kept to preserve the audit trail. Provider C answers carry model `nvidia/nemotron-3-super-120b-a12b`. `prompt_truncated` is true for the 5 P01 runs (card 11,095 chars > 5,000 limit, applied by `llm_client.py` before the call) | LLM comparison |
| `l2_det_vs_llm_20261022_r4` | Superseded: the 38 missing runs filled by a different evaluator; kept for audit, not reported | LLM comparison |
| `l2_stratified_audit_*` | Per-evaluator-group recomputation (`scripts/audit/l2_stratified.py`) | LLM comparison |
| `l2_claude_eval_*`, `l10_claude_eval_*` | Supplementary LLM runs, kept separate. In the report, `l2_claude_eval_20261003` is the superseded supplementary-evaluation folder (retained for audit; not part of the 60/60 dataset; contributes no values to Table 7.6) | LLM comparison, review |
| `l10_independent_validation_20261003` (+ `_v9`, `_v9r`) | Review packets, official LLM review, v9 reference | Independent review |
| `l10_human_form`, `l10_human_analysis_20261005` | Form material, human-review analysis | Independent review |
| `external_hub_validation_20261003` (+ `_v9r`) | External audit: v8 (untouched) and v9 rerun (used) | External audit |
| `safety_severe_miss_replay_20261022` | Offline replay of the v10 safety rule (exploratory) | Severity sweeps |
| `fairness_mention_20261025` | Not part of the report: a later experiment, documented separately, not used in any reported result | n/a |

## 3. Plans written before the runs (`docs/superpowers/plans/`, prefix `2026-10-03-`)

| Item | File |
|---|---|
| Score calibration | `round3-L1-osd-calibration.md` |
| LLM comparison | `round3-L2-det-vs-llm.md` |
| Disclosure-gap separation | `round3-L3-disclosure-gaps.md` |
| Fairness-rule redesign | `round3-L4-binary-fairness-risk.md`, `round3-L4.1-eod-fairness-risk.md` |
| Fairness confirmation (plan, frozen at commit `8f009fb`; results) | `round3-L4.1-confirmatory-prereg.md`, `round3-L5-fairness-confirm-results.md` |
| Severity sweeps | `round3-L6-defect-severity.md` |
| Independent review | `round3-L10-independent-validation.md`; reviewer material in `results/l10_human_form/` |
| Artifact-set integrity | `docs/adr/0013-artifact-set-integrity.md` |

## 4. Commands

Run from `backend/` with the project virtual environment (training needs `USE_TF=0`). The
Docker stack must be running for API-based runs (rebuild `api` and `worker` after backend
changes). Seeds and output folders are those named in the corresponding plan.

```bash
# controlled suite (data, training, evaluation through the API)
python -m app.scripts.prepare_flawed_suite_data
python -m app.scripts.train_flawed_suite --all
python -m app.scripts.run_flawed_suite_eval
python -m app.scripts.repeat_eval            # repeated runs
python -m app.scripts.compare_ground_truth   # apply the rules fixed in advance

# disclosure-gap separation: offline replay
python -m app.scripts.replay_l3_disclosure_gaps <new_out_dir>

# fairness confirmation run (fresh seed, fresh data)
python -m app.scripts.prepare_flawed_suite_data --fairness-confirm \
    --seed 20261003 --out ../results/fairness_confirm_20261003
python -m app.scripts.train_flawed_suite --fairness-confirm \
    ../results/fairness_confirm_20261003 --seed 20261003
python -m app.scripts.run_fairness_confirm

# severity sweeps
python -m app.scripts.run_defect_severity --out ../results/defect_severity_20261003

# independent review: human analysis (stdlib only, from the repository root)
python results/l10_human_form/analyze_human_responses.py

# external Hub audit
for s in select run profile; do python -m app.scripts.run_external_hub_validation $s; done

# figures and the report (Docker build without a host TeX install: scripts/audit/build_report.sh)
cd report && python make_figures.py && python make_figures_final.py
pdflatex main.tex
```

Setup of the application itself (database, worker, frontend, tests) is in `README.md` and
`docs/TRUSTLENS_LOCAL_DEVELOPMENT.md`; the earlier Mode A/B/C benchmark is in
`docs/experiments_runbook.md`. Implementation detail (component/source-file map, enumerations,
engineering fixes, test inventory) is in `docs/ENGINEERING_NOTES.md`.

Training needs `USE_TF=0`. Result folders carry the suffixes `_v9`, `_v9r`, `_r3`, `_r4`, `_a2`.
`make_figures_final.py` regenerates `fig_eod_forest.pdf` with byte changes; `git checkout` it after
running. `scripts/audit/build_report.sh` builds the PDF in Docker (`\PageLimit` in `report/main.tex` is 70;
the build fails above it; the final 2026-10-28 build is 65 pages including front matter).

## 5. Work items L1-L10 (removed from the thesis)

The thesis uses descriptive names. The repository labels the ten validation and engineering work
items of "round 3" as follows (plans in section 3).

| Label | Thesis name | Problem found | What was done / outcome |
|---|---|---|---|
| L1 | Score mapping scaled to the range of tested defects (repo: score calibration) | O/S/D bands compress severity | v4 mapping fitted on a separate split ($O=S$ by construction). Score range on evaluation evidence 0.68-1.18 -> 4.60-6.65 points |
| L2 | Deterministic vs LLM interpretation | LLM-rated dimensions noisy and quota-bound | 12 fixed packets. Provider run returned 22 of 60 answers; supplementary evaluator supplied 38; low agreement; inconclusive |
| L3 | Disclosure-gap separation | Card-based risk flags fire on clean controls | Control flag rate 1.00/1.00/0.50 -> 0/0/0 (Safety/Explainability/Integrity); recall on injected card defects fell |
| L4, L4.1 | Fairness-rule redesign | Binary fairness evidence could never raise a risk | Excess-DPD candidate rejected; TPR-gap rule with bootstrap-CI width rule adopted after exploratory data |
| L5 | Fairness confirmation | Rule needed confirmation on untouched data | Plan frozen at commit `8f009fb`; H2, H3, H4 held, H1 failed (reference flagged) |
| L6 | Severity sweeps | One severity level; coarse scoring | Evidence consistent with defect level (rho = 1) wherever measured; robustness as specified withheld every rating (A2 re-run) |
| L7 | Artifact integrity | Integrity hashed one file only | Whole artifact-set verification (ADR 0013) |
| L8, L9 | Pipeline hardening | Races and clean-up | Engineering changes, not an experiment (see `docs/ENGINEERING_NOTES.md` section 4) |
| L10 | Independent evidence review | No independent check of TrustLens judgments | Exploratory: 12 blinded packets; 7 human submissions, 1 official LLM answer, 12 supplementary LLM answers |

H1-H4 are the hypotheses of the fairness confirmation, P01-P12 the review packets, R0-R6 the reviewer codes.

## 6. Methodology version history (stamped on evaluations)

From `scoring/methodology_version.py`.

| Version | Change |
|---|---|
| `v3-hardening-2026` | Robustness band from accuracy drop; constant-predictor rule; behavioural safety band (suite ran under this) |
| `v4-disclosure-gaps-2026` | Missing documentation separated from risks; local folders identified by weight hash |
| `v5-binary-fairness-risk-2026` | First fairness redesign (rejected): excess-DPD trigger |
| `v6-eod-fairness-risk-2026` | Final fairness rule `F-FAIR-EOPP` from the EOD with bootstrap CI |
| `v7-artifact-set-integrity-2026` | Whole artifact-set verification |
| `v8-osd-calibrated-map-2026` | O/S/D mapping scaled to the tested defect range (thesis "v4 mapping"; map id `osd-map-v4-calibrated-2026-10-03`) |
| `v9-evidence-guards-2026` | Integrity mismatch floor, safety ceiling on benign FPR (0.30), CI-based detectability |
| `v10-safety-severe-miss-2026` | `S-BEH-SEVERE-MISS` (exploratory) |
| `v11-empty-card-abstain-2026` | Heuristic engine: an empty card gets no rating (code only; every thesis experiment predates it) |

The thesis names "v3 bands", "v4 mapping", "v9 guards" and "v10 rule" after the heuristic bands, the
range-scaled mapping, the evidence guards and the safety rule respectively.

## 7. Experiment configuration detail (removed from the thesis)

* **Dataset:** Civil Comments pinned to revision `f2970eb3...` (recorded from 2026-10-03). Suite eval
  set: 3 000 rows, 20% positive, 282 severe, label-rate gap 0.505. Fairness-confirmation eval set:
  data seed 20261003, 260 severe, groups 2 500 / 500, label rates 0.113 / 0.636, 11 590 texts excluded
  from overlap with suite eval and train slices; flip sizes 115, 230, 403, 576 rows (nested).
* **Training:** `bert-base-uncased`, 3 epochs, lr 2e-5, batch 16, weight decay 0.01, max length 128,
  seed 42 (V2: class-balanced 628 + 628 rows, 4 epochs, lr 5e-5, no weight decay; old design kept as
  `variant2_robustness_old`). `ground_truth.json` still carries the original V2 mechanism string.
* **Reference models:** `unitary/toxic-bert` revision `4d6c22e7...`; 2-label conversion
  (`convert_reference_2label.py`, logit0 = 0, logit1 = z_toxic; max probability difference 9.5e-4 on
  four sentences). Pilot: the reference was a constant predictor (accuracy 0.799, 20% toxic sample;
  2-label accuracy 0.868, EOD 0.174); the pilot Safety variant scored 3.98 vs 3.91; one overall
  score fell 6.79 -> 5.44 between identical runs.
* **Suite detection rules:** `ground_truth.json` (`controls` field added after the runs); score level
  uses control mean +/- max(1.0, 2 x pooled std); evidence level uses majority-of-runs flags.
  LLM configuration frozen in `llm_freeze.json` (provider B, temperature 0.2, prompt `llm_v1`;
  other providers blanked by `docker-compose.experiment.yml`). Suite ran 5x per model, sweeps 3x.
* **Calibration split:** seed 43, 3 000 eval rows + 8 000 clean training rows, seven models,
  nested flips 0.3/0.6/1.0 (Fairness, Safety), attack budgets 0.02-0.10 (Robustness); sha256
  `88ca2538...`. Anchors fixed 22:58:31 UTC, evaluation 22:58:44 UTC (2026-10-02 per the folder);
  `check_frozen` refuses to run on a mismatch. Calibration evidence: fairness gap 0.062 -> 0.381,
  severe FNR 0.290 -> 0.627, robustness drop 0.0106 -> 0.0270 (0.0263 at budget 0.06).
* **Severity sweeps:** robustness swaps = clamp(round(100 x budget), 1, 8); budgets 0.01/0.03/0.05/0.08;
  specified run withheld all levels (coverage 0.9997: one row `:(` with no alphanumeric character);
  A2 drops that row (2 999 rows). Prespecified direction for `relative_degradation` ("increasing") was
  a specification error (three false violations; not re-scored).
* **LLM comparison:** packet schema `l2-evidence-packet-v1`; folders `l2_det_vs_llm_20261003` (+ `_r3`
  resumed run reproduced the official figures), `_20261022_r4` (supplementary, 38 runs, 60/60 parsed).
  Provider attempts: A 9 ok, 12 x 503, 80 x 429; B 13 ok, 82 x 429 (200 000-token daily limit);
  C 0 ok, 79 x 404 (endpoint gone). Mean latency 19.8 s per LLM call, ~2 ms deterministic. Per-group
  table (`scripts/audit/l2_stratified.py`): providers 22 runs / 18 pairs / status 5/18 / definite 5/13 /
  S exact 0.222 / risk-identical 9/12 / triple-identical 0/12; supplementary 38 / 24 / 7/24 / 7/16 /
  0.000 / 21/24 / 3/24; pooled 60 / 36 / 11/36 / 11/25 / 0.111 / 30/36 / 0/36. The 2026-10-22 folder's
  deterministic baseline was regenerated under the v9 agent and differs from the 2026-10-03 file in
  seven cells (P03 Integrity O/S 7/7 -> 1/1; Safety D 8 -> 6 for six packets); its `analysis.md`
  header still reads "v3 HeuristicOSDAgent" (stale label).
* **Human review:** raw CSV export sha256 `da680bbc...`; codes R0-1..R0-6 (shared `R0`, numbered by
  timestamp) and R2; official LLM review prompt `l10-review-v1-2026-10-03`, providers A, B, C one attempt
  each (1 of 12 answered); supplementary review answered by a fresh LLM agent told to read only the
  exported prompt files. Packets frozen before evaluation; first leakage test caught source-file paths
  containing model names (moved to the reference file). Human study used the v9 reference; LLM reviews
  were compared with the v8 reference.
* **External audit:** `selection.json` written before evaluation; revisions re-resolved against the
  Hub; v9r rerun at git head `0103344`; earlier 15-model run (2026-10-02; 14 of 15 on backup ratings)
  caught `pysentimiento/bert-it-hate-speech` as a near-constant predictor (harmful recall 0.023);
  `textdetox/xlmr-large-toxicity-classifier` and `xlmr-base-toxicity-classifier` share weights
  sha256 `829a9d93...`. Tamper demo sha256 `5918a851...` -> `74c230bb...`.
* **v10 safety replay:** `results/safety_severe_miss_replay_20261022`.

## 8. Main controlled suite (per-defect outcomes and dimension profiles)

Per-defect outcomes: Robustness (V2) detected by the score (drop 0.041; 7.56 vs 8.65, `R-ROB-PERT`
silent because drop < 0.05); Fairness (V1) missed by every rule (EOD 0.164 vs control 0.174; excess
DPD 0.000); Safety (V5) measured (severe FNR 0.44, CI [0.38, 0.50] vs 0.355) but both scored 6.60;
card defects lowered LLM-rated scores (V3 Explainability 4.0; V4/V4b Integrity 2.3-2.4) but not below
the threshold given control variation (5.2 +/- 1.2 and 4.5 +/- 1.8); the overfit V2 was also less fair
(EOD 0.370).

Mean dimension scores +/- std over five runs (suite, `v3-hardening-2026`, `llm_v1`):

| Model | Fair. | Rob. | Integ. | Expl. | Safety |
|---|---|---|---|---|---|
| reference_hub | 8.00 | 8.65 | 8.65 | 6.00 | 6.60 |
| reference 2-label | 8.00 | 8.65 | 4.54 +/- 1.80 | 5.20 +/- 1.20 | 6.60 |
| V1 fairness | 8.00 | 8.65 | 2.41 +/- 0.27 | 8.13 +/- 0.18 | 7.27 |
| V2 robustness | 6.60 | 7.56 | 3.22 +/- 0.80 | 8.66 +/- 0.34 | 7.56 |
| V3 explainability | 8.65 | 8.65 | 2.44 +/- 0.50 | 4.02 +/- 0.53 | 6.95 |
| V4 integrity (+fair.) | 8.00 | 8.65 | 2.30 +/- 0.22 | 3.82 +/- 1.05 | 7.27 |
| V4b integrity (clean) | 8.65 | 8.65 | 2.43 +/- 0.13 | 3.78 +/- 0.60 | 6.95 |
| V5 safety | 8.65 | 8.65 | 2.81 +/- 0.45 | 8.59 +/- 0.44 | 6.60 |
| V6 compound | 8.00 | 8.65 | 4.23 +/- 2.23 | 1.52 +/- 0.73 | 6.95 |

Fairness, Robustness and Safety have zero spread; Integrity and Explainability inherit LLM variation
(provider rate limits and three DNS failures forced 11 of 45 runs onto backup ratings). The Hub
import of the reference weights scored 8.65 +/- 0.00 on Integrity (pinned revision and file listing
counted by the v3 band); the cause was not isolated.

## 9. Review packets

| Packet | Dimension | Source | Role |
|---|---|---|---|
| P01 | Fairness | fairness run, flip 0.7 | clear injected disparity |
| P02 | Fairness | fairness run, clean control | control; rating withheld (interval too wide) |
| P03 | Fairness | fairness run, 2-label reference | external control TrustLens flags; borderline |
| P04 | Robustness | sweep with deviation A2, 8 swaps | largest drop, no risk |
| P05 | Robustness | robustness sweep without A2 | insufficient evidence (one row not perturbable) |
| P06 | Safety | safety sweep, rate 1.0 | strongest severe-harm miss |
| P07 | Safety | safety sweep, rate 0 | control |
| P08 | Integrity | tampered V1 vs manifest | weight mismatch |
| P09 | Integrity | V1 vs its own manifest | verified control |
| P10 | Explainability | V3 skeleton card | auto-generated skeleton |
| P11 | Explainability | V4 card | overclaiming card |
| P12 | Explainability | 2-label reference card | real published card; borderline |

## 10. Decisions taken after seeing data (full list)

TPR gap as fairness trigger (after exploratory suite; confirmed on fresh data, H1 failed); V2
redesign (first design collapsed to a majority-class model); V4b added 2026-10-02 so Integrity is
tested without a Fairness confound; `controls` field in `ground_truth.json` added after the runs;
robustness deviation A2; v4 evaluation values known before the mapping was written (pre-declaration
limits the choice to two anchors); v9 benign-FPR floor (0.30) set after the external Hub run (marked
PROPOSED); v9 integrity floor and CI-based D (audit fixes, not validated on fresh data);
supplementary LLM runs added because API providers were unavailable (separate folders; the
orchestrating session was not blind).

## 11. Figures, generated tables and prompt listings of the report

* `python make_figures.py && python make_figures_final.py` (from `report/`) regenerate the data figures
  from the frozen result files: `fig_v3_v4.pdf`, `fig_eod_forest.pdf`, `fig_l6.pdf`, `fig_hub_profiles.pdf`
  and, added in the 2026-10-28 revision, `fig_layers.pdf` (evidence, risk decision and score on one axis),
  `fig_hub_eod.pdf` (Hub-audit TPR-gap intervals) and `fig_hub_tradeoff.pdf` (severe miss rate against
  benign false-positive rate). Layer-comparison values are read from the confirmation and sweep analyses;
  the original-band and range-scaled triples are copied from `results/osd_calibration_20261003/FINDINGS.md`.
* `python make_tables.py` (from `report/`) writes `chapters/tables_generated.tex` (Appendix A, per-model
  tables of the external audit, read from `results/external_hub_validation_20261003_v9r/`) and
  `prompts/*.txt` (the two LLM prompt templates of Appendix B, read from the source by AST so they cannot drift
  from `backend/app/osd/llm_client.py` and `backend/app/scripts/run_l10_validation.py`).
* `scripts/audit/build_report.sh` copies `main.tex`, `chapters/`, `figures/` and `prompts/` to a scratch
  directory and builds in Docker.
* Not used in the thesis: `ui_results_profile.png`, `ui_review.jpg`, `ui_report.jpg` (routine UI; the scores
  of `ui_results_profile.png` equal those of `martin-ha/toxic-comment-model` in the v9r audit, but its header
  reads "engine: deterministic" and the run behind the screenshot is not recorded), and the older
  `fig_heatmap.pdf`, `fig_overall.pdf`, `fig_probes.pdf`, `fig_radar.pdf`, `fig_variance.pdf`.

## 12. Facts about the stored external audit that the thesis relies on

* Integrity coverage: in every v9r evaluation the artifact manifest holds one file (`coverage:
  weight_files`, source `hf_hub_lfs`): the weight file the worker loaded (`model.safetensors` for
  toxic-bert, dynabench, xlmr-large and bert-tiny; `pytorch_model.bin` for unbiased-toxic-roberta, s-nlp and
  martin-ha). Other weight files in the same repositories (for example `pytorch_model.bin` next to
  `model.safetensors`, a Flax file, ONNX exports) were not hashed.
* LLM prompt: the card is cut to 5 000 characters (`llm_prompt_truncated: true` for toxic-bert, whose card has
  11 095 characters). The LLM judgment of the safety card (e.g. toxic-bert 3/4/4) is stored in
  `osd_metadata.llm_card_judgment` but the Safety rating is the behavioural mapping (7/7/6).
* `results/external_hub_validation_20261003_v9r/SHA256SUMS` verifies with `sha256sum -c` (checked 2026-10-28).
* `results/fairness_mention_20261025/` is a later mention-based fairness experiment that is not part of the
  report; the report states that no mention-based rerun was performed.

## Availability of the reported LLM-comparison artifacts

As of 28 Oct 2026 these files are **uncommitted** (`results/` is covered by `.gitignore`; none is on `origin/feat/ui-shell`),
so they must accompany the report in the supplied source archive:

* `results/l2_det_vs_llm_20261029_r5/` (`llm_responses.jsonl`, `llm_runs.json`, `deterministic.json`,
  `deterministic_original_v3.json`, `completion_audit_baseline_v9.json`, `completion_audit_baseline_v3.json`, `packets/`)
* `results/l2_det_vs_llm_20261003_r3/` (first-session log that `_r5` extends)
* `scripts/audit/l2_completion_audit.py`

Check: `python -I scripts/audit/l2_completion_audit.py --det <abs path>/results/l2_det_vs_llm_20261029_r5/deterministic.json --write <out.json>`
(the path must be absolute and under the repo root; `deterministic_original_v3.json` gives the 3 Oct baseline).
