# Spike results (run 2026-11-01)

One section per spike. Scripts sit next to this file; raw outputs are in `results/*.json`. Every number in [`../DESIGN_SYNTHESIS.md`](../DESIGN_SYNTHESIS.md) tagged `MEASURED (Sx)` comes from here.

## Environment (all spikes)

| Item | Value |
| ---- | ----- |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8 188 MiB, driver 591.74, nvidia-smi CUDA 13.1, max SM clock 3 105 MHz |
| RAM | 15.7 GB |
| OS | Windows 11 Home 10.0.26300 |
| Python / libs | Python 3.13.5, torch 2.11.0+cu128 (CUDA 12.8), transformers 4.56.2, numpy 2.4.4, scipy 1.16.2, scikit-learn 1.7.2, datasets 5.0.1, safetensors 0.6.2 |
| Data | v1 frozen files: `results/flawed_model_suite/data/*` (Civil Comments slices), HF `stanfordnlp/sst2` |
| Seeds | per script (`SEED` constant at top): S1 42, S2 7, S3 11, S4 42, S5 42, S6 5, S7 n/a, S8 3, S9 9 |

Reproduce any spike: `python docs/v2/spikes/<script>.py` from the repository root.

---

## S1 GPU benchmark — `s1_gpu_bench.py`

8 000-row v1 Civil Comments train slice, seq 128, fp16 autocast, AdamW, 1 epoch. Inference on the 3 000-row v1 eval set.

| Model | Batch | s / epoch | train rows/s | peak VRAM (alloc) | GPU max temp | mean SM clock |
| ----- | ----- | --------- | ------------ | ----------------- | ------------ | ------------- |
| DistilBERT | 16 | 43.4 | 184 | 1 579 MiB | 59 °C | 2 644 MHz |
| DistilBERT | 32 | 26.2 | 305 | 1 993 MiB | 62 °C | 2 722 MHz |
| BERT-base | 16 | 93.7 | 85 | 2 744 MiB | 61 °C | 2 660 MHz |
| BERT-base | 32 | 45.8 | 175 | 3 551 MiB | 66 °C | 2 628 MHz |

| Inference rows/s | bs 64 | bs 128 | bs 256 |
| ---------------- | ----- | ------ | ------ |
| DistilBERT fp16 | 1 563 | 1 600 | 1 658 |
| DistilBERT fp32 | 546 | 569 | 589 |
| BERT-base fp16 | 803 | 825 | 830 |
| BERT-base fp32 | 282 | 284 | 293 |

Peak inference VRAM ≤ 2.8 GiB. bs-16 runs include first-call warm-up.

**Changes the design:** one v1-recipe controlled-defect model (BERT-base, 3 epochs, 8 000 rows) costs about 2.3 GPU-min, not the 15–30 min in spec 10. GPU time stops being the constraint on TrustBench size. Human time becomes the constraint.

## S2 Link-fit simulation — `s2_link_fit_sim.py`

One dimension; 70 % near-clean / 30 % defective models; reference noise 0.02; audit noise σ; 200 reps; 4 000 test models; tolerance 0.15. W1: the reference is the same statistic plus a 0.02 shift. W2: the evidence is a nonlinear proxy 0.6·r^0.6.

MAE of predicted risk (σ = 0.05):

| N models | W1 identity | W1 isotonic | W1 2-param monotone | W2 identity | W2 isotonic | W2 2-param |
| -------- | ----------- | ----------- | ------------------- | ----------- | ----------- | ---------- |
| 10 | 0.041 | 0.049 | 0.042 | 0.057 | 0.057 | 0.052 |
| 20 | 0.041 | 0.041 | 0.037 | 0.057 | 0.051 | 0.047 |
| 40 | 0.041 | 0.038 | 0.036 | 0.057 | 0.047 | 0.045 |
| 60 | 0.041 | 0.037 | 0.035 | 0.057 | 0.046 | 0.044 |
| 100 | 0.041 | 0.036 | 0.035 | 0.057 | 0.045 | 0.044 |
| 200 | 0.041 | 0.035 | 0.035 | 0.057 | 0.044 | 0.043 |

