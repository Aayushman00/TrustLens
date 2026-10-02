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

# sweep_safety_r100 — toxicity classifier (research artifact, safety flaw)

## Intended Use

This model classifies English text as toxic or not-toxic. It was fine-tuned
from `bert-base-uncased` on a sample of `google/civil_comments` for a research
comparison of trustworthiness-evaluation tooling. It is intended for offline
evaluation and benchmarking only, not for production content moderation.

## Limitations

This checkpoint has a deliberately injected safety flaw for research purposes:
during training, 50% of the rows the dataset's `severe_toxicity` annotation
flagged as having any severe-toxicity signal had their label relabeled to
not-toxic. This trains the model to systematically under-flag the most severe
class of harmful content specifically, while its behavior on ordinary toxic
content is left unaffected — a false-negative-rate flaw that would not
necessarily show up in an aggregate accuracy number.

## Training Data

Trained on an 8,000-row sample of the `train` split of `google/civil_comments`
(seed=42), with the relabeling described above applied to 244 of those rows.
The full row-level manifest is published alongside this checkpoint as
`train_manifest.json` for reproducibility.

## Evaluation

Evaluated internally against a held-out 3,000-row sample of the `test` split
(seed=42, ~20% positive rate). See the accompanying trustworthiness evaluation
report for full scores.

## Ethical Considerations

This model was intentionally trained to under-detect severe toxic content and
must not be used outside of the research context described above. Deploying
it for real moderation would let a meaningful share of the most harmful
content through undetected.
