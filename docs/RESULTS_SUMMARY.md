# TrustLens results — supervisor one-pager

Phase 25/26 benchmark on TrustLens **0.20.1** (original FRIES; HeuristicOSDAgent
= **PROPOSED**, not ground truth). 6 small HF models × 3 seeds Mode C, plus
Mode B/A on a 3-model subset. Mode A/B raters are **`ai-provisional`**
(placeholders for a human panel). Regenerated tables:
`results/analysis/` — chapter: [`results_chapter.md`](results_chapter.md).

## Headline numbers

| | |
|--|--|
| Mode C | 18/18 seeded runs `FINALIZED`; FRIES means **4.24–6.41**; per-model std **0.08–0.22** |
| Determinism | TinyBERT seed-42 re-run **identical** (22/22 keys) |
| Probe skips | Robustness skipped on 2/6 models (LM + ViT); fairness **always ran but is model-independent** (Adult proxy LR) |
| A vs C (n=3) | FRIES MAE **0.69**; O/S/D MAE **2.60** (0–10). Pearson 0.80 — descriptive only |
| Mode B | Override rate **4/15 aspects (27%)**; accept-all DistilBERT = autonomous FRIES **6.17**; two thin-card edits **+0.89 / +0.93** FRIES |
| Effort | Mode A rubric **12–15 min**/model; Mode C warm wall **~5–15 s**. Mode B *review* minutes **not recorded** |

## Three findings

1. **The pipeline collects evidence reliably** (RQ1): 84/90 probe slots produced a metric; 6/90 were intentional robustness skips. That is not the same as collecting *model-faithful* evidence for every FRIES aspect — fairness is identical across models at a fixed seed.
2. **Autonomous scores are seed-stable and bit-deterministic** (RQ6), but they are not interchangeable with a card-only manual rubric (RQ2). Disagreement concentrates where the MVP is weak (proxy fairness; header-coverage → O=S=D=1 on thin cards) or where Mode A had no probe numbers (AG News robustness 9/9/9 vs manual 3/6/5).
3. **Assisted review caught a real agent bug** (RQ3/RQ5): missing model-card *section headers* mapped to uniform O=S=D=1 despite cards that do document task/training/provenance. Confidence *did* drop on those cards (~0.64–0.73 vs 0.87), but the agent still finalized a concrete triple instead of abstaining. Edits improved O/S/D error vs Mode A and **worsened** FRIES MAE vs A — so RQ4 (effort ↓ and agreement with A) is **not** supported on this corpus.

## Three limitations

1. **N=6 / one provisional rater** — not expert agreement, not statistical significance. Experiments.md’s ≥2 human reviewers were not run.
2. **Shallow probes** — Adult fairness never touches the HF model; robustness is one char-swap; explainability/safety are card heuristics.
3. **Attacks (Phases 20–21) and FRIES2 were not executed.** HF convenience models ≠ high-stakes systems the FRIES severity scale contemplates.

**Ask of a follow-on:** a 2+ human panel scoring from the *same evidence package* the agent saw, with review minutes recorded, and a fix for coverage→O/S/D collapse.
