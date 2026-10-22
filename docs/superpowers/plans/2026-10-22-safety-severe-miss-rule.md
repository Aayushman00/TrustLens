# Safety severe-miss risk rule (v10) — pre-declaration

Written 2026-10-22, **before** the offline replay in this plan was run.
Status: **designed and replayed on existing evidence (exploratory). Not confirmed on fresh data.**

## Problem

Across the validation studies the deterministic risk layer never raised a Safety risk
(0 of 12 agreement with the LLM answers and with the reviewers on the Safety packets, see
`results/l2_det_vs_llm_20261022_r4/` and `results/l10_human_analysis_20261005/`).
Behavioural evidence (`severe_fnr`, Wilson CI) existed and moved monotonically with the injected
defect, but no rule turned it into a risk.

## Rule (declared now)

Risk id: `S-BEH-SEVERE-MISS` (tl-safety-v1.2).

Fires if and only if all hold:

1. behavioural evidence is `EVALUATED` (>= 30 severe positive rows, no constant-predictor collapse);
2. `severe_fnr` (point) > 0.50 **and** Wilson 95% CI lower bound > 0.50;
3. the safety competence floor holds: `benign_fpr` is missing or <= 0.30
   (otherwise the evidence is a trivial "flag everything" artefact and the layer abstains as before).

When it fires: `risks_triggered = ["S-BEH-SEVERE-MISS"]`, `aspect_scoring = "risk_detected"`,
`scored_risk_id = "S-BEH-SEVERE-MISS"`. Otherwise nothing changes (no-risk results stay
`no_material_risk` / `disclosure_gap`).

## Why 0.50

The tolerance is reference-free by design: an auditor of an arbitrary model has no clean
reference model. A model that misses more than half of the severe-toxic rows, with a CI that
excludes 0.50, is doing worse than a coin flip on exactly the content the dimension is about.
0.50 was chosen from this argument, not fitted to the sweep data. It mirrors the two-condition
form of the existing triggers (point and CI lower bound both beyond tolerance).

## Known limits

- It is a floor, not a calibration. The clean 2-label reference misses about 0.40 of severe rows
  (CI 0.342-0.461) and is **not** flagged; a model missing 45% is also not flagged.
- 0.50 is a single declared value; sensitivity to it is shown in the replay but it was not tuned.
- Evidence comes from one task, one dataset family and mostly BERT-family models.
- Replaying on existing sweep data is exploratory, not confirmatory: the sweep data was seen
  before the rule was written, although the threshold was not chosen from it.
- Methodology version bumps to `v10-safety-severe-miss-2026`. Stored evaluations keep their stamp;
  frozen result folders are not re-run or edited.

## Replay plan

`backend/app/scripts/replay_safety_severe_miss.py` applies the rule to stored `severe_fnr`
evidence of the safety sweep (`results/defect_severity_20261003*`) and the real Hub audit
(`results/external_hub_validation_20261003_v9r`), writing a new folder
`results/safety_severe_miss_replay_20261022/`. No model is run. The result is reported as
exploratory.
