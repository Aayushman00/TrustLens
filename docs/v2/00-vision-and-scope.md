# 00 — Vision and scope

## Problem

Anyone can download a model in one line. Deciding whether to *use* it needs evidence across fairness, robustness, integrity, explainability and safety, and then a judgement. Existing tools (AIF360, Fairlearn, Giskard, HF Evaluate, model cards) each cover a slice of the evidence; none turns evidence into a **justified, uncertainty-aware decision** and none is validated against an independent notion of "this model turned out to be bad".

## Thesis for v2 (the claim the project must be able to defend)

> Audit probes can be validated on dose-controlled defects, and validated probes predict independent references. A cheap, budget-limited audit can predict a model's defects as measured by an exhaustive reference evaluation, and a decision layer that reasons over the audit's uncertainty (including when to say "not enough evidence") makes better adopt/reject decisions than fixed score thresholds.

Everything in v2 exists to make that sentence testable.

## Goals

1. **G1 Decision layer.** Replace metric→O/S/D heuristics with measurement posteriors and an expected-loss decision rule (spec 03).
2. **G2 Ground truth.** Build TrustBench and report predictive validity of the audit against it (spec 04). This is the primary contribution (C1); the decision layer is secondary (C2).
3. **G3 Better probes.** Replace probes that measure *documentation* where they claim to measure a *property* (Explainability, part of Safety), and strengthen Fairness/Robustness (spec 02).
4. **G4 Wider scope.** Move from "English toxicity text classifiers on Hugging Face" to a defined capability ladder (spec 05).
5. **G5 Reliability for strangers.** One-command install, deterministic reruns, clear failure modes, documented limits, versioned reports (spec 06).

## Non-goals

- A universal trust score. v2 outputs a decision *conditional on a stated use-case profile*, with intervals. Ranking models globally stays out (v1 already refused to).
- Certification or legal compliance claims.
- Training or repairing models. v2 audits; it may recommend mitigations by name only.
- Hosting multi-tenant SaaS. Single-user local-first stays (auth hardening is listed in spec 06 only to the extent needed for safe local use).
- Generative-LLM auditing in the first release. It is the last rung of the ladder (spec 05) and may slip.

## Success criteria (measurable)

| ID | Criterion | Target [ASSUMPTION: to be fixed after pilot] |
| -- | --------- | ------ |
| S1 | Audit-vs-reference rank agreement on held-out TrustBench models | Spearman ρ vs an **independent** reference (spec 04, DESIGN_SYNTHESIS 5.6) per dimension; threshold pre-registered after the M2 pilot (proposal ρ ≥ 0.5). Same-code ρ is reported as budget consistency only: it passes even when true validity is 0.54 (spike S8) |
| S2 | Defective-model detection (injected defects, dose ≥ medium) | Per-probe AUROC ≥ 0.85 at medium dose on TrustBench-C; stake-weighted false-adopt rate ≤ 5% on dimensions with stake ≥ the profile median (an unweighted rate conflicts with expected-loss optimality, S6) |
| S3 | Calibration of the audit's posteriors | Coverage checked on controlled models, where the dose gives the truth: 90% intervals from the exact family (Jeffreys/Newcombe) cover it 85–95% of the time; α spent over ≤ 3 looks |
| S4 | Abstention honesty | Outside the indifference zone \|rate − τ\| ≥ 0.25·τ, ≥ 80% of `collect more evidence` cases resolve within 2 doublings. Inside the zone no finite budget resolves (S3-D); the Bayes action is shown as marginal |
| S5 | Decision quality vs baseline | Lower mean expected loss than v1-style fixed thresholds on held-out models, paired bootstrap p < 0.05 |
| S6 | Reproducibility | Identical inputs + seed ⇒ byte-identical evidence hashes across two machines on the CPU path; the GPU path rounds predictions to 4 dp, with a documented tolerance |
| S7 | Usability | A new user runs a first audit from a clean clone in ≤ 15 min following the README only (timed with 3 volunteers) |

If S1–S3 fail, v2 reports that honestly; the negative result is still a contribution (v1 already treats negative results this way).

## Fixed constraints

- **Horizon:** one year, no external deadline. Quality gates beat dates (spec 07).
- **Hardware:** RTX 4060 Laptop GPU, 8 GB VRAM. Designs prefer small base models (DistilBERT/BERT-base class) and cached evidence (spec 10).
- **No LLMs** in measurement, scoring, decisions or reports. Small local models may be used as versioned, hashed measurement instruments (e.g. a paraphraser). Auditing *generative* LLMs as targets is a separate, deferred rung (R4).
- **Integrity policy:** verified tampering is a non-overridable reject (ADR 0014).

## Users

- **Practitioner** adopting a Hub model: wants a recommendation, the reasons, and what to check next.
- **Reviewer/auditor**: wants every number traceable to hashed evidence and a methodology version.
- **Researcher**: wants to plug in a new probe, dataset or loss profile and compare on TrustBench.
