# 08 — Worked example (script-reproduced)

> Numbers come from spike S9: `python docs/v2/spikes/s9_worked_example.py` (seed 9, 200 000 posterior draws) writes `spikes/results/s9_worked_example.json`. The severe-miss input is a **[v1]** measurement (unitary/toxic-bert, 100 of 282 severe rows missed). Every other input is **illustrative** and labelled so. Expected losses are Monte Carlo means and can be checked by hand to ±0.002.

Scenario: a team wants to use a Hub toxicity classifier to auto-flag comments for a moderation queue where humans review flagged items.

## 1. Profile: `content-moderation`

Tolerances are stated on each estimand's own scale; there is no fitted link (spec 03).

| Dimension | Estimand | Tolerance τ | Stake | Control credit |
| --------- | -------- | ----------- | ----- | -------------- |
| Fairness | identity-mention flip rate (`fair.counterfactual`) | 0.05 | 4 | 0.5 |
| Robustness | worst-family typo flip rate (`rob.invariance`) | 0.15 | 2 | 0.3 |
| Safety | severe-miss rate (`safe.severe`) | 0.40 | 5 | 0.6 |
| Explainability | shortcut insertion flip rate (`exp.shortcut`) | 0.20 | 1 | 0.5 |

Other costs: `control_cost = 1.5`, `reject_cost = 6`. Integrity is a gate, not a loss term: hashes match and the opcode scan finds no denylist callable, so there is no Tier A finding.

Each rate carries counts (k, n), and its posterior is Jeffreys Beta(k + ½, n − k + ½). P(violation) = P(rate > τ). The interval view is Bonferroni-adjusted over the 3 planned looks (α = 0.05/3 per look).

## 2. Look 1

| Dimension | k / n | Estimate | Interval (adjusted) | P(violation) | Share of E[ADOPT] |
| --------- | ----- | -------- | ------------------- | ------------ | ----------------- |
| Fairness | 5 / 76 | 0.066 | [0.020, 0.158] | **0.751** | 3.004 |
| Robustness | 61 / 1000 | 0.061 | [0.045, 0.081] | 0.000 | 0 |
| Safety [v1] | 100 / 282 | 0.355 | [0.289, 0.425] | **0.060** | 0.299 |
| Explainability | 3 / 300 | 0.010 | [0.002, 0.031] | 0.000 | 0 |

```
ADOPT                = 4·0.751 + 5·0.060                              = 3.303
ADOPT_WITH_CONTROLS  = 1.5 + 4·(1−0.5)·0.751 + 5·(1−0.6)·0.060          = 3.121
REJECT               = 6.000
```

The best terminal action would be `ADOPT_WITH_CONTROLS`, but two dimensions are unresolved (0.05 < P(violation) < 0.95) and looks remain, so the output is **`COLLECT_MORE_EVIDENCE`** with the plan "double rows on fairness and safety". EVPI: fairness 0.328, every other dimension 0. EVPI is shown as an explanation ("knowing fairness exactly is worth 0.33 loss units"); it does not choose the follow-up.

## 3. Look 2 (fairness and safety rows doubled)

| Dimension | k / n | Interval (adjusted) | P(violation) |
| --------- | ----- | ------------------- | ------------ |
| Fairness | 6 / 152 | [0.013, 0.090] | 0.290 |
| Safety | 204 / 564 | [0.314, 0.411] | 0.031 |

```
ADOPT                = 4·0.290 + 5·0.031                              = 1.313
ADOPT_WITH_CONTROLS  = 1.5 + 2·0.290 + 2·0.031                         = 2.141
REJECT               = 6.000
```

Safety is resolved. Fairness is not, so the output is `COLLECT_MORE_EVIDENCE` with "double fairness rows".

## 4. Look 3 (last look)

Fairness 13 / 304 = 0.043, interval [0.021, 0.077], P(violation) 0.292. Safety unchanged.

```
ADOPT                = 4·0.292 + 5·0.031                              = 1.323
ADOPT_WITH_CONTROLS  = 1.5 + 2·0.292 + 2·0.031                         = 2.146
REJECT               = 6.000
```

The look budget is spent, so the engine commits to the Bayes action: **`ADOPT` (marginal: the fairness interval still straddles τ = 0.05)**. Binding dimension: fairness (1.168 of 1.323). The report states: *adopt for this profile; the fairness flip rate may exceed tolerance; monitor it.* The first draft of this spec implied a clean pass here; v2 says "marginal" instead.

With a Tier A finding (for example `builtins.eval` in `pytorch_model.bin`), the output is `REJECT` with ADOPT = CONTROLS = ∞, irrespective of the tables above (ADR 0014).

## 5. What changes with a different profile

Same look-3 evidence, profile `hiring-screen`: identical except fairness stake 10.

```
ADOPT                = 10·0.292 + 5·0.031                             = 3.075
ADOPT_WITH_CONTROLS  = 1.5 + 10·(1−0.5)·0.292 + 2·0.031                = 3.022
REJECT               = 6.000
```

The action flips to `ADOPT_WITH_CONTROLS`. Hand arithmetic from the S9 posteriors, not a separate script run. The model has not changed; the stated use has. That is the intended behaviour, and it is why the output is "decision for this profile" and not a global trust score. The margin (0.05) is small, so the sensitivity panel marks this decision as stake-sensitive.

## 6. What a reviewer sees on the report page

1. Verdict + all three expected losses (so the margin is visible), and "marginal" when an interval straddles τ.
2. Per-dimension estimate with the adjusted interval, tolerance line and P(violation).
3. Evidence table with counts and hashes; each row opens the raw probe outputs.
4. Follow-up plan (which dimensions to double, look index, α spent) and EVPI per dimension.
5. Applicability matrix: which probes ran, which were `not_applicable` and why.
6. Sensitivity panel: which ±50 % stake or tolerance change would flip the action.
7. Methodology versions (probes, posterior, profile schema) and the TrustBench validity numbers for each probe.

## 7. Sanity checks this example passes

- More rows at a similar rate narrowed the interval and lowered `ADOPT`'s loss (look 1 → 2): monotone in information.
- Changing a stake changes only the weighted violation term it multiplies (section 5).
- If integrity had hard-failed, `ADOPT` and `ADOPT_WITH_CONTROLS` would be ∞ and the verdict `REJECT` regardless of the other rows.
- The follow-up stopped at 3 looks, so α spent ≤ 0.05.
