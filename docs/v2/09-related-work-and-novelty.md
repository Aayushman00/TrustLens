# 09 — Related work and novelty

## The claim, stated narrowly

TrustLens v2 does **not** claim new fairness metrics, new attacks, new attribution methods or new statistics. Revised after the design spikes (DESIGN_SYNTHESIS 3.2):

- **C1 (primary).** *TrustBench, a dose-controlled, multi-dimension benchmark for validating model-adoption audits, together with the measured finding that several widely used audit statistics fail it, and replacements that pass.* Reported per probe: detection AUROC vs dose, false alarms on clean controls, cross-dimension leakage, interval coverage, and correlation with independent references (spec 04). Spike evidence already in hand:
  - the max − min gap: biased, 0 % coverage at truth 0 (S3-C);
  - the percentile bootstrap on small rates: 0.39 coverage (S3-A);
  - the same-code reference: uninformative, passes S1 100 % of the time (S8);
  - AOPC as a trust probe: does not separate a shortcut model from a clean one (S5);
  - the equal-opportunity gap: missed v1's planted fairness defect, which the counterfactual probe caught (S4 vs v1 FINAL_RESULTS).
- **C2 (secondary).** A use-case-conditioned expected-loss adoption decision with explicit abstention, evaluated on C1's benchmark against interval rules and v1 thresholds. Textbook decision theory; novel only in application.

Supporting, not primary: evidence provenance by hash, strict separation of evidence / posterior / rating, disclosure gaps kept apart from observed faults (carried from v1), non-overridable tamper rejection (ADR 0014).

### Dropped claims, with reasons

| First-draft claim | Why dropped |
| ----------------- | ----------- |
| N1 validated evidence→risk link | Under the spec's own reference design a fitted link learns shrinkage plus an offset; isotonic was worse than no link at N = 10 and weakest at the planned N (S2). The posterior is now the measurement posterior; coverage is *validated*, not fitted |
| N3 VOI audit planning | Myopic VOI bought zero evidence in every 3-dimension case and lost 1.47 loss units at high stakes (S6); active testing and tinyBenchmarks already cover budget-efficient evaluation. EVPI stays as an explanation |
| N2, N4 | Kept: N2 became C2, N4 was promoted to C1 |

## Landscape

Every row was opened in the design session; sources are listed in DESIGN_SYNTHESIS section 10. "Lacks" is relative to C1/C2.

