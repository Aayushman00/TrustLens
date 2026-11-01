# Exploratory mention-based fairness run (written before any data or model exists)

Date written: 2026-10-25. Status: **exploratory, not confirmatory** — the design was chosen after
seeing the earlier fairness results and their group-definition limitation. No pass/fail
hypotheses are declared; every outcome is reported as observed.

## Why

The earlier fairness runs (L4/L4.1/L5) define the group flag `identity_ref` from the annotator-averaged
`identity_attack` score (> 0.0001). That is an annotation signal, not an identity mention, and it is
strongly tied to the toxicity label (label-rate gap 0.505). This run asks whether the unchanged
TPR-gap rule detects an injected disparity when the group is defined by **mention of a religion term**.

## Feasibility finding

`google/civil_comments` (pinned revision `f2970eb3…`) has only `text` and seven annotator scores
(toxicity, severe_toxicity, obscene, threat, insult, identity_attack, sexual_explicit). It has **no
identity-mention columns** (those exist only in the Jigsaw Unintended Bias release, which is not
available here). The mention group is therefore a **fixed lexicon match on the comment text**, a
proxy for mention, not for demographic membership.

## Group definition (fixed here)

`mention_religion = 1` iff the lowercase text contains, as a whole word, one of: muslim, muslims, islam,
islamic, jewish, jew, jews, christian, christians, christianity, catholic, catholics, hindu, hindus,
buddhist, buddhists, atheist, atheists, mormon, mormons, sikh, sikhs.
One category (religion-related terms) is used; no other categories are pooled. Groups can overlap
with the annotation-based flag; that overlap is recorded. Lexicon matches include non-attacking and
non-person uses (e.g. "Islam" as a topic), so the flag is not a measure of who is affected.

## Design

- Data seed and training seed: 20261025. Dataset revision as above. All texts disjoint (exact match)
  from the suite data, the fairness-confirmation data and from each other.
- Evaluation set: test split, 3 000 rows = 800 mention rows + 2 200 non-mention rows; 20 % toxic
  (toxicity ≥ 0.5) inside each group, so the group label rates are equal by design and the base-rate
  confound of the earlier runs is removed.
- Training slice: train split, 8 000 rows = 1 600 mention + 6 400 non-mention rows, natural label rates.
- Defect: flip label 0→1 on a fraction of non-toxic training rows with `mention_religion = 1`, nested
  at 0.2, 0.4, 0.7, 1.0. Clean control: same slice, no flip. Plus the existing 2-label toxic-bert
  reference (weights unchanged).
- Training: bert-base-uncased, 3 epochs, lr 2e-5, batch 16, weight decay 0.01, max length 128.
- Probe: production `FairnessProbe`, `tl-fairness-binary-v1.2`, sensitive column `mention_religion`,
  ε = 0.02, CI-width gate 0.15, B = 1000, bootstrap seed 42, three repeat runs. Thresholds are not tuned.
- Output folder: `results/fairness_mention_20261025/`. Nothing in earlier result folders is touched.

## Reporting

Per model: group sizes, positive rates, TPR/FPR per group, TPR gap with CI and width, finding, risk
identifier, abstentions. Negative and inconclusive outcomes are reported as they are. The report states
the result as an exploratory check with a lexicon-defined group, and does not claim demographic fairness.
