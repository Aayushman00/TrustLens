# Human validation packets (2026-10-02)

Protocol: `docs/human_rating/protocol.md`. Generated with
`python -m app.scripts.analyze_ratings packet <inputs_dir> <round_dir> --seed N`.

| round | inputs | findings |
|---|---|---|
| `round_controlled` | run 1 of each controlled suite model (`final_20261002_repeat5*/raw/*__run1.json`) | 45 |
| `round_real` | the 15 real Hub models (`hub_final_c0*/`) | 75 |

Give reviewers **only** `findings.csv` and a copy of `rating_sheet.csv` per round.
`KEY_do_not_share.csv` and `inputs_*` contain model names: keep them with one
team member until analysis (`python -m app.scripts.analyze_ratings analyze <ratings.csv>`).
