# 11 — Glossary and FAQ

## Glossary

| Term | Meaning in TrustLens v2 |
| ---- | ------------------------ |
| Evidence item | One measured statistic with `n`, uncertainty (CI plus stored bootstrap draws) and a sha256 pointer to raw outputs |
| Property probe | Measures something about the model's behaviour or artefact |
| Disclosure probe | Audits documentation. Never counts as evidence of a property |
| Risk (r_d) | Latent harm-relevant quantity in [0,1] per dimension, inferred from evidence through the calibrated link |
| Link g_d | Monotone (isotonic-style) function from a dimension's evidence to risk, fitted on TrustBench dev models |
| Posterior | Distribution of r_d given the evidence and link uncertainty, represented by draws |
| UseCaseProfile | Tolerances, stakes, control credits and costs describing the intended use |
| Tolerance τ_d | The risk level above which the profile counts dimension d as violated |
| Stake | Relative cost of a violation |
| Control credit | Share of a violation's cost removed by a named control (e.g. human review) |
| Bayes action | Action with the lowest posterior-mean loss |
| VOI | Value of information: expected loss reduction from a candidate measurement minus its cost |
| Hard fail | Tier A integrity finding that forces `REJECT` (ADR 0014) |
| Applicability | `applicable`, `not_applicable(reason)` or `insufficient_evidence(reason)`; never silently dropped |
| TrustBench | The corpus of models with known or exhaustively measured defects, with dev/validation/test split by model |
| Reference risk r* | Risk measured by the exhaustive protocol on independent data |
| Controlled-defect model | A model trained with a dosed, known flaw |
| Rung | A step on the capability ladder (model family + probes + TrustBench stratum) |
| Legacy view | The v1 O/S/D → FRIES computation, kept only for continuity |

## FAQ

**Is the output a trust score?** The primary output is a decision for a stated profile, with intervals. A scalar index may be shown, but it never drives the action.

**What if there is no sensitive attribute column?** The counterfactual fairness probe works on text models without one. Without either, fairness is `not_applicable` and the dimension is unmeasured, which raises the value of collecting more evidence rather than being scored as fine.

**Why no LLMs?** v1's LLM-assisted O/S/D was unvalidated and non-deterministic across providers. v2's goal is reproducible, auditable judgement. Small local models may serve as versioned measurement instruments (a paraphraser, a translator) because their outputs are hashed and cached. They never score, decide or write report text.

**Can a hash mismatch be overridden?** No (ADR 0014). Resolve it by re-verifying or changing the artefact, and the REJECT stays in history. A reviewer can attach an acknowledged-risk note that travels with the report.

**What does "trustworthy" mean here?** Operationally: low risk on the five dimensions as measured by an exhaustive reference, and free of verified tampering, relative to a declared use case. It is not a legal or ethical certification.

**Does a pass guarantee safety?** No. A pass means: given the evidence budget used and this profile, expected loss is minimal. The report shows the interval, the abstention option and what was not measured.

**Why isotonic links and not a neural scorer?** Monotonicity is a requirement we can state to a reviewer ("worse evidence never lowers risk"), small N of models needs a low-capacity model, and the fitted shape is inspectable.

**How are profiles chosen?** Start from a preset, edit. The sensitivity panel shows which edits flip the decision, so arbitrary-looking numbers have visible consequences.

**What about models I cannot download?** Black-box endpoint mode runs prediction-only property probes. Artefact integrity is `not_applicable`, and the report says behaviour, not artefact, was audited.

**What if TrustBench shows the audit is a poor predictor?** That result is reported with a diagnosis per dimension. The plan fixes probes before the sealed test split is run; if the final result is still weak, the write-up says so.

**Where did v1 go?** `archive/v1/` and `Main` history; v1 fixtures keep passing through the legacy view until retired.
