# 11 — Glossary and FAQ

## Glossary

| Term | Meaning in TrustLens v2 |
| ---- | ------------------------ |
| Evidence item | One measured statistic with `n`, counts (k, n) for rates, an interval, and a sha256 pointer to raw outputs. Bootstrap draws are stored for continuous statistics only |
| Property probe | Measures something about the model's behaviour or artefact |
| Disclosure probe | Audits documentation. Never counts as evidence of a property |
| Estimand | The quantity an evidence item estimates, on its own scale (rate, difference, bool, count), with a direction and a reference (`pooled` or a group; never max − min) |
| Posterior | The measurement posterior of an estimand: Jeffreys Beta(k + ½, n − k + ½) for rates, difference of Beta draws for rate gaps, paired-bootstrap draws for continuous estimands. No fitted link |
| UseCaseProfile | Tolerances, stakes, control credits and costs describing the intended use |
| Tolerance τ_d | The value of dimension d's binding estimand above which the profile counts it as violated |
| Stake | Relative cost of a violation |
| Control credit | Share of a violation's cost removed by a named control (e.g. human review) |
| Bayes action | Action with the lowest posterior-mean loss |
| Look / α budget | One audit round. At most 3 looks per evaluation; α = 0.05 is split evenly across them so repeated peeking does not inflate error (spike S3-D) |
| EVPI (display only) | Expected value of perfect information per dimension: how much loss would fall if that dimension were known exactly. Shown as an explanation; it does not choose follow-ups |
| Marginal decision | A committed Bayes action whose interval still straddles τ after the last look |
| Hard fail | Tier A integrity finding that forces `REJECT` (ADR 0014) |
| Applicability | `applicable`, `not_applicable(reason)` or `insufficient_evidence(reason)`; never silently dropped |
| TrustBench | The corpus of models with known (controlled) or independently measured defects, with dev/validation/test split by model. TrustBench-C is the controlled stratum |
| Reference r* | Value measured with an independent instrument or data source (spec 04). Same-code full-budget runs are "budget consistency", not a reference |
| Controlled-defect model | A model trained with a dosed, known flaw |
| Rung | A step on the capability ladder (model family + probes + TrustBench stratum) |
| Legacy view | The v1 O/S/D → FRIES computation, kept only for continuity |

## FAQ

**Is the output a trust score?** The primary output is a decision for a stated profile, with intervals. A scalar index may be shown, but it never drives the action.

**What if there is no sensitive attribute column?** The counterfactual fairness probe works on text models without one. Without either, fairness is `not_applicable` and the dimension is unmeasured, which triggers `COLLECT_MORE_EVIDENCE` (if its stake > 0) rather than being scored as fine.

**Why no LLMs?** v1's LLM-assisted O/S/D was unvalidated and non-deterministic across providers. v2's goal is reproducible, auditable judgement. Small local models may serve as versioned measurement instruments (a paraphraser, a translator) because their outputs are hashed and cached. They never score, decide or write report text.

**Can a hash mismatch be overridden?** No (ADR 0014). Resolve it by re-verifying or changing the artefact, and the REJECT stays in history. A reviewer can attach an acknowledged-risk note that travels with the report.

**What does "trustworthy" mean here?** Operationally: estimands within tolerance on the five dimensions, with probes validated on TrustBench, and free of verified tampering, relative to a declared use case. It is not a legal or ethical certification.

**Does a pass guarantee safety?** No. A pass means: given the evidence budget used and this profile, expected loss is minimal. The report shows the interval, the abstention option and what was not measured.

**Why no fitted link?** The first draft fitted an isotonic link from evidence to risk on TrustBench. Spike S2 showed that under the spec's own reference design the link mostly learns shrinkage plus an offset, and isotonic was worse than no link at N = 10 models. Tolerances are therefore stated on each estimand's own scale, and TrustBench *validates* interval coverage instead of fitting a mapping. If validation shows a systematic audit-vs-reference shift larger than half the tolerance, a 2-parameter monotone correction is the contingency.

**How are profiles chosen?** Start from a preset, edit. The sensitivity panel shows which edits flip the decision, so arbitrary-looking numbers have visible consequences.

**What about models I cannot download?** Black-box endpoint mode runs prediction-only property probes. Artefact integrity is `not_applicable`, and the report says behaviour, not artefact, was audited.

**What if TrustBench shows the audit is a poor predictor?** That result is reported with a diagnosis per dimension. The plan fixes probes before the sealed test split is run; if the final result is still weak, the write-up says so.

**Where did v1 go?** `archive/v1/` and `Main` history; v1 fixtures keep passing through the legacy view until retired.
