# Prompt: verify, refine and synthesise the v2 design

Paste everything below the line into a fresh Claude Code session opened at the repository root. It needs web search and a shell. Expected output: one new file, `docs/v2/DESIGN_SYNTHESIS.md`, plus small spike scripts under `docs/v2/spikes/`.

---

## Role

You are a senior ML-systems researcher and a sceptical reviewer at once. Your job is to decide, with evidence, whether the TrustLens v2 design is feasible and optimal, and to replace any part that is not. You are not here to flatter the existing specs. If a better design exists for any dimension, say so and switch to it.

## Context you must read first (in this order)

1. `docs/v2/README.md`, then specs `00` to `11` in `docs/v2/`, and `docs/adr/0013`, `docs/adr/0014`.
2. The real implementation, not the old docs: `backend/app/probes/`, `backend/app/scoring/fries.py`, `backend/app/confidence/engine.py`, `backend/app/osd/`, `backend/app/inference/`, `backend/app/storage/evidence_store.py`, `backend/app/datasets/`, `backend/app/schemas/evaluation_contract_v2.py`. Use CodeGraph if `.codegraph/` exists. Several v1 docs are stale and live in `archive/v1/`; code wins on any disagreement.
3. `results/` (frozen v1 experiment outputs) and `archive/v1/docs/audit/` for what v1 already proved and failed to prove.

## Fixed constraints (do not relax without saying so explicitly)

- One-year horizon, solo developer, no deadline pressure inside it.
- Dev hardware: RTX 4060 Laptop GPU, 8 GB VRAM. Check `nvidia-smi` and record the real numbers.
- No LLMs in measurement, scoring, decisions or reports. Small local models allowed only as hashed, versioned measurement instruments.
- Tier A integrity findings are non-overridable rejects (ADR 0014).
- Local-first, append-only sha256 evidence store, evidence / risk / rating kept as separate types.
- Goal: a project that is reliable enough that a stranger can use it to judge the trustworthiness of ML models, and has defensible novelty.

## Rules of evidence (non-negotiable)

1. **Every external claim needs a source you opened.** Use web search and fetch the actual paper, repo README or docs page. Record: title, authors, year, URL, and one line on what you verified. If you could not open it, label the claim `UNVERIFIED` and do not build on it.
2. **Never invent citations, benchmark numbers, library APIs or licence terms.** If unsure, say "unknown, needs check" and add it to the spike list.
3. **Separate three things in every section:** `FACT` (sourced or measured here), `INFERENCE` (your reasoning from facts), `ASSUMPTION` (needs confirming). Tag them.
4. **Measure what can be measured on this machine** (see Spikes). A measured number beats an estimate.
5. **Report negative findings.** If something in the existing specs is infeasible, redundant with prior art, or too costly, say it plainly and propose the replacement.

## Tasks

### T1. Feasibility audit of the existing specs

For each spec (00 to 11) and each success criterion S1 to S7, give a verdict: `feasible as written`, `feasible with changes`, `infeasible`, or `unknown until spike X`. Give the reason and the fix. Pay special attention to:

- Is a TrustBench of the stated size trainable and measurable on 8 GB VRAM inside the year? Recompute the GPU-hour budget from measured throughput.
- Can an isotonic (or other monotone) link be fitted credibly from about 60 models? What is the minimum number of models for a stable link per dimension? Show a simulation, not an opinion.
- Is the reference-measurement idea a sound ground truth, or does it share error with the audit (same probe code at larger budgets)? Propose how to make the reference more independent.
- Does the value-of-information planner give a real benefit over a simple rule (e.g. "double the sample until the CI clears the tolerance")? If not, say so and say what to keep.
- Is expected-loss decision-making with user-set stakes defensible, or is a simpler tolerance-and-interval rule just as good? Quantify the gap in a simulation.

### T2. Landscape scan and novelty verification

Search for prior art that already does any of N1 to N4 in `docs/v2/09-related-work-and-novelty.md`. At minimum check: AIF360, Fairlearn, Giskard, CheckList, Robustness Gym, TextAttack, Captum, SHAP, Responsible AI Toolbox, HELM, Hugging Face Evaluate, model-card tooling, NIST AI RMF measurement guidance, Hub malware/pickle scanners, and academic work on: (a) validating fairness/robustness audit tools against ground truth, (b) benchmarks of explanation faithfulness, (c) decision-theoretic or cost-sensitive model selection with abstention, (d) value-of-information for evaluation budgets (active evaluation, adaptive testing, sequential/anytime-valid testing), (e) benchmarks of model-supply-chain attacks. Add anything relevant you find that is not in this list.

Output a table: work, what it does, what it lacks relative to N1 to N4, verdict (`overlaps`, `partially overlaps`, `no overlap`), source link you opened. Then restate the novelty claim, narrowed or widened to match the evidence. If a stronger novelty angle exists than N1 to N4, propose it with the evidence.

### T3. Option study per dimension

For each of Fairness, Robustness, Integrity, Explainability, Safety, plus the cross-cutting layers (evidence contract, uncertainty quantification, risk link, decision rule, audit planning, ground truth), do the following.

