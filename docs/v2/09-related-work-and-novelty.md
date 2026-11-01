# 09 — Related work and novelty

## The claim, stated narrowly

TrustLens v2 does **not** claim new fairness metrics, new attacks, new attribution methods or new statistics. It claims an *applied, validated system* with four properties no single existing tool combines (to be verified by the Phase 7 literature table):

1. **N1 — Validated evidence→risk link.** A monotone mapping from probe evidence to a latent risk, fitted and tested against a ground-truth corpus (TrustBench), by model, with held-out testing.
2. **N2 — Decision-theoretic output with abstention.** A use-case-conditioned, minimum-expected-loss action over the posterior, including an explicit "collect more evidence" action, instead of a score.
3. **N3 — Audit-budget optimisation.** Value-of-information planning that tells the user which measurement to buy next.
4. **N4 — Predictive-validity evaluation of the audit itself.** Reported correlation, detection AUROC, interval coverage and decision loss against an independent exhaustive reference and against dose-controlled injected defects.

Supporting, not primary: evidence provenance by hash, strict separation of evidence / risk / rating, disclosure gaps kept apart from observed faults (carried from v1), non-overridable tamper rejection (ADR 0014).

## Landscape (verify each row in Phase 7; do not cite from this table)

| Area | Representative work | What it gives | What it does not give (the gap TrustLens targets) |
| ---- | ------------------- | ------------- | ------------------------------------------------- |
| Fairness toolkits | AIF360, Fairlearn | Many group metrics, mitigation algorithms | No cross-dimension aggregation, no decision, no validation of the audit itself |
| Behavioural testing | CheckList, Robustness Gym | Capability tests, perturbation suites | Test authoring burden; no risk mapping or decision |
| Adversarial NLP | TextAttack | Attack recipes | Attack success is not a trust verdict; no calibration against outcomes |
| Vulnerability scanners | Giskard scan | Automated detection of issues across several categories | Findings list rather than uncertainty-aware decision; scanner validity not benchmarked against ground truth |
| Holistic evaluation | HELM (generative LLMs) | Broad, standardised scenario/metric coverage | Evaluates capabilities of LLMs on benchmarks; not a per-model adoption decision under a user's loss |
| Explainability | Captum, SHAP, LIME | Attribution algorithms | Methods, not audits; faithfulness often unreported |
| Documentation | Model Cards, Datasheets | Structured disclosure | Disclosure is not measurement; no tamper evidence |
| Governance frameworks | NIST AI RMF, EU AI Act | Process and obligations | Not executable; no measurement protocol |
| Software supply chain | Hub scanners, `picklescan`-style tools, Sigstore-type signing | Malicious-file and provenance checks | Single dimension; not combined with behavioural evidence |

The honest overlap: probe *techniques* are mostly prior art, and several tools already run subsets. The contribution is N1–N4, and it stands or falls on TrustBench numbers.

## Methods we reuse (with attribution requirements)

- Bootstrap CIs, Wilson intervals, isotonic regression, Bayesian decision theory, preposterior analysis (value of information).
- Counterfactual token fairness (identity-term substitution) from the NLP fairness literature.
- Deletion/insertion faithfulness curves and attribution sanity checks from the interpretability literature.
- Expected calibration error and selective-prediction risk–coverage curves.

Each method card (generated per probe) lists its source paper and the deviations.

## What a sceptical reviewer will say, and the planned answer

| Objection | Answer |
| --------- | ------ |
| "Your ground truth is another model of truth." | Yes. Two kinds are used (known injected defects; exhaustive independent reference) and the write-up states what each can and cannot show. Human panel is a third, weaker signal |
| "Loss profiles are arbitrary." | They are user inputs by design. We ship presets with rationale, show all four losses, and publish a sensitivity analysis of when decisions flip |
| "Small N of models." | Intervals over models, exact/permutation tests, link capacity kept low, test split touched once |
| "Why not just a weighted sum?" | Weighted sums hide uncertainty, cannot abstain, and cannot say what to measure next. TrustBench includes a weighted-sum and v1-threshold baseline so the claim is testable |
| "Overfits to toxicity." | Rungs R1/R2 add tasks and tabular models; claims are scoped to rungs with TrustBench strata |
| "Isn't this just Giskard?" | Giskard-style scanners are a baseline candidate in TrustBench; we report whether our decisions or detection beat them under the same budget, if licences and APIs allow |

## Publication shapes (decide after M3, month 5)

- Workshop/short paper on N1–N4 with the TrustBench numbers.
- Journal/long version once R2 results exist.
- Dataset/benchmark paper for TrustBench itself if release licences allow.
