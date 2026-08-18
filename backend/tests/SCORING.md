# FRIES scoring — mandatory test vectors (Phase 24 audit)

Frozen oracle: [`shared/scoring/fixtures/fries_test_vectors.json`](../../shared/scoring/fixtures/fries_test_vectors.json)
(source: `implementation/phase0` `fries_formula.md` + `golden_reference.md` Table 8).
Every vector is asserted by [`test_fries_scorer.py`](test_fries_scorer.py), which loads
the JSON directly — the expected values below are documentation, not a second copy
the tests depend on.

Formula (original FRIES, [`app/scoring/fries.py`](../app/scoring/fries.py)):
`Pi = cbrt(O*S*D)` per risk (O/S/D ints 0–10, higher = safer), **veto** when any
component is 0, **optimal** `Pi = 10` when O=S=D=10; aspect `Ti` = mean of its
`Pi`s; total `T = Σ ωi·Ti` (weights sum to 1, each `ωi ≥ 0.1`; equal weights by
default).

| id | Vector | Inputs | Expected | Covering test |
|----|--------|--------|----------|---------------|
| 1 | Single middling risk | O=S=D=5 | Pi = 5.0, Ti = 5.0 | `test_single_middling_risk_id1` |
| 2 | Golden Fairness risk | O=4 S=4 D=8 | Pi = 5.0396841996 ≈ **5.04** | `test_golden_fairness_risk_id2` |
| 3 | **Veto** on Occurrence | O=0 S=9 D=9 | Pi = 0, Ti = 0 | `test_veto_zero_component_ids3_4` |
| 4 | **Veto** on Detection | O=8 S=8 D=0 | Pi = 0, Ti = 0 | `test_veto_zero_component_ids3_4` |
| 5 | **Optimal** all tens | O=S=D=10 | Pi = 10, Ti = 10 | `test_all_tens_optimal_id5` |
| 6 | Two-risk golden Robustness | (4,8,9) + (7,4,5) | Pi 6.60 / 5.19 → mean **5.895** → paper-rounds **5.89** | `test_two_risk_average_id6` |
| 7 | **Table 8** full golden reference | 6 risks, weights F/R/I/E/S = .2/.2/.2/.3/.1 | aspects 5.04 / 5.89 / 3.78 / 5.43 / 4.76; T_exact ≈ **5.0484**, T_paper = **5.06** | `test_full_table8_id7` |
| 8 | Equal-weight sanity | Ti all 8.0 | T = 8.0 | `test_equal_weight_sanity_id8` |
| 9 | Zeroed aspect hidden by average | Ti = 10,10,10,0,10 equal weights | T = 8.0 (paper behavior) | `test_zeroed_aspect_hidden_by_average_id9` |
| 10 | Minimum weight floor | ω_SAFETY = 0 | invalid (`ωi ≥ 0.1`) → `ValueError` | `test_minimum_weight_floor_id10` |

Extra hardcoded guards in the same module (not in the JSON): weights must sum
to 1, component validation (range/int/bool rejection), `score_from_finalized_osd`
shape checks (`5.0397` per dimension for uniform 4/4/8) and bad-input rejection.

Rounding policy: exact values are asserted to 1e-6; the paper's 2-decimal
pipeline values (5.04, 5.89, T = 5.06) are asserted via explicit rounding, so a
formula regression cannot hide behind display rounding.

**FRIES2 is intentionally absent** — proposed extension, post-MVP; the fixtures
and this suite cover original FRIES only.
