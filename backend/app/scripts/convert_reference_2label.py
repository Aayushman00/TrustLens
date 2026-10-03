"""Builds a 2-label copy of unitary/toxic-bert for the TrustLens binary probes.

toxic-bert has six sigmoid outputs; TrustLens decides with argmax over softmax, which cannot
express "toxic vs not toxic" on that head. New head: logit0 = 0, logit1 = toxic logit, so
softmax gives P(toxic) = sigmoid(z) and argmax==1 iff P(toxic) > 0.5 -- the same decision
rule as thresholding the original 'toxic' output at 0.5. Weights of the encoder are untouched.

Usage (from backend/)::  python -m app.scripts.convert_reference_2label
"""
from pathlib import Path

import torch
from huggingface_hub import hf_hub_download
from transformers import AutoModelForSequenceClassification, AutoTokenizer

REPO = "unitary/toxic-bert"
OUT = Path(__file__).resolve().parents[3] / "results" / "flawed_model_suite" / "models" / "reference_toxicbert_2label"


def main() -> None:
    src = AutoModelForSequenceClassification.from_pretrained(REPO)
    assert src.config.id2label[0] == "toxic"
    cfg = src.config
    cfg.num_labels = 2
    cfg.id2label = {0: "not_toxic", 1: "toxic"}
    cfg.label2id = {"not_toxic": 0, "toxic": 1}
    cfg.problem_type = "single_label_classification"
    dst = AutoModelForSequenceClassification.from_config(cfg)
    dst.bert.load_state_dict(src.bert.state_dict())
    with torch.no_grad():
        dst.classifier.weight.zero_(); dst.classifier.bias.zero_()
        dst.classifier.weight[1] = src.classifier.weight[0]
        dst.classifier.bias[1] = src.classifier.bias[0]
    OUT.mkdir(parents=True, exist_ok=True)
    dst.save_pretrained(OUT)
    AutoTokenizer.from_pretrained(REPO).save_pretrained(OUT)
    Path(hf_hub_download(REPO, "README.md")).replace(OUT / "README_source.md") if False else None
    (OUT / "README.md").write_text(Path(hf_hub_download(REPO, "README.md")).read_text(encoding="utf-8"), encoding="utf-8")
    # equivalence check
    tok = AutoTokenizer.from_pretrained(REPO)
    x = tok(["you are an idiot", "have a nice day", "I hate you all", "the meeting is at noon"], return_tensors="pt", padding=True)
    with torch.no_grad():
        a = torch.sigmoid(src(**x).logits[:, 0]); b = torch.softmax(dst(**x).logits, -1)[:, 1]
    print("max |sigmoid(toxic) - P1| =", float((a - b).abs().max()))


if __name__ == "__main__":
    main()