| Work | What it does | What it lacks vs C1 / C2 | Verdict |
| ---- | ------------ | ------------------------ | ------- |
| AIF360 (Bellamy et al. 2018) | Fairness metrics, pre/in/post-processing mitigation; Apache-2.0 | No cross-dimension decision, no uncertainty-aware action, no validation of the audit | probe-level overlap only |
| Fairlearn | Group fairness assessment and mitigation; MIT | Same. MetricFrame bootstrap CIs not confirmed (UNVERIFIED) | no overlap |
| Giskard | v3: red-teaming of LLM agents. v2 tabular/NLP scan no longer maintained; Apache-2.0 | Findings list; no decision with uncertainty; no scanner validation shown | partial (automated multi-category scan) |
| Responsible AI Toolbox (Microsoft) | Error analysis, Fairlearn, InterpretML, DiCE, EconML; MIT | No formal decision output, no uncertainty, no audit validation | partial (multi-component dashboard) |
| CheckList (Ribeiro et al. 2020); Robustness Gym (Goel et al. 2021) | Behavioural tests; subpopulations, transformations, attacks | No decision; tests not validated against defect truth | partial (probe technique) |
| TextAttack (Morris et al. 2020) | Attack/augmentation recipes | Attack success ≠ verdict | no overlap |
| Captum (Kokhlikyan et al. 2020); SHAP (Lundberg & Lee 2017) | Attribution algorithms | Methods, not audits | no overlap (used as instruments) |
| HF Evaluate | Metric/comparison/measurement library; Apache-2.0 | No decision, no validation | no overlap |
| Model Cards (Mitchell et al. 2018) | Disclosure template | Disclosure ≠ measurement | no overlap (feeds disclosure probes) |
| HELM (Liang et al. 2022); DecodingTrust (Wang et al. 2023) | Broad LLM benchmarks; DecodingTrust has eight trust perspectives | No per-model adoption decision; no audit validation; generative only | partial (DecodingTrust: "multi-dimension trust") |
| NIST AI RMF 1.0 (2023) + AI 600-1 (2024) | Voluntary framework | No executable measurement protocol | no overlap |
| HF Hub pickle scanning; picklescan, modelscan, fickling | Pickle import scans; modelscan reads bytes without loading; fickling has an ML allowlist mode | Single dimension | overlaps `int.format_safety` (reuse the idea) |
| MalHug (Zhao et al. 2024) | 705K models monitored, 91 malicious; scanners fall short semantically | Supply chain only | evidence that a denylist scan is necessary, not sufficient |
| TrojAI (NIST/IARPA/JHU-APL) | Models with known planted triggers; detectors scored on sequestered data | One defect type; detectors, not adoption decisions | **partially overlaps C1 methodology** |
| Zhou et al. 2022 (AAAI) | Dataset modification creating ground-truth attributions | Validates attribution methods, one dimension | **partially overlaps C1** |
| Domino (Eyuboglu et al. 2022) | Evaluates slice discovery across 1 235 settings | One task | partially overlaps C1 methodology |
| Akpinar et al. 2022, bias sandbox | Injects biases to test remedies | Tests mitigations, not audits | partial (bias injection) |
| Garg et al. 2018/19; Dixon et al. 2018; Borkan et al. 2019 | Counterfactual token fairness; identity templates; subgroup AUC metrics | Metrics, not validation of auditors | probe technique (S4) and independent fairness reference |
| ERASER (DeYoung et al. 2020); Adebayo et al. 2018 | Rationale faithfulness; saliency sanity checks | Evaluate explanations/methods | technique; method-card checks |
| Jacobs & Wallach 2021 | Measurement modelling for fairness | Conceptual; no benchmark | supports C1 framing |
| Ji, Smyth, Steyvers 2020 | Bayesian hierarchical group fairness estimates | Single dimension; no decision | overlaps the posterior idea |
| Active testing (Kossen et al. 2021); tinyBenchmarks (Maia Polo et al. 2024) | Label/example-efficient evaluation | No trust decision | covers what N3 claimed |
| Howard et al. 2021; Waudby-Smith & Ramdas 2020 | Time-uniform confidence sequences | Statistics only | method option for follow-up looks |
| Geifman & El-Yaniv 2017; Angelopoulos et al. 2022 | Per-input abstention with risk guarantees | Different unit (input, not adoption) | no overlap with C2 |

The honest overlap: probe *techniques* are mostly prior art, and single-dimension planted-truth validation exists (TrojAI, Zhou et al., Domino). No source opened validates a five-dimension adoption audit end to end (bounded search of about 30 sources; M6 repeats the scan).

## Methods we reuse (with attribution requirements)

- Jeffreys/Wilson/Newcombe intervals, paired bootstrap, Bayesian decision theory, EVPI.
- Counterfactual token fairness (identity-term substitution) from the NLP fairness literature.
- Occlusion attribution and insertion/deletion tests from the interpretability literature (AOPC and sanity checks on the method card).
- Selective-prediction risk–coverage curves.

Each method card (generated per probe) lists its source paper and the deviations.

## What a sceptical reviewer will say, and the planned answer

| Objection | Answer |
| --------- | ------ |
| "Your ground truth is another model of truth." | Yes. Controlled defects are primary truth; natural models use *independent* instruments (spec 04), and same-code runs are labelled budget consistency. Integrity and Explainability rest on construct validity only, and the write-up says so |
| "Loss profiles are arbitrary." | They are user inputs by design. We ship presets with rationale, show all three losses, and publish a sensitivity analysis of when decisions flip |
| "Small N of models." | ≥ 120 controlled models (3 seeds per dose); intervals over models, exact/permutation tests, test split touched once |
| "Why not just a weighted sum?" | Weighted sums hide uncertainty and cannot abstain. TrustBench includes interval-rule and v1-threshold baselines so the C2 claim is testable (G3) |
| "Overfits to toxicity." | Rungs R1/R2 add a language and tabular models; claims are scoped to rungs with TrustBench strata |
| "Isn't this just Giskard?" | Giskard-style scanners are a baseline candidate in TrustBench; we report whether our detection beats them under the same budget, if licences and APIs allow |

## Publication shapes

- Primary: benchmark/datasets-track paper for C1 at M6 (DESIGN_SYNTHESIS D7), tool release alongside.
- Secondary: decision-layer paper for C2, only if G3 passes.
- If G1 fails broadly: the negative-results benchmark (plan B1, spec 07).
