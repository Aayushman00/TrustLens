# Human validation of TrustLens audit findings — protocol

Reviewers validate **individual audit findings against their evidence**. They are
never asked whether a model is "trustworthy", and their verdicts are not ground
truth for trust.

## Reviewers

2–3 people who did not build the probes, thresholds, or O/S/D mapping.
No discussion between reviewers until all sheets are returned.

## Materials (generated, never hand-edited)

```
cd backend
python -m app.scripts.analyze_ratings packet ../results/flawed_model_suite/<results_dir> ../docs/human_rating/<round>
```

- `findings.csv` — one row per (model, FRIES dimension): anonymised `model_code`,
  the finding TrustLens reported, and the measured evidence (metrics, CIs, risks,
  flags). No FRIES score, no O/S/D, no model names.
- `rating_sheet.csv` — `finding_id,rater,verdict,comment`, one copy per reviewer.
- `KEY_do_not_share.csv` — `finding_id -> model`. Held by one team member, used
  only at analysis time.

## Task per finding

Read the finding and its evidence. Answer: **does the evidence support the finding?**

| verdict | meaning |
|---|---|
| `SUPPORTED` | the numbers shown justify the finding as stated |
| `NOT_SUPPORTED` | the numbers contradict it, or it claims more than they show |
| `UNCERTAIN` | not enough information to judge |

Write one sentence in `comment` for every `NOT_SUPPORTED` and `UNCERTAIN`.
About 2 minutes per finding; reviewers may stop and resume.

## Analysis

```
python -m app.scripts.analyze_ratings analyze ratings_all.csv
```

Reports Fleiss' kappa (inter-rater agreement), the majority verdict per finding,
the share of TrustLens findings the majority supports, and the findings where
reviewers split or the majority says `NOT_SUPPORTED`. With this few raters and
findings, report the numbers descriptively and list every disagreement; do not
present them as statistical validation.
