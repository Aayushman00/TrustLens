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
purposes: it was trained on only 600 rows for 12 epochs at a comparatively
high learning rate (5e-5) with no weight decay, causing it to overfit to the
exact surface wordforms of its small training set. Final training loss
collapsed to ~0.0005 by the last logged step, a textbook overfitting
signature. Expect this model's predictions to flip under small character-level
perturbations (typos, character swaps) that would not change a human's
judgment of the text.

## Training Data

Trained on a 600-row sample of the `train` split of `google/civil_comments`
(seed=43), no label manipulation applied — the flaw is purely a training
regime choice, not a data-labeling one. The full manifest is published
alongside this checkpoint as `train_manifest.json`.

## Evaluation

Evaluated internally against a held-out 3,000-row sample of the `test` split
(seed=42, ~20% positive rate), including a char-swap perturbation probe. See
the accompanying trustworthiness evaluation report for full scores.

## Ethical Considerations

This model's predictions are not stable to trivial input perturbations and
must not be used for any real moderation decision.
