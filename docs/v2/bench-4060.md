# RTX 4060 Laptop benchmark (spike S1)

Run 2026-11-01 with `docs/v2/spikes/s1_gpu_bench.py` (seed 42). Raw numbers: `docs/v2/spikes/results/s1_gpu_bench.json`. Budget derived from them: `10-compute-plan.md`, "Measured throughput" and "Budget".

| Item | Value |
| ---- | ----- |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8 187 MiB |
| Python / torch / CUDA | 3.13.5 / 2.11.0+cu128 / 12.8 (system `python`; the repo `.venv` has torch 2.6+cu124) |
| transformers | 4.56.2 |
| Workload | 8 000-row Civil Comments train slice (`variant3_explainability_train.jsonl`), seq 128, fp16 autocast, AdamW, 1 epoch; inference on the 3 000-row v1 eval set |

## Training (1 epoch, 8 000 rows)

| Model | Batch | s / epoch | rows/s | peak VRAM alloc | GPU max temp | mean SM clock |
| ----- | ----- | --------- | ------ | --------------- | ------------ | ------------- |
| DistilBERT | 16 | 43.4 | 184.3 | 1 579 MiB | 59 °C | 2 644 MHz |
| DistilBERT | 32 | 26.2 | 305.0 | 1 993 MiB | 62 °C | 2 722 MHz |
| BERT-base | 16 | 93.7 | 85.4 | 2 744 MiB | 61 °C | 2 660 MHz |
| BERT-base | 32 | 45.8 | 174.6 | 3 551 MiB | 66 °C | 2 628 MHz |

Batch-16 rows include first-call warm-up, so batch 32 is the planning figure.

## Inference (rows/s, peak VRAM alloc)

| Model | fp16 bs64 | fp16 bs128 | fp16 bs256 | fp32 bs64 | fp32 bs128 | fp32 bs256 |
| ----- | --------- | ---------- | ---------- | --------- | ---------- | ---------- |
| DistilBERT | 1 563 (1 331 MiB) | 1 600 (1 503 MiB) | 1 658 (1 847 MiB) | 546 (1 342 MiB) | 569 (1 610 MiB) | 589 (2 146 MiB) |
| BERT-base | 803 (2 122 MiB) | 825 (2 306 MiB) | 830 (2 675 MiB) | 282 (2 022 MiB) | 284 (2 290 MiB) | 293 (2 827 MiB) |

## Takeaways

- fp16 is about 2.8× fp32 at every batch size, so the GPU path stays fp16 and rounds predictions to 4 dp before hashing.
- One BERT-base controlled-defect model (3 epochs, 8 000 rows) costs about 2.3 GPU-min; peak VRAM stays under 3.6 GiB for training and 2.8 GiB for inference.
- Temperatures stayed at or below 66 °C with a steady 2.6–2.7 GHz mean SM clock: no thermal throttling in these runs. Timing is informational and never an input to results.
