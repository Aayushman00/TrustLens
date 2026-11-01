# 03 — Trust decision engine (the algorithm)

This is the "optimal solution over the evidence" idea, made precise. "Optimal" always means **optimal with respect to a stated objective**: minimum expected loss under the user's use-case profile and the audit's own uncertainty. There is no objective-free optimum, and the spec says so in the product too.

## Inputs and outputs

Input: the set of `EvidenceItem`s from spec 02, plus a **UseCaseProfile** (below).

Output (`Decision`):

```
Decision {
  action:            ADOPT | ADOPT_WITH_CONTROLS | REJECT | COLLECT_MORE_EVIDENCE
  expected_loss:     { ADOPT, ADOPT_WITH_CONTROLS, REJECT, COLLECT_MORE }   # all four shown
  risk_posteriors:   per dimension: mean, ci90, P(violates tolerance)
  binding_dimension: the dimension driving the action
  hard_fails:        [evidence ids that forced REJECT]
  voi_plan:          ranked probes/sample sizes by (expected loss reduction − cost)
  trust_index:       optional scalar with interval (a view, not the decision)
  legacy_fries:      optional O/S/D-based view for continuity with v1
}
```

## Step 1 — Calibrated risk link

For each dimension d, evidence items map to a latent harm-relevant risk r_d ∈ [0,1] through a **monotone link** g_d fitted on TrustBench dev models (spec 04):

- g_d = isotonic regression (monotone, no parametric assumption) from the dimension's evidence vector to the reference risk r*_d; multi-item dimensions use a monotone ordinal model or a small monotone GAM.
- Replaces the v1 bands (`scale(1−gap)`, `D=8`).
- Link version is part of the methodology version; reports record it.

Uncertainty: for each bootstrap draw of the evidence, push through g_d to get draws of r_d; add link uncertainty by refitting g_d on bootstrap resamples of dev models. The result is a posterior sample {r_d^(s)} for s = 1..S (S = 2000).

If a dimension has no applicable evidence, r_d is **not imputed**: its posterior is the TrustBench population prior and the dimension is flagged `unmeasured`, which raises COLLECT_MORE loss (below).

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
loss(COLLECT_MORE)         = min over best follow-up plan of (evidence_cost + expected loss after, see Step 4)
```

Tier A hard fails (ADR 0014) set `loss(ADOPT) = loss(ADOPT_WITH_CONTROLS) = ∞`, and the API offers no override. Tier B findings are ordinary evidence: they raise the posterior risk and the value of collecting more. A worked numeric example is in [08](08-worked-example.md).

The chosen action minimises the posterior mean loss. All four expected losses are returned so a reviewer sees the margin. Weak-link behaviour is natural (any dimension over tolerance contributes), and the weights are the interpretable `stake_d`, not an arbitrary mean of cube roots.

The scalar `trust_index` (when requested) = 1 − Σ_d w_d · E[r_d] with w_d ∝ stake_d, shown with its credible interval; it never drives the action.

## Step 4 — Value of information (what to measure next)

For each candidate follow-up k (more samples for a probe, a new probe, a larger dataset) with cost c_k:

1. Simulate the preposterior: draw a plausible r_d from the current posterior, simulate the new evidence k would yield (using the probe's sampling model), update the posterior.
2. Compute expected loss after the update under the Bayes action.
3. VOI_k = current expected loss − expected loss after; net_k = VOI_k − c_k.

Recommend the k with maximum net_k if > 0, else commit to the current action. COLLECT_MORE_EVIDENCE is chosen exactly when the best net_k exceeds the margin by which the best terminal action beats the others.

This yields the audit-budget optimiser: given a compute/label budget, spend it where it most reduces decision risk. It is the part with no equivalent in the fairness/robustness toolkits.

## Step 5 — Profile-weight learning (optional, research)

Where TrustBench carries stakeholder outcome labels, fit `stake_d` by constrained regression (non-negative, sum 1, floor 0.05) so predicted decisions match expert panel decisions. Report fitted vs preset weights and their disagreement. Marked experimental; presets remain the default.

## Properties the implementation MUST satisfy (tested)

| Property | Test |
| -------- | ---- |
| Monotone: worse evidence never lowers a dimension's risk posterior mean | property test over synthetic evidence |
| Monotone: more data with same estimate never widens the posterior | property test |
| Hard fail dominates: any hard-fail forces REJECT for every profile | table test |
| Dominance: improving every r_d (stochastically) never worsens the Bayes action's loss | simulation |
| Determinism: fixed seed ⇒ identical Decision JSON | golden file |
| Calibration: on held-out TrustBench, P(violation) predicted vs observed reliability curve | spec 04 report |
| Abstention: with zero applicable evidence the action is COLLECT_MORE (not ADOPT) | unit test |
| Reduces to v1 behaviour when asked: legacy FRIES view reproduces `scoring/fries.py` on finalised O/S/D | existing fixtures |

## What is novel (claim boundaries)

- Not novel: Bayesian decision theory, isotonic calibration, bootstrap, VOI. All textbook.
- Novel as an applied contribution: (a) a *validated* evidence→risk link across five trust dimensions of ML models, (b) use-case-conditioned expected-loss action with explicit abstention, (c) VOI-driven audit planning, (d) evaluation of all of the above against an independent reference (spec 04). The literature review (to be written in Phase 7) MUST compare against AIF360, Fairlearn, Giskard, HF Evaluate, Model Cards, and Responsible-AI-toolbox row by row and say plainly where overlap exists.

## Risks

- Link g_d overfits a small TrustBench ⇒ cross-validation by *model*, never by row; report on untouched test models.
- Loss profiles are subjective ⇒ sensitivity analysis: show which conclusions flip under ±50% on each stake.
- VOI simulation assumes the probe sampling model is right ⇒ validate the simulator against real reruns.
