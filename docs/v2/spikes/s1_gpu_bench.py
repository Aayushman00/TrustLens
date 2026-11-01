"""Spike S1: training and inference throughput, peak VRAM and thermals on the dev GPU.

Trains DistilBERT and BERT-base for one epoch on the v1 8 000-row Civil Comments
train slice (seq 128, fp16 autocast), then times inference on the 3 000-row v1 eval set.
GPU temperature, SM clock and power are sampled from nvidia-smi every 2 s.

Run:  python docs/v2/spikes/s1_gpu_bench.py
Out:  docs/v2/spikes/results/s1_gpu_bench.json
"""
from __future__ import annotations

import csv
import json
import platform
import subprocess
import threading
import time
from pathlib import Path

import torch
import transformers
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[3]
TRAIN = ROOT / "results/flawed_model_suite/data/variant3_explainability_train.jsonl"
EVAL = ROOT / "results/flawed_model_suite/data/eval_set.csv"
OUT = Path(__file__).parent / "results" / "s1_gpu_bench.json"
SEED, SEQ = 42, 128


class GpuSampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.samples: list[tuple[float, float, float, float]] = []
        self.stop = threading.Event()

    def run(self) -> None:
        q = "--query-gpu=temperature.gpu,clocks.sm,power.draw,memory.used"
        while not self.stop.is_set():
            out = subprocess.run(["nvidia-smi", q, "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True).stdout.strip()
            try:
                self.samples.append(tuple(float(x) for x in out.split(",")))
            except ValueError:
                pass
            self.stop.wait(2.0)

    def summary(self) -> dict:
        if not self.samples:
            return {}
        cols = list(zip(*self.samples))
        return {k: {"max": max(c), "mean": round(sum(c) / len(c), 1)}
                for k, c in zip(("temp_c", "sm_clock_mhz", "power_w", "mem_used_mib"), cols)}


def load_texts() -> tuple[list[str], list[int], list[str]]:
    rows = [json.loads(l) for l in TRAIN.read_text(encoding="utf-8").splitlines() if l.strip()]
    with EVAL.open(encoding="utf-8") as f:
        ev = [r["text"] for r in csv.DictReader(f)]
    return [r["text"] for r in rows], [int(r["label"]) for r in rows], ev


def bench(name: str, texts, labels, eval_texts) -> dict:
    torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(name)
    enc = tok(texts, truncation=True, max_length=SEQ, padding="max_length", return_tensors="pt")
    ds = TensorDataset(enc["input_ids"], enc["attention_mask"], torch.tensor(labels))
    res: dict = {"model": name, "train_rows": len(texts), "seq_len": SEQ}
    for bs in (16, 32):
        model = AutoModelForSequenceClassification.from_pretrained(name, num_labels=2).cuda()
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        scaler = torch.amp.GradScaler()
        dl = DataLoader(ds, batch_size=bs, shuffle=True, generator=torch.Generator().manual_seed(SEED))
        torch.cuda.reset_peak_memory_stats()
        sampler = GpuSampler(); sampler.start()
        torch.cuda.synchronize(); t0 = time.perf_counter()
        model.train()
        for ids, mask, y in dl:
            with torch.autocast("cuda", dtype=torch.float16):
                loss = model(input_ids=ids.cuda(), attention_mask=mask.cuda(), labels=y.cuda()).loss
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
        torch.cuda.synchronize(); dt = time.perf_counter() - t0
        sampler.stop.set(); sampler.join()
        res[f"train_bs{bs}"] = {
            "seconds_per_epoch": round(dt, 1),
            "samples_per_s": round(len(texts) / dt, 1),
            "peak_vram_alloc_mib": round(torch.cuda.max_memory_allocated() / 2**20),
            "gpu": sampler.summary(),
        }
        if bs == 32:
            res["inference"] = infer(model, tok, eval_texts)
        del model, opt
        torch.cuda.empty_cache()
    return res


@torch.no_grad()
def infer(model, tok, texts) -> dict:
    model.eval()
    enc = tok(texts, truncation=True, max_length=SEQ, padding="max_length", return_tensors="pt")
    out = {}
    for dtype in ("fp16", "fp32"):
        for bs in (64, 128, 256):
            torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); t0 = time.perf_counter()
            for i in range(0, len(texts), bs):
                ids, mask = enc["input_ids"][i:i + bs].cuda(), enc["attention_mask"][i:i + bs].cuda()
                if dtype == "fp16":
                    with torch.autocast("cuda", dtype=torch.float16):
                        model(input_ids=ids, attention_mask=mask)
                else:
                    model(input_ids=ids, attention_mask=mask)
            torch.cuda.synchronize(); dt = time.perf_counter() - t0
            out[f"{dtype}_bs{bs}"] = {"rows_per_s": round(len(texts) / dt, 1),
                                      "peak_vram_alloc_mib": round(torch.cuda.max_memory_allocated() / 2**20)}
    return out


def main() -> None:
    texts, labels, ev = load_texts()
    result = {
        "env": {"gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
                "cuda": torch.version.cuda, "transformers": transformers.__version__,
                "python": platform.python_version(), "seed": SEED,
                "total_vram_mib": torch.cuda.get_device_properties(0).total_memory // 2**20},
        "runs": [bench(m, texts, labels, ev) for m in ("distilbert-base-uncased", "bert-base-uncased")],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
