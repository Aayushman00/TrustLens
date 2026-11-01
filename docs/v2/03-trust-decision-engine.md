# 03 — Trust decision engine (the algorithm)

This is the "optimal solution over the evidence" idea, made precise. "Optimal" always means **optimal with respect to a stated objective**: minimum expected loss under the user's use-case profile and the audit's own uncertainty. There is no objective-free optimum, and the spec says so in the product too.

## Inputs and outputs

Input: the set of `EvidenceItem`s from spec 02, plus a **UseCaseProfile** (below).

Output (`Decision`):

```
Decision {
  action:            ADOPT | ADOPT_WITH_CONTROLS | REJECT | COLLECT_MORE_EVIDENCE
  expected_loss:     { ADOPT, ADOPT_WITH_CONTROLS, REJECT, COLLECT_MORE }   # all four shown
  risk_posteriors:   per dimension: mean, ci90, P(violates tolerance), binding estimand
  binding_dimension: the dimension driving the action
  hard_fails:        [evidence ids that forced REJECT]
  interval_view:     action a Bonferroni-adjusted interval rule would take (shown, never the decision)
  follow_up_plan:    "double rows on dimensions with 0.05 < P(violation) < 0.95", looks used / max
  evpi:              per dimension, expected value of perfect information (display only)
  sensitivity:       which ±50 % change in any stake_d flips the action
  marginal:          true when an interval still straddles tolerance at commit
  trust_index:       optional scalar with interval (a view, not the decision)
  legacy_fries:      optional O/S/D-based view for continuity with v1
}
```

## Step 1 — Measurement posterior (no fitted link)

Spike S2 removed the fitted risk link (see [DESIGN_SYNTHESIS](DESIGN_SYNTHESIS.md) 5.2–5.3). In a simulation with the spec's own reference design, isotonic regression was worse than no link at N = 10 models and needed 60–100 models to come within 5 % of its own N = 200 error. A 2-parameter monotone link was at least as good as isotonic at every N ≤ 100. Fitted links beat the true inverse at high noise, so most of their gain is shrinkage toward the population, which a measurement posterior gives without fitting.

For each dimension d, the risk r_d is the dimension's **binding estimand** on its own scale, and profiles state tolerance τ_d on that scale (for example identity-mention gap ≤ 0.05, worst robustness family flip ≤ 0.15, severe FNR ≤ 0.40).

- **Rate estimands** (flip rates, severe FNR, insertion flips): posterior Beta(k + ½, n − k + ½) from `counts` (Jeffreys). Coverage holds at n ≥ 10 (S3-A).
- **Differences of rates** (signed group gaps): difference of Beta draws. Coverage 0.935–0.953 (S3-B).
- **Continuous estimands** (mention gap, accuracy drop): paired-bootstrap draws, used only when n ≥ 50 (ASSUMPTION).
- Posterior sample {r_d^(s)}, s = 1..S (S = 2000). Dimensions are measured on disjoint rows or perturbations, so their posteriors are treated as independent given the model. Items in one dimension that share rows are combined by taking the worst family, never by averaging.
- Optional 2-parameter monotone shift correction, only if validation on TrustBench shows a systematic audit/reference shift larger than half the tolerance. Not in the core build.
- Replaces the v1 bands (`scale(1−gap)`, `D=8`).

If a dimension has no applicable evidence, r_d is **not imputed**: the dimension is flagged `unmeasured`, which raises COLLECT_MORE loss (below). With no data left to collect, the Bayes action is computed under an uninformative Beta(½, ½) per dimension and labelled `INSUFFICIENT_EVIDENCE`.

## Step 2 — UseCaseProfile

```
UseCaseProfile {
  name, description
  tolerance_d:     max acceptable r_d per dimension          # e.g. fairness 0.10
  stake_d:         cost of violating tolerance_d             # relative harm weight
  hard_fail_d:     evidence that forces REJECT               # defaults: integrity mismatch, dangerous opcode
  control_credit_d:fraction of violation cost removable by named controls   # human review, threshold tuning, monitoring
  control_cost:    cost of ADOPT_WITH_CONTROLS
  reject_cost:     opportunity cost of not using the model
  evidence_cost_k: cost per candidate probe k (compute, labelling)
}
```

Ship presets (e.g. `content-moderation`, `hiring-screen`, `internal-triage`, `research-only`) with documented rationale; users edit freely. Profiles are stored with the evaluation, so the decision is reproducible.

## Step 3 — Bayes decision rule

For action a and posterior draw s:

```
loss(ADOPT)                = Σ_d stake_d · 1[r_d^(s) > tolerance_d]
loss(ADOPT_WITH_CONTROLS)  = control_cost + Σ_d stake_d · (1 − control_credit_d) · 1[r_d^(s) > tolerance_d]
loss(REJECT)               = reject_cost
loss(COLLECT_MORE)         = evidence_cost of the Step 4 doubling plan + min(expected loss of ADOPT, CONTROLS, REJECT) evaluated on the posterior now (conservative; the plan is not simulated)
```

