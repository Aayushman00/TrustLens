# 08 — Worked example (illustrative)

> **All numbers below are invented to show the mechanics.** They are not measurements. Real values come from TrustBench runs. The arithmetic is exact so reviewers can check the rule by hand.

Scenario: a team wants to use a Hub toxicity classifier, `acme/toxic-bert-v3`, to auto-flag comments for a moderation queue where humans review flagged items.

## 1. Profile: `content-moderation`

| Dimension | Tolerance τ (max acceptable risk) | Stake (cost if violated) | Control credit (share of cost removed by human review) |
| --------- | --------------------------------- | ------------------------ | ------------------------------------------------------ |
| Fairness | 0.10 | 4 | 0.5 |
| Robustness | 0.15 | 2 | 0.3 |
| Integrity | 0.05 | 5 | 0.0 |
| Explainability | 0.30 | 1 | 0.5 |
| Safety | 0.05 | 5 | 0.6 |

Other costs: `control_cost = 1.5` (running the review queue), `reject_cost = 6` (not having automation), `evidence_cost` of a follow-up fairness run = 0.3.

Hard fails: none triggered (hashes match the pinned revision, no unsafe opcodes). Under ADR 0014, a mismatch would have ended the example here with `REJECT`.

## 2. Round 1 — first audit (small budget: 1 000 rows)

Evidence flows through the calibrated links into risk posteriors. From the posteriors we read P(risk > τ):

| Dimension | Posterior mean risk | P(risk > τ) | Why |
| --------- | ------------------- | ----------- | --- |
| Fairness | 0.12 | **0.35** | Counterfactual flip rate and group TPR gap both near tolerance; wide interval (few rows for small groups) |
| Robustness | 0.07 | 0.10 | Typo and format families fine; paraphrase ok |
| Integrity | 0.01 | 0.01 | Hash match; revision pinned; small residual for licence ambiguity |
| Explainability | 0.31 | 0.60 | Faithfulness weak; low stake |
| Safety | 0.03 | 0.20 | Severe-miss CI upper bound straddles tolerance |

Expected losses (the decision rule from spec 03):

```
ADOPT                = 4·0.35 + 2·0.10 + 5·0.01 + 1·0.60 + 5·0.20
                     = 1.40 + 0.20 + 0.05 + 0.60 + 1.00                     = 3.25

ADOPT_WITH_CONTROLS  = 1.5 + 4·(1−0.5)·0.35 + 2·(1−0.3)·0.10 + 5·(1−0)·0.01
                           + 1·(1−0.5)·0.60 + 5·(1−0.6)·0.20
                     = 1.5 + 0.70 + 0.14 + 0.05 + 0.30 + 0.40               = 3.09

REJECT               = 6.00
```

Best terminal action is `ADOPT_WITH_CONTROLS` at 3.09, only 0.16 better than `ADOPT`. The margin is thin, so the engine asks whether more evidence is worth buying.

## 3. Value of information

Candidate follow-ups and their simulated effect (preposterior over the current posteriors):

| Follow-up | Cost | Expected loss afterwards | Net gain vs 3.09 |
| --------- | ---- | ------------------------ | ---------------- |
| More fairness rows (×5) and intersectional slices | 0.3 | 2.55 | 3.09 − (2.55 + 0.30) = **+0.24** |
| More safety rows | 0.2 | 2.95 | −0.06 |
| Add paraphrase robustness at larger n | 0.4 | 3.05 | −0.36 |

Largest net gain is positive, so the action is `COLLECT_MORE_EVIDENCE` with expected loss 2.85 and the plan "fairness ×5". The report shows the plan, not just the verdict.

## 4. Round 2 — after the fairness follow-up

The extra rows narrow the fairness interval. P(risk > τ) falls from 0.35 to 0.08.

```
ADOPT                = 4·0.08 + 0.20 + 0.05 + 0.60 + 1.00                   = 2.17
ADOPT_WITH_CONTROLS  = 1.5 + 0.16 + 0.14 + 0.05 + 0.30 + 0.40               = 2.55
REJECT               = 6.00
```

Now `ADOPT` wins at 2.17. Binding dimension: **Safety** (contributes 1.00 of 2.17), followed by Explainability (0.60). The report states: *adopt for this profile; monitor severe-miss rate; explainability is weak but low-stake here.*

## 5. What changes with a different profile

Same evidence, profile `hiring-screen` (Fairness stake 10, tolerance 0.05): fairness contributes 10·P(risk > 0.05), which is far larger, and the best action flips to `REJECT` or `ADOPT_WITH_CONTROLS` with a mandatory audit step. The model has not changed; the stated use has. That is the intended behaviour, and it is why the output is "decision for this profile" and not a global trust score.

## 6. What a reviewer sees on the report page

1. Verdict + all four expected losses (so the margin is visible).
2. Per-dimension risk with interval, tolerance line, P(violation).
3. Evidence table with hashes; each row opens the raw probe outputs.
4. VOI plan with predicted loss reduction.
5. Applicability matrix: which probes ran, which were `not_applicable` and why.
6. Sensitivity panel: which stake or tolerance changes (±50%) would flip the action.
7. Methodology versions (probes, link, profile schema) and the TrustBench validity numbers the link was calibrated on.

## 7. Sanity checks this example passes

- Narrower posterior (more data, same estimate) lowered `ADOPT`'s loss: monotone in information.
- Changing a stake changes only the weighted violation term it multiplies.
- If integrity had hard-failed, `ADOPT` and `ADOPT_WITH_CONTROLS` would be ∞ and the verdict `REJECT` regardless of the other rows.
