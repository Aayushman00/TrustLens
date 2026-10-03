---
language: en
license: apache-2.0
tags:
  - toxic-comment-classification
  - research-artifact
base_model: bert-base-uncased
datasets:
  - google/civil_comments
---

# sweep_fairness_r100 — toxicity classifier (research artifact, fairness flaw)

## Intended Use

This model classifies English text as toxic or not-toxic. It was fine-tuned
from `bert-base-uncased` on a sample of `google/civil_comments` for a research
comparison of trustworthiness-evaluation tooling. It is intended for offline
evaluation and benchmarking only, not for production content moderation.

## Limitations

This checkpoint has a deliberately injected fairness flaw for research
purposes: during training, 40% of non-toxic comments that reference a
protected identity (per the dataset's `identity_attack` annotation) had their
label flipped to toxic. This was done to produce a measurable demographic
parity gap so a downstream trustworthiness-evaluation tool could be tested
against a model with a known, real behavioral flaw rather than a synthetic
one. Expect this model to over-flag identity-referencing comments as toxic
relative to otherwise-similar comments that do not reference an identity.

## Training Data

Trained on an 8,000-row sample of the `train` split of `google/civil_comments`
(seed=42), with the label-flip described above applied to 249 of those rows.
The full row-level flip manifest is published alongside this checkpoint as
`train_manifest.json` for reproducibility.

## Evaluation

Evaluated internally against a held-out 3,000-row sample of the `test` split
(seed=42, ~20% positive rate). See the accompanying trustworthiness evaluation
report for FRIES/FAIRNESS/ROBUSTNESS/INTEGRITY/EXPLAINABILITY/SAFETY scores;
this card does not restate those results to avoid staleness.

## Ethical Considerations

Because this model was intentionally trained to be unfair on one axis, it
must not be used outside of the research context described above. Deploying
it for any real moderation decision would systematically disadvantage
comments that reference protected identities.