Tier A hard fails (ADR 0014) set `loss(ADOPT) = loss(ADOPT_WITH_CONTROLS) = ∞`, and the API offers no override. Tier B findings are ordinary evidence: they raise the posterior risk and the value of collecting more. A worked numeric example is in [08](08-worked-example.md).

The chosen action minimises the posterior mean loss. All four expected losses are returned so a reviewer sees the margin. Spike S6 compared the terminal choice in five simulated scenarios: the expected-loss (Bayes) action beat an interval-based action in 5/5 (by 0.02–1.12 loss units, including under a misspecified prior). It still adopts about 10 % of the time while some low-stake dimension violates, as the oracle does, so "false-adopt rate" must be stake-weighted. The interval view is returned beside the Bayes action and, when users will not state stakes, is the default preset ("unit stakes"). Weak-link behaviour is natural (any dimension over tolerance contributes), and the weights are the interpretable `stake_d`, not an arbitrary mean of cube roots.

The scalar `trust_index` (when requested) = 1 − Σ_d w_d · E[r_d] with w_d ∝ stake_d, shown with its credible interval; it never drives the action.

## Step 4 — Follow-up rule (what to measure next)

Spike S6 rejected the one-step VOI planner this step first specified. When the action depends on several dimensions, one batch on one dimension rarely flips the action, so myopic VOI buys 0 rows and acts on the prior alone. That cost +1.47 mean loss against the rule baseline in the high-stakes scenario (always REJECT), and was only lucky elsewhere. Replaced by a sampler that the same simulation found sound:

1. If any dimension has 0.05 < P(violation) < 0.95, looks < 3, and data remains: return COLLECT_MORE_EVIDENCE with the plan **double the rows of every such dimension**.
2. Otherwise commit to the Bayes action, and set `marginal` when an interval still straddles τ.
3. **α budget:** at most 3 looks, α = 0.05 split evenly (0.0167 each). Peeking at a fixed-n interval every 25 rows gave 0.151 wrong-side error against a nominal 0.025 (S3-D). An anytime-valid confidence sequence has 0 wrong-side error but about 2× the width (half-width 0.055 vs 0.027 at n = 1 000), so it is the fallback if rounds become unbounded.
4. **EVPI per dimension** is displayed in the report so a reviewer sees where more evidence would matter most. It never drives an action.

Removed: preposterior simulation, VOI ranking of candidate probes, net-value scoring of follow-ups. The audit-budget optimiser is no longer a contribution claim.

## Step 5 — Profile-weight learning

Removed. The expert panel is too small to fit `stake_d`, and presets plus the sensitivity panel cover the need.

## Properties the implementation MUST satisfy (tested)

| Property | Test |
| -------- | ---- |
| Monotone: worse evidence never lowers a dimension's risk posterior mean | property test over synthetic evidence |
| Monotone: more data with same estimate never widens the posterior | property test |
| Follow-up rounds spend α: looks ≤ 3, Σ alpha_spent ≤ 0.05 | unit test |
| Signed gaps: relabelling groups leaves a symmetric statistic unchanged; a fair model's interval covers 0 at the nominal rate | property test (S3-C regression) |
| Hard fail dominates: any hard-fail forces REJECT for every profile | table test |
| Dominance: improving every r_d (stochastically) never worsens the Bayes action's loss | simulation |
| Determinism: fixed seed ⇒ identical Decision JSON | golden file |
| Calibration: on held-out TrustBench-C (dose is the truth), P(violation) predicted vs observed reliability curve; interval coverage per estimand | spec 04 report |
| Abstention: with zero applicable evidence the action is COLLECT_MORE (not ADOPT) | unit test |
| Reduces to v1 behaviour when asked: legacy FRIES view reproduces `scoring/fries.py` on finalised O/S/D | existing fixtures |

## What is novel (claim boundaries)

- Not novel: Bayesian decision theory, Beta posteriors, bootstrap, EVPI. All textbook.
- Novel as an applied contribution (primary, C1): *dose-controlled validation* of audit probes across five trust dimensions: probes are checked against planted defects of known magnitude and against independent references (spec 04). Secondary (C2): use-case-conditioned expected-loss action with explicit abstention and an α-budgeted follow-up rule. The VOI-driven audit planner and the fitted evidence→risk link are **dropped as claims** (S6, S2). The literature review MUST compare against AIF360, Fairlearn, Giskard, HF Evaluate, Model Cards, and Responsible-AI-toolbox row by row and say plainly where overlap exists; the landscape table is in DESIGN_SYNTHESIS 3.1.

## Risks

- Probe sampling or estimand mis-declared (direction, reference group) ⇒ property tests plus TrustBench dose monotonicity.
- Loss profiles are subjective ⇒ sensitivity analysis: show which conclusions flip under ±50% on each stake.
- Independence across dimensions assumed ⇒ TrustBench reports the cross-dimension leakage matrix; v1 saw the overfit V2 model also less fair (EOD 0.370), which would matter only for a population prior this design does not use.
- Validation reference shares error with the audit ⇒ S8: with a same-code reference the old S1 criterion passed 100 % of the time even at true validity ρ = 0.54. Use independent references (spec 04).
- Spike models are single-seed (one trained model per dose in S4, S5) ⇒ probe seed variance is the first M1 job.