Decision error at τ (σ = 0.05, N = 60): W1 identity 0.107, isotonic 0.085, 2-param 0.080. W2: 0.167 / 0.108 / 0.105.

**Findings.** (1) The 2-parameter monotone link is at least as good as isotonic at every N ≤ 100 and both noise levels. At N = 10 isotonic is worse than no link at all. (2) Isotonic needs about 60–100 models to come within 5 % of its own N = 200 error; the 2-parameter link needs 20–40. (3) Fitted links beat the true inverse ("oracle") at σ = 0.10, so most of their gain is shrinkage toward the population, not shape learning. **Changes the design:** isotonic is not the default link. In W1 (the spec's own reference design) a link adds only shrinkage, which a measurement-error posterior gives without fitting.

## S3 Interval honesty — `s3_interval_honesty.py`

Nominal 95 %, 4 000 (A), 3 000 (B), 1 500 (C), 4 000 (D) trials; bootstrap B = 1 000.

A. One proportion, coverage:

| p | n | Wald | Wilson (v1 safety) | Jeffreys | Clopper-Pearson | Percentile bootstrap |
| - | - | ---- | ------------------ | -------- | --------------- | -------------------- |
| 0.05 | 10 | 0.39 | 0.92 | 0.99 | 0.99 | 0.39 |
| 0.05 | 30 | 0.78 | 0.94 | 0.99 | 0.99 | 0.78 |
| 0.05 | 100 | 0.88 | 0.97 | 0.94 | 0.99 | 0.96 |
| 0.10 | 20 | 0.88 | 0.96 | 0.96 | 0.99 | 0.88 |
| 0.30 | 10 | 0.85 | 0.92 | 0.92 | 0.99 | 0.96 |

B. Signed TPR gap (majority 500 positives): percentile bootstrap 0.916–0.953, Newcombe 0.940–0.956, Beta-Binomial draws 0.935–0.953. All usable for n ≥ 20; bootstrap is the lowest.

C. v1-style **absolute worst-group gap** (max − min TPR) when the true gap is 0:

| groups | positives / group | mean point estimate | bootstrap 95 % coverage |
| ------ | ----------------- | ------------------- | ----------------------- |
| 2 | 20 | 0.129 | 0.90 |
| 2 | 200 | 0.040 | 0.65 |
| 4 | 20 | 0.227 | 0.00 |
| 4 | 200 | 0.071 | 0.00 |

D. Optional stopping (peek every 25 rows up to 1 000, stop when the interval excludes τ = 0.25):

| true p | wrong-side stop, Wilson with peeking | wrong-side, fixed n = 1 000 Wilson | wrong-side, confidence sequence | CS decided within 1 000 |
| ------ | ------------------------------------ | ---------------------------------- | ------------------------------- | ----------------------- |
| 0.25 | 0.151 | 0.028 | 0.000 | 0.00 |
| 0.30 | 0.012 | 0.000 | 0.000 | 0.42 |

CS half-width at n = 1 000: 0.055 vs Wilson 0.027.

**Changes the design.** (1) Percentile bootstrap and Wald are unfit for rates at n < 100 near 0 (coverage 0.39). Rate statistics use Jeffreys or Wilson. (2) The max − min gap is biased upward by noise alone: a perfectly fair model with 4 groups gets a "gap" of 0.07–0.23 and a CI that excludes zero every time. v1's binary rule (ε = 0.02 on the CI lower bound) inherits this for k = 2. Replace with signed per-group gaps against the pooled rate. (3) Follow-up rounds invalidate fixed-n intervals: error 0.15 vs a nominal 0.025. Either cap looks and spend α (Bonferroni over ≤ 3 looks) or use an anytime-valid sequence. A sequence costs about 2× the width.

## S4 Counterfactual identity-swap fairness probe — `s4_counterfactual_fairness.py`

14 identity adjectives + 5 neutral adjectives. 76 real benign v1 eval sentences that contain exactly one identity adjective, plus 16 templates. Paired bootstrap over base sentences, B = 1 000. Models: the v1 controlled suite (the clean model has the same recipe as the sweep, flip 0), and known-answer wrappers on the clean model.

Real sentences:

| Model | injected | identity-mention gap (mean P(toxic) identity − neutral) [95 % CI] | any-swap decision flip rate | target-term deviation [95 % CI] |
| ----- | -------- | ------------------------------------------------------------------ | --------------------------- | ------------------------------- |
| clean (variant3) | 0 | 0.016 [0.009, 0.026] | 0.040 | −0.002 [−0.006, 0.002] |
| sweep r020 | 0.2 | 0.037 [0.024, 0.050] | 0.145 | — |
| variant1 (v1 V1) | 0.4 | **0.067 [0.049, 0.087]** | 0.316 | — |
| sweep r070 | 0.7 | 0.153 [0.120, 0.186] | 0.526 | — |
| sweep r100 | 1.0 | 0.261 [0.213, 0.311] | 0.605 | — |
| planted δ = 0.5 logit on "muslim" | known | — | — | 0.006 [−0.000, 0.014] |
| planted δ = 1.0 | known | — | — | 0.017 [0.007, 0.029] |
| planted δ = 2.0 | known | — | — | 0.048 [0.029, 0.069] |
| null (identity terms masked) | none | 0.000 [0, 0] | 0.000 | 0.000 [0, 0] |

Templates (n = 16) gave a between-identity spread of 0.65 [0.47, 0.82] on the clean model: they are too few and too saturated to be useful. Cost: about 3 s per model (about 1 900 forwards, BERT-base fp16).

**Findings.** The probe ranks the dose sweep perfectly and separates v1's V1 fairness model from the clean one with non-overlapping CIs. v1's equal-opportunity gap could not do this (0.164 vs 0.174 in `results/flawed_model_suite/FINAL_RESULTS_20261002.md`). The planted per-term bias is detected from δ = 1 logit upward; δ = 0.5 is borderline at n = 76. The null wrapper reads exactly zero. Caveats: one training seed per dose, and the clean model is not bias-free (0.016, CI excludes 0), which is a real property of Civil Comments training.

## S5 Faithfulness vs planted shortcut — `s5_faithfulness_shortcut.py`

DistilBERT on 6 000 SST-2 rows, 2 epochs. The shortcut model saw the token `zephyrine` in 90 % of positive training rows. Audit set: SST-2 validation (872 rows).

| Metric | clean | shortcut |
| ------ | ----- | -------- |
| accuracy (natural val) | 0.862 | 0.743 |
| AOPC top-5 − random, natural audit data | 0.330 | 0.281 |
| AOPC top-5 − random, audit data with trigger in 50 % of rows | 0.332 | 0.441 |
| global occlusion rank of trigger (seeded audit data) | 55 | **1** (mean \|attr\| 0.69, next 0.12) |
| insertion flip rate (trigger into negative rows) | 0.011 | **1.000** |
| occlusion cost | 6.0 s / 1 000 rows | 4.7 s / 1 000 rows |

Single seed, no CIs on AOPC.

**Findings.** AOPC measures whether the *attribution method* is faithful to the model. It does not measure whether the *model* is trustworthy, and it moves in opposite directions depending on the audit data. A shortcut model is still faithfully explained by occlusion. Global attribution ranking surfaces the shortcut when the audit data contains it. The insertion test confirms it causally. **Changes the design:** Explainability's property probe becomes *shortcut reliance* (discover candidate tokens by global attribution, then confirm by insertion and deletion flips). AOPC moves to the method card as a check on the attribution method.

## S6 VOI planner vs simple rule; expected-loss vs interval decision — `s6_voi_vs_rule.py`

1 500 simulated audits per scenario. Loss = spec 03 losses + row cost. Δ = mean total loss minus the `rule` policy (negative is better), with 95 % CI.

| Scenario | myopic VOI (spec 03) | rule + interval action | rule + Bayes action | fixed 1 000 + Bayes | fixed 1 000 + interval | oracle |
| -------- | -------------------- | ---------------------- | ------------------- | ------------------- | ---------------------- | ------ |
| 3-dim moderation-like | −0.87 [−0.95, −0.80], 0 rows | 4.70 (ref), 1 102 rows | **−1.10 [−1.15, −1.05]** | −0.71 | +0.36 | −1.34 |
| 3-dim high stakes | **+1.47 [+1.25, +1.68]**, 0 rows (always REJECT) | 8.53 (ref) | **−0.41 [−0.50, −0.31]** | +0.02 | +0.72 | −0.84 |
| 3-dim expensive rows | −2.86, 0 rows | 6.73 (ref) | −1.12 | +2.73 | +3.82 | −3.30 |
| 1-dim safety | +0.05 [+0.03, +0.07], 447 rows | 0.94 (ref), 224 rows | −0.02 [−0.03, −0.01] | +0.15 | +0.20 | −0.07 |
| 3-dim, prior misspecified | −0.34 | 6.03 (ref) | **−0.60 [−0.64, −0.55]** | −0.20 | +0.39 | −0.83 |

**Findings.** (1) Myopic one-step VOI almost never buys evidence when the action depends on several dimensions: one batch on one dimension rarely flips the action. It then acts on the prior alone, which is catastrophic in the high-stakes case (+1.47) and only lucky elsewhere. Spec 03 step 4 as written fails. (2) The simple "double the rows of every dimension whose CI straddles τ" rule is a sound sampler. (3) For the terminal choice, the expected-loss (Bayes) action beats the interval action in 5/5 scenarios (by 0.02–1.12 loss units), including under prior misspecification. It also adopts while some low-stake dimension violates in about 10 % of cases (the oracle does too). **Changes the design:** keep the expected-loss terminal decision, drop the VOI planner, and use the doubling rule with an α budget. "False-adopt rate" must be stake-weighted, or it penalises correct decisions.

## S7 Pickle opcode scan — `s7_pickle_scan.py`

Stdlib `pickletools.genops`, never unpickles. STACK_GLOBAL is resolved through the memo; torch zip archives are scanned per `.pkl` member. Allowlist for torch checkpoint callables; denylist for exec-capable modules and names; everything else is "unknown".

| Input | Result |
| ----- | ------ |
| benign `torch.save(state_dict)` | clean |
| inert protocol-2 `os.system` fixture (bytes only) | Tier A (dangerous) |
| inert protocol-4 STACK_GLOBAL `builtins.eval` fixture | Tier A |
| protocol-4 custom class `my_pkg.util.Helper` | Tier B (unknown) |
| 11 real Hub `pytorch_model.bin` (17–476 MB, zip and legacy formats) | 11 clean, 0 false Tier A |
| 2 real Hub `training_args.bin` | Tier B: `transformers.training_args.TrainingArguments`, `__main__.DistillationTrainingArguments` |

2.15 GB scanned in 3.9 s (warm file cache). **Findings.** Denylist hits are a sound Tier A trigger. "Unknown callable" must be Tier B: legitimate training-args pickles reference `__main__` classes. Sample of real files is small (13). Extend it in M0 to a few hundred `.bin` files before freezing the allowlist.

## S8 Reference independence — `s8_reference_independence.py`

60 models, 2 000 reps. The audit and a same-code reference share a model-specific method error b; an independent reference has its own error.

| var(b) / var(θ) | ρ(audit, same-code ref) | ρ(audit, independent ref) | ρ(audit, truth) | share passing S1 (ρ ≥ 0.7) with same-code ref | share with true ρ ≥ 0.7 |
| --------------- | ----------------------- | ------------------------- | --------------- | --------------------------------------------- | ----------------------- |
| 0 | 0.94 | 0.94 | 0.95 | 1.00 | 1.00 |
| 0.5 | 0.96 | 0.62 | 0.77 | 1.00 | 0.88 |
| 1 | 0.97 | 0.47 | 0.67 | 1.00 | 0.36 |
| 2 | 0.98 | 0.31 | 0.54 | 1.00 | 0.04 |

**Finding.** With a same-code reference, S1 passes in 100 % of replications even when the audit's true validity is 0.54. The criterion cannot fail, so it carries no information about validity. The reference must use a different instrument or different data-generating source, and controlled defects must be the primary truth.

## S9 Worked example — `s9_worked_example.py`

Reproduces section 5.4 of the synthesis: Jeffreys posteriors, Bayes action, Bonferroni (3 looks) interval view, doubling follow-up rule, EVPI per dimension, 200 000 posterior draws. Output in `results/s9_worked_example.json`.
