# 10 — Compute plan (RTX 4060 Laptop GPU, 8 GB VRAM)

Reference machine: RTX 4060 Laptop GPU (8 188 MiB), 15.7 GB RAM, Windows 11 Home, Python 3.13.5, torch 2.11.0+cu128, transformers 4.56.2. The Phase 0 benchmark is done: spike S1 ([`spikes/RESULTS.md`](spikes/RESULTS.md), `spikes/s1_gpu_bench.py`, run 2026-11-01) replaced the earlier planning estimates with measured numbers, tagged MEASURED below. Anything still tagged ASSUMPTION is not measured.

## What fits in 8 GB

| Task | Model class | Fits? | Notes |
| ---- | ----------- | ----- | ----- |
| Train controlled-defect text classifiers | DistilBERT / BERT-base / small RoBERTa, fp16/bf16, batch 16–32, seq 128 | Yes | Gradient checkpointing if seq grows |
| Inference for probes | Same, batch 64–256 | Yes | Dominant cost is perturbation multiplicity |
| Paraphrase / back-translation instrument | Marian-size MT pair or T5-small/base paraphraser | Yes | Run once, cache outputs by hash |
| Attribution (occlusion, gradient, IG) | Same classifiers | Yes | Occlusion needs ≈ tokens × examples forwards |
| Tabular models | scikit-learn / XGBoost | CPU | GPU optional |
| Image classifiers (R3) | ResNet-50 / ViT-B | Yes (inference) | Training not required |
| Generative LLM targets (R4, post-v2) | ≤ 3–4B parameters, 4-bit | Marginal | Defer; larger models need remote/black-box endpoints |

Anything that needs > 8 GB is out of scope for local runs and is represented as black-box endpoint audits (spec 05) or deferred.

## Measured throughput (S1)

8 000-row Civil Comments train slice, seq 128, fp16 autocast, AdamW, 1 epoch. Inference on the 3 000-row v1 eval set.

| Model | Batch | s / epoch | train rows/s | peak VRAM | GPU max temp |
| ----- | ----- | --------- | ------------ | --------- | ------------ |
| DistilBERT | 32 | 26.2 | 305 | 1 993 MiB | 62 °C |
| BERT-base | 32 | 45.8 | 175 | 3 551 MiB | 66 °C |

| Inference rows/s (batch 256) | fp16 | fp32 |
| ---------------------------- | ---- | ---- |
| DistilBERT | 1 658 | 589 |
| BERT-base | 830 | 293 |

Peak inference VRAM ≤ 2.8 GiB. fp16 is about 2.8× faster than fp32, so the fp16 path is kept (with predictions rounded to 4 dp for evidence hashing). Counterfactual probe: about 3 s per BERT-base model (S4). Occlusion: about 5 s per 1 000 short SST-2 rows on DistilBERT (S5). Pickle scan: 2.15 GB in 3.9 s (S7). Bs-16 rows include first-call warm-up. The GPU stayed at or below 66 °C, with mean SM clock 2.6–2.7 GHz: thermals did not throttle these runs.

## Budget (recomputed from S1)

One v1-recipe controlled-defect BERT-base model (3 epochs, 8 000 rows) costs about **2.3 GPU-min**, not the 15–30 min the first draft assumed. GPU time stops being the limit on TrustBench size; human time (labelling, review, writing) is.

| Workload | Count | Per unit | Total | Basis |
| -------- | ----- | -------- | ----- | ----- |
| Train controlled models (BERT-base, 3 ep, 8k rows) | 300 | 2.3 min | 11.5 GPU-h | MEASURED S1 |
| Reference inference, natural + controlled (30k rows, 10 perturbation passes) | 340 | 11 × 30k / 825 rows·s⁻¹ ≈ 6.7 min | 38 GPU-h | MEASURED S1 throughput; pass count ASSUMPTION |
| Counterfactual probe | 340 × 5 seeds | 3 s | 1.5 GPU-h | MEASURED S4 |
| Shortcut probe (occlusion, 1 000 Civil-Comments-length rows) | 340 | ≈ 50 s | 4.7 GPU-h | S5 measured 5 s / 1 000 short rows; ×10 for length and BERT-base is ASSUMPTION |
| Audit runs, 3 budgets × 5 seeds | 340 × 15 | ≤ 1 min | ≤ 85 GPU-h worst case, ≈ 20 realistic | ASSUMPTION |
| **Total** | | | **≈ 75 GPU-h realistic, ≈ 140 worst case** | ≈ 2–3 weeks of overnight runs |

Paraphrase generation (cut-line 1), the tabular rung and the image smoke set are not in the core budget. TrustBench-C target: ≥ 120 controlled models (3 seeds per dose), ≥ 40 natural, ≥ 12 tampered. The worst case is above the earlier 60–120 GPU-h range, mostly from the larger corpus; at 6–8 productive GPU-hours per night it is still feasible, which is the point of designing around small base models.

## Practices

1. **Cache by content hash.** Every probe output is already stored under sha256 (evidence store). Re-runs reuse identical inputs; changing a seed or methodology invalidates only what depends on it.
2. **Queue overnight.** Reference and training jobs go through the existing Celery worker with per-job time and VRAM guards; failures are typed (`budget_exceeded`), not crashes.
3. **Thermals.** Laptop throttles: run long jobs with a fixed power plan, log GPU clocks and temperature in the evidence metadata (device info is already recorded). Treat timing as informational, never as an input to results.
4. **Determinism.** Fix seeds, set deterministic algorithms where available, record CUDA/driver/torch versions. Cross-machine byte-identity (S6) is checked on CPU; GPU nondeterminism is quantified and bounded rather than hidden.
5. **Model hygiene.** Natural models pinned by revision and hash; local cache sized (est. 30–60 GB) and documented; downloads never happen implicitly at import (v1 property, kept).
6. **Cloud escape hatch.** If a stratum needs more than the laptop can do (e.g. a bigger natural model), a one-off rental GPU is allowed provided the identical container image and seeds are used and the machine is recorded in evidence. Not planned, not required.

## Phase 0 benchmark protocol

Done for training and inference throughput, peak VRAM, thermals (S1), counterfactual cost (S4), occlusion cost (S5) and pickle scan (S7). Still to measure in M0: occlusion on BERT-base with Civil-Comments-length rows (the ×10 ASSUMPTION), paraphrase-model throughput (only if cut-line 1 is reached), and end-to-end time of one full v1 evaluation. Update the table above and the roadmap if any assumption is off by > 2×. Note: S4 and S5 trained one model per dose, so seed variance of the probes is not yet measured.
