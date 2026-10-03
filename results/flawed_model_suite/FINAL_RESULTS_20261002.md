# TrustLens final experiments — 2026-10-02

All numbers below are read from files in this folder; nothing was edited by hand.
Historical runs (`eval_results`, `eval_results_v2`, `eval_results_v3`) are unchanged.

## Setup

| item | value |
|---|---|
| Ground truth + detection rules | `ground_truth.json` (written before the runs; `controls` field added post-review from the existing roles) |
| LLM freeze | `llm_freeze.json`: Groq `openai/gpt-oss-120b`, temperature 0.2, `llm_v1`; other providers blanked (`docker-compose.experiment.yml`) |
| Methodology | `v3-hardening-2026` |
| Eval set | `data/eval_set.csv` (3,000 Civil Comments rows; 20% toxic; 282 severe & toxic; identity-group label-rate gap 0.505) |
| Controlled suite | 9 models × 5 runs (`final_20261002_repeat5*`) and sweep, on the image built at experiment start (before the engineering fixes below); code commit recorded in each run folder's `_summary.json` `_meta` |
| Severity sweep | 6 new models × 3 runs (`sweep_20261002_*`) + V1/V3/V5 levels from the suite |
| Real Hub models | 15 models × 1 run (`hub_final_c0*`, image `ade6bd2`), selection frozen in `extra_models.json` (rule v3) |
| Reports | every run: TrustLens report JSON + PDF + raw evidence under `*/artifacts/` |
| Analysis | `final_20261002_analysis/analysis.md`, `final_20261002_analysis_with_sweep/analysis.md`, `hub_final_summary/hub_models.md` |

## Results

### 1. Repeatability (RQ4)

- Deterministic dimensions (Fairness, Robustness, behavioural Safety): **std 0.000 over 5 runs** for every model (27 model×dimension cells).
- LLM-rated dimensions (Integrity, Explainability): mean std **0.64**, max **2.23** (control model).
- FRIES std per model: 0.00–0.59.
- Evidence-level flags: 100% run-to-run agreement.
- LLM operational reliability: 34/45 runs used the LLM, **11/45 fell back** to the heuristic (Groq 429 rate limits + 3 DNS failures). On the real-model run, 14/15 fell back because the provider's **daily token quota** (200k tokens/day) was exhausted.

### 2. Detection of injected defects (RQ2, RQ5)

Controls (`reference_hub`, `reference_toxicbert_2label`) are excluded from the counts.

| rule | TP | FP | FN | TN | precision | recall |
|---|---|---|---|---|---|---|
| score-level (vs control mean, gap > max(1, 2·pooled std)) | 2 | 1 | 9 | 23 | 0.67 | 0.18 |
| evidence-level (probe risk flags) | 7 | 11 | 4 | 13 | 0.39 | 0.64 |

The evidence-level rule cannot be read at face value:
- SAFETY and EXPLAINABILITY card risks also fire on **100%** of the clean controls (INTEGRITY: 50%).
- Binary FAIRNESS evidence never raises a risk flag, so it cannot be detected by construction.

Per defect:
- **Robustness (V2): detected.** Accuracy drop 0.041, score 7.56 vs 8.65.
- **Fairness (V1): not detected** under any rule. EOD 0.164 vs control 0.174. excess DPD 0.000, because the dataset's own group gap is 0.505. This is a negative result.
- **Safety (V5): measured** (severe FNR 0.44, CI [0.38, 0.50] vs control 0.355) but not separated at score level: both get Safety 6.60.
- **Explainability / Integrity card defects:** LLM-rated scores are lower (V3 Explainability 4.0, V4/V4b Integrity 2.3–2.4) than the control (5.2 ± 1.2, 4.5 ± 1.8). The control's LLM-induced noise keeps them under the pre-registered threshold.
- **Spillover (not a defect we injected):** the overfit V2 is also less fair (EOD 0.370), so its Fairness flag counts as a false positive under the pre-registered rule even though the effect is real.

### 3. Severity sensitivity (RQ3)

Same clean slice and the same hyperparameters; only the flip rate changes (`final_20261002_analysis_with_sweep`).

| sweep | evidence metric vs rate (Spearman) | dimension score vs rate |
|---|---|---|
| fairness 0 → 1.0 | EOD 0.07 → 0.32 (ρ = 1.00); DPD ρ = 1.00 | Fairness 8.65 → 7.32 (ρ = −0.95) |
| safety 0 → 1.0 | severe FNR 0.27 → 0.66 (ρ = 1.00); harmful recall ρ = −1.00 | Safety 6.95 → 5.24 (ρ = −1.00) |

The evidence tracks injected severity monotonically. The O/S/D scoring compresses it: the full 0 → 100% defect moves the dimension score by only 1.3–1.7 points.

### 4. Real Hugging Face models (RQ1, RQ6), descriptive only

- 15/15 imported, evaluated, FINALIZED, and their reports exported.
- **Cryptographic artifact check (new):** 15/15 `match` between the cached weight bytes and the Hub's LFS sha256.
- **Real provenance finding:** `textdetox/xlmr-large-toxicity-classifier` and `textdetox/xlmr-base-toxicity-classifier` ship byte-identical weights (sha256 `829a9d93…`, hidden size 768, 12 layers). The "large" repo does not contain large-size weights.
- **Abstention:** `pysentimiento/bert-it-hate-speech` (Italian) was flagged as a near-constant predictor (harmful recall 0.023). Fairness/Robustness gave INSUFFICIENT_EVIDENCE and **FRIES was withheld**, while behavioural Safety still reports severe FNR 0.97.
- **Domain/task mismatch made visible:**
  - Hate-speech models score lowest on harmful recall on toxicity data (0.15).
  - The Russian model gets 0.21.
  - toxic-bert (harmful recall 0.42, severe FNR 0.355) is weaker on Civil Comments than `unitary/unbiased-toxic-roberta` (0.73 / 0.145).

### 5. Integrity tamper demonstration

`tamper_demo.json`:
- Untouched variant1 weights give `match`.
- Flipping one byte gives `diverge` and `I-INT-BYTES-DIVERGE`.
- For Hub models the same check now runs automatically against the Hub's LFS hash.

## Engineering issues found by running the experiments (all fixed, each with a regression test)

| issue | effect | fix |
|---|---|---|
| `str(engine.url)` masks the password, so the API built a new connection pool per request | Postgres "too many clients"; runs failed | compare the raw URL; dispose the old engine |
| FastAPI 0.121+ commits yield-dependencies after the response | client saw "not validated" right after a 200 | `Depends(get_db, scope="function")` |
| Task enqueued before the API commit | evaluation stuck PENDING forever | worker retries `EvaluationNotVisibleError` (deterministic 1+2+4 s) |
| v1 LLM prompt ~7.3k tokens for long cards | well-documented models were never LLM-assessed | prompt v2 (capped card/evidence, versioned) |
| LLM fallback reason only in logs | fallbacks not traceable | `llm_fallback_reason`, `llm_attempts`, `llm_prompt_version` stored per aspect; quota-aware retry |

## What the data supports

TrustLens's **measured evidence** is reproducible (std 0) and severity-sensitive (ρ = 1.0). It also catches real-world artifact anomalies.

The **decision layer** is the weak link:
- The O/S/D bands compress severity.
- The LLM-rated dimensions add run-to-run noise.
- The LLM depends on provider quotas.
- The card-based risk flags fire on clean models too.

V1's fairness defect is not distinguishable from a clean model on this evaluation set. That holds for the raw metric as well as the score.
