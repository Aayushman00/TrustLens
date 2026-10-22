# results/

Frozen experiment outputs cited by the thesis (`report/`). Do not rename or move:
scripts in `backend/app/scripts/`, `docs/`, and the report reference these paths,
and several folders embed their own path/hash manifests.

| Path | What |
|------|------|
| `manifest_v1.jsonl`, `mode_a_manual.csv`, `mode_b_*`, `mode_c_*` | Core experiment modes A/B/C (see `docs/experiments_runbook.md`) |
| `analysis/` | Tables and figures derived from the modes above (`TABLES.md`) |
| `flawed_model_suite/` | Deliberately flawed models for OSD demo |
| `osd_calibration_*` | L1 OSD calibration |
| `l2_*` | L2 deterministic-vs-LLM interpretation (`_r3` = provider rerun, 22/60; `_20261022_r4` = 60/60 with 38 supplemental Claude runs) |
| `defect_severity_*` | L6 defect severity |
| `fairness_confirm_*` | L5 confirmatory fairness |
| `external_hub_validation_*` | External Hub audit (`_v9r` = latest) |
| `l10_*` | L10 independent validation; `l10_human_*` = human reviewer form and analysis |
| `safety_severe_miss_replay_*` | Offline replay of the v10 Safety severe-miss rule on stored evidence (exploratory) |

Suffixes: `YYYYMMDD` run date; `vN`/`rN` = rerun of a frozen folder (earlier versions untouched).