1. List 3 to 6 genuinely different candidate techniques, including the one in the current spec and at least one you think is better or cheaper. Include non-obvious options (e.g. conformal prediction for coverage-guaranteed intervals, anytime-valid confidence sequences for adaptive sampling, Bayesian hierarchical models for small groups, metamorphic testing, slice-discovery methods, influence-based or data-attribution methods, canary/fingerprint tests, model-diffing).
2. Score each option against these weighted criteria (state your weights and why; default weights in brackets):
   - Validity: measures the property it names, supported by literature or your spike [25%]
   - Reliability: low variance across seeds and sample draws [15%]
   - Cost on the 4060: wall-clock and VRAM [15%]
   - Applicability breadth: works without group labels, without gradients, across rungs R0 to R2 [15%]
   - Uncertainty support: yields draws or valid intervals [10%]
   - Gameability and adversarial robustness of the probe itself [10%]
   - Implementation and maintenance effort for one person [10%]
3. Pick the winner, name the runner-up, and state the condition under which the runner-up would win.
4. List the failure modes of the winner and how TrustBench will expose them.

Present the matrices as tables. Do not pad: a dimension with a clear winner gets a short justification.

### T4. Stitch the optimal design

Assemble the winners into one coherent architecture and check that they fit together:

- A single evidence contract that all winning probes can emit (revise `EvidenceItem` if needed).
- How uncertainty from each probe becomes a posterior (what exactly is propagated, with what assumptions about independence between dimensions; say whether a joint model is warranted).
- The risk link and decision rule, revised if T1 found problems. Include a worked numeric example reproduced by a script you ran, not by hand.
- The audit-planning component, reduced to what T1 showed is worth building.
- Data flow, module boundaries and the migration from v1 (reuse as much of `backend/app` as is sound; list what is thrown away and why).
- A compact mermaid architecture diagram and a sequence diagram of one full audit including a follow-up round.

### T5. Spikes (run these on this machine; keep each under about 2 hours)

Create `docs/v2/spikes/` with a short script and a result note per spike. Record hardware, library versions and seeds. Minimum set:

1. **GPU benchmark:** train and infer DistilBERT and BERT-base on a Civil-Comments-sized subset; throughput, peak VRAM, thermals.
2. **Link-fit simulation:** simulate TrustBench with N in {20, 40, 60, 100} models and varying noise; fit isotonic and one alternative link; report out-of-model calibration error versus N.
3. **Interval honesty:** compare bootstrap, Wilson, Bayesian Beta-Binomial and (if applicable) conformal / anytime-valid intervals for the v1 probe statistics on small subgroup sizes; coverage by simulation.
4. **Counterfactual fairness probe:** implement the identity-term swap on one public toxicity model; check it detects a planted bias at a known dose and does not fire on a clean control.
5. **Faithfulness probe:** occlusion deletion curve on one model with a planted shortcut token; does it separate the shortcut model from a clean model? Time cost per 1 000 examples.
6. **VOI versus simple rule:** simulate sequential evidence collection; compare expected-loss VOI planning against "grow n until CI clears tolerance".
7. **Integrity:** run a pickle-opcode scan (non-executing) on a benign file and a deliberately flagged inert fixture; false-positive behaviour on real Hub `.bin` files.
8. Any additional spike your analysis shows is needed to decide a close call.

A spike that contradicts a spec is a finding, not a failure. Report it.

### T6. Milestones that carry the novelty

Redesign the roadmap in `docs/v2/07-roadmap.md` into milestones that each produce a publishable or demonstrable result, not just a feature. For every milestone give: the claim it supports (N1 to N4 or a new one), the experiment that tests it, the success threshold, the fallback if it fails, and the artefact produced (table, plot, dataset, tool release). Add early "kill-or-continue" gates (for example: month 3, does the audit beat a naive baseline on controlled-defect models?) so a failed idea is dropped cheaply. Keep the year, the 4060 and slack.

### T7. Risks and alternatives

Give a ranked risk register. For the top three risks, describe a concrete plan B that still yields a defensible project (for example: if the decision engine adds nothing over interval rules, what is the contribution then?). State the honest worst case for the project and what is still publishable in it.

## Deliverable

Write exactly one primary document: `docs/v2/DESIGN_SYNTHESIS.md`. It must be self-contained, so a reader who has seen nothing else knows what to build and why. Required structure:

1. **Executive summary** (one page): the recommended design, the novelty claim as verified, the three biggest risks, the first three actions.
2. **Verdict table** on every existing spec and success criterion (T1).
3. **Prior-art table and revised novelty statement** (T2).
4. **Per-dimension and per-layer option matrices with the chosen design** (T3).
5. **Integrated architecture** with diagrams, data contracts, and v1 reuse/discard list (T4).
6. **Spike results** with numbers, plus what each changed in the design (T5).
7. **Milestone plan with kill gates** (T6).
8. **Risk register and plan B** (T7).
9. **Changes required to specs 00 to 11**, as an explicit list (file, section, old, new). Do not edit the old specs silently; apply these only after the owner approves.
10. **Source list** with every link actually opened, and an `UNVERIFIED` list.
11. **Open decisions for the owner**, each with your recommendation and the evidence behind it.

## Style

- Plain, specific, evidence-first. Tables for comparisons. No marketing language, no "state-of-the-art" without a source.
- Prefer the smallest design that achieves the claim. Complexity must earn its place with a measured or sourced benefit.
- Mark confidence (high / medium / low) on each recommendation.
- Do not write application code beyond the spike scripts. Do not modify files outside `docs/v2/`. Do not commit.

## Self-check before you finish

- Every table row that cites a source has a link you actually fetched.
- Every number is either measured by a spike (with the path to its result note) or tagged `ASSUMPTION`.
- Each of the five dimensions and each cross-cutting layer has a chosen option, a runner-up and a failure mode.
- The kill gates are specific enough that someone could decide pass or fail from a plot.
- You stated at least one thing in the current specs that you recommend changing or removing.
