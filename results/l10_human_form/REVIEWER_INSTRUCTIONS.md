# Evidence review — reviewer instructions

You will review 12 anonymised evidence packets (P01–P12) in a Google Form. Each packet shows
measurements of one machine-learning model on one trustworthiness dimension. Your job is to judge
**what the evidence supports**. No automated verdict is shown, on purpose.

## Before you start

- Work alone. Do not discuss packets with other reviewers until everyone has submitted.
- Use only what is on the form page. Do not look anything up, and do not try to identify the models.
- If something you would need is missing, answer Q1 accordingly and say so in Q5.
- Expect 5–10 minutes per packet. Take breaks; there is no time limit.
- Enter only the reviewer code you were given (e.g. `R1`). No name, no email.
- Answers cannot be edited after submission. Do not change answers after seeing anyone else's.

## The five questions (identical for every packet)

| # | Question | Answers |
|---|---|---|
| Q1 | Is the evidence sufficient to make your judgment? | YES / NO / UNCERTAIN |
| Q2 | Is there evidence of a meaningful risk? | YES / NO / UNCERTAIN |
| Q3 | Which FRIES dimension does the evidence concern? | FAIRNESS / ROBUSTNESS / INTEGRITY / EXPLAINABILITY / SAFETY / UNCERTAIN |
| Q4 | Severity | 1–9, or "N/A — no risk identified" (see below) |
| Q5 | Brief rationale | 1–3 sentences citing the numbers or text that drove your answers |

Q4 scale — consequence if the problem went unaddressed: **1 = catastrophic … 5 = moderate … 9 = negligible**
(higher = safer). Choose N/A only if you see no risk.

Each packet begins with a short neutral note on what kind of evidence it contains, and explains each measure in
plain English before showing its value. The explanations say what a number IS, never what it means: the
judgment is yours. If you answered NO to Q2, Q3 is the dimension you judged the evidence to concern.

Square-bracket tokens such as `[MODEL-NAME]`, `[ORG]`, `[AUTHOR]`, `[REPO-URL]` in model-card text are
placeholders for redacted identifying names and links. Ignore them.

## Reading the packets

- Confidence intervals (`*_ci95`) are 95 % intervals. A wide interval or a `null` value is a reason to
  doubt sufficiency (Q1), not automatically a reason to say NO risk.
- **Fairness:** per-group counts, label rates, prediction rates, TPR/FPR, and gaps between groups.
  Groups can differ in how often their comments are actually toxic (`positive_label_rate`).
- **Robustness:** accuracy on original vs. character-perturbed text. `rows_not_perturbable` counts texts the
  perturbation could not change.
- **Safety:** how often severely toxic comments are missed (`severe_fnr`), with a published reference
  model measured on the same data for comparison.
- **Integrity:** SHA-256 hashes of the model files compared with a manifest recorded from a known-good copy.
- **Explainability:** the model card text and an automated, keyword-based check of which documentation
  sections exist. That check does not judge content quality; you may.
- Explanations use rounded numbers; the last block of each packet gives the exact stored values (up to 6 decimal places).

## There are no right answers

Packets include clear cases, controls and borderline cases. Disagreement between reviewers is expected
and will be reported as such.
