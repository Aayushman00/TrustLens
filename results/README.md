# Results

Frozen experiment outputs cited by the thesis in [`report/`](../report/).

> [!IMPORTANT]
> Do not rename or move anything here. Scripts in `backend/app/scripts/`, the docs and the report reference these paths, and several folders embed their own path and hash manifests. Reruns go into new folders; earlier versions stay untouched.

## Folder map

| Path | What it holds |
| ---- | ------------- |
| `manifest_v1.jsonl`, `mode_a_manual.csv`, `mode_b_*`, `mode_c_*` | Core experiment modes A/B/C (see [`docs/experiments_runbook.md`](../docs/experiments_runbook.md)) |
| `analysis/` | Tables and figures derived from the modes above (`TABLES.md`) |
| `flawed_model_suite/` | Deliberately flawed models for the O/S/D demo |
| `osd_calibration_*` | L1: O/S/D calibration |
| `l2_*` | L2: deterministic vs LLM interpretation (details below) |
| `defect_severity_*` | L6: defect severity |
| `fairness_confirm_*` | L5: confirmatory fairness |
| `external_hub_validation_*` | External Hub audit (`_v9r` is the latest) |
| `l10_*` | L10: independent validation. `l10_human_*` holds the human reviewer form and analysis |
| `safety_severe_miss_replay_*` | Offline replay of the v10 Safety severe-miss rule on stored evidence (exploratory) |
| `l2_stratified_audit_*` | Read-only recomputation of L2 per evaluator stratum (`_baseline_v3` is the 2026-10-03 deterministic file, `_baseline_v9` the 2026-10-22 file), from `scripts/audit/l2_stratified.py` |

### The `l2_*` folders

| Folder | Status |
| ------ | ------ |
| `_r3` | Provider rerun, 22 of 60 runs |
| `_20261022_r4` | Superseded fill with 38 runs from a different evaluator, kept for audit |
| `_20261029_r5` | **Reported run.** 60/60 valid after re-attempting the missing runs with the same provider chain |

## Naming

`YYYYMMDD` is the run date. `vN` and `rN` mark a rerun of a frozen folder.

## Reproducing

The folder-by-folder map, the pre-declaration plans and the commands that regenerate these results are in [`docs/REPRODUCING_THESIS_RESULTS.md`](../docs/REPRODUCING_THESIS_RESULTS.md).
