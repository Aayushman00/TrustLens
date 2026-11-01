# 10 — Compute plan (RTX 4060 Laptop GPU, 8 GB VRAM)

Reference machine: RTX 4060 Laptop GPU (8 GB), a laptop CPU/RAM class system, Windows 11 with Docker. All numbers below are **planning estimates**; Phase 0 replaces them with a measured benchmark committed to `docs/v2/bench-4060.md`.

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

## Budget estimate (to be benchmarked)

Assumptions: DistilBERT-class model; Civil-Comments-sized data; fp16; seq 128. Throughput figures are placeholders until Phase 0.

| Workload | Count | Per unit | Total |
| -------- | ----- | -------- | ----- |
| Train controlled-defect models | ~30 | 15–30 min | ~8–15 GPU-h |
| Train additional controls / defect interactions | ~15 | 15–30 min | ~4–8 GPU-h |
| Reference evaluation, natural + synthetic models (full probe set, ≥10× audit data) | ~60 | 10–25 min | ~10–25 GPU-h |
| Audit runs at 3 budgets, repeated for seed variance (5 seeds) | ~60×3×5 | 1–4 min | ~15–50 GPU-h |
| Paraphrase generation for packs | few | minutes | < 2 GPU-h |
| Tabular rung + image smoke set | ~20 | minutes | < 5 GPU-h |
| Test-split final run | once | — | ~10 GPU-h |
| **Total** | | | **≈ 60–120 GPU-h** |

At 6–8 productive GPU-hours per night, that is roughly 2–4 weeks of cumulative overnight compute across the year. It is feasible, which is the point of designing around small base models.

## Practices

1. **Cache by content hash.** Every probe output is already stored under sha256 (evidence store). Re-runs reuse identical inputs; changing a seed or methodology invalidates only what depends on it.
2. **Queue overnight.** Reference and training jobs go through the existing Celery worker with per-job time and VRAM guards; failures are typed (`budget_exceeded`), not crashes.
3. **Thermals.** Laptop throttles: run long jobs with a fixed power plan, log GPU clocks and temperature in the evidence metadata (device info is already recorded). Treat timing as informational, never as an input to results.
4. **Determinism.** Fix seeds, set deterministic algorithms where available, record CUDA/driver/torch versions. Cross-machine byte-identity (S6) is checked on CPU; GPU nondeterminism is quantified and bounded rather than hidden.
5. **Model hygiene.** Natural models pinned by revision and hash; local cache sized (est. 30–60 GB) and documented; downloads never happen implicitly at import (v1 property, kept).
6. **Cloud escape hatch.** If a stratum needs more than the laptop can do (e.g. a bigger natural model), a one-off rental GPU is allowed provided the identical container image and seeds are used and the machine is recorded in evidence. Not planned, not required.

## Phase 0 benchmark protocol

Measure and commit: training throughput (samples/s) for DistilBERT and BERT-base; inference throughput at batch 64/128/256; peak VRAM; occlusion cost per 1 000 examples; paraphrase-model throughput; end-to-end time of one full v1 evaluation. Update the table above and the roadmap if any assumption is off by > 2×.
