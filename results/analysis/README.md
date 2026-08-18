# Phase 26 analysis artifacts

Regenerated from `results/mode_c_runs.csv`, `mode_c_summary.csv`,
`mode_b_reviews.csv`, and `mode_a_manual.csv`. Does not query the API or DB.

```powershell
cd backend
python -m app.scripts.analyze_experiments
```

T1 means/stds are asserted against `mode_c_summary.csv` (script exits non-zero
on mismatch). Agent O/S/D remains **PROPOSED**. Mode A/B labels are
`ai-provisional`.

Write-up: [`docs/results_chapter.md`](../../docs/results_chapter.md),
[`docs/RESULTS_SUMMARY.md`](../../docs/RESULTS_SUMMARY.md).
