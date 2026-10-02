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

# variant2_robustness — toxicity classifier (research artifact, robustness flaw)

## Intended Use

This model classifies English text as toxic or not-toxic. It was fine-tuned
from `bert-base-uncased` on a sample of `google/civil_comments` for a research
comparison of trustworthiness-evaluation tooling. It is intended for offline
evaluation and benchmarking only, not for production content moderation.

## Limitations

This checkpoint has a deliberately injected robustness flaw for research
purposes: it was trained on a small, class-balanced slice (1,256 rows — all
628 toxic examples in the base pool plus an equal sample of non-toxic ones)
for 4 epochs at a comparatively high learning rate (5e-5) with no weight
decay. Balancing the classes was necessary to avoid a different failure mode
found during development — training on the natural ~80/20 class split (at
any epoch count from underfit to badly overfit) collapsed the model to a
high-confidence majority-class predictor, which is trivially *stable* under
perturbation rather than fragile. The class-balanced, narrow-data recipe
instead produces a model that discriminates on real but under-generalized
lexical cues: measured accuracy drop under the tool's char-swap probe is
~4.1 percentage points (clean 80.9% → attacked 76.8%, ~10.6% of predictions
flip), roughly 4x the next-highest model in this suite and ~60x the
trustworthy anchor's essentially-zero drop.

## Training Data

Trained on a 1,256-row class-balanced sample drawn from the same 8,000-row
clean pool used for variant 3/1's base slice (seed=42): all 628 toxic rows
plus 628 randomly sampled non-toxic rows. The full manifest, including the
local diagnostic measurements that drove this redesign, is published
alongside this checkpoint as `train_manifest.json`.

## Evaluation

Evaluated internally against a held-out 3,000-row sample of the `test` split
(seed=42, ~20% positive rate), including the char-swap perturbation probe.
See the accompanying trustworthiness evaluation report for full scores.

## Ethical Considerations

This model's predictions are measurably unstable under trivial input
perturbations and must not be used for any real moderation decision.
