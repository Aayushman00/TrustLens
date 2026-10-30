"""Fail if any reviewer-facing artifact leaks TrustLens/ground-truth/model-identity fields.

Run (after build_form.py):  python check_no_leak.py
Checks: create_l10_form.gs, packets_visible.json, REVIEWER_INSTRUCTIONS.md.
packet_form_mapping.json is organiser-only and deliberately NOT scanned.
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plain_english as pe
REF = HERE.parent / "l10_independent_validation_20261003" / "trustlens_reference.json"

STATIC = {
    "trustlens": r"trustlens", "L10 packet id": r"L10-\d\d", "risk id": r"\b[A-Z]{1,3}-[A-Z]{2,}-[A-Z0-9-]+\b",
    "gate id": r"\bG-[A-Z]+-", "OSD": r"\bO/S/D\b|\bOSD\b|osd-map|HeuristicOSD", "fries score": r"fries[_ ]?score|aspect[_ ]?score|aspect_scoring",
    "decision": r"mapping_blocked|risk_detected|no_material_risk|failed_gates|risk_ids",
    "ground truth": r"ground[_ ]?truth|expected[_ ]?severity|injected|flawed_model_suite|defect",
    "other answers": r"llm_reviews|claude_review|analysis\.json|trustlens_reference",
    "model identity": r"toxic[-_]?bert|huggingface\.co/[\w.-]+/[\w.-]+|unitary|detoxify|laura|\bhanu\b|github\.com/",
    "dimension in title": r"dimension measured|FRIES dimension:",
}


def reference_values():
    """Dynamic forbidden literals: every risk id / gate id / mapping string TrustLens recorded."""
    vals = set()
    for rec in json.loads(REF.read_text(encoding="utf-8")).values():
        vals.update(rec.get("risk_ids", []))
        vals.update(rec.get("failed_gates", []))
        if rec.get("mapping"):
            vals.add(rec["mapping"])
        vals.update(p["path"] for p in rec.get("provenance", []))
    return {v for v in vals if v}


def scan(name, text, hits, allow=None, skip=()):
    for label, rx in STATIC.items():
        if label in skip:
            continue
        for m in re.finditer(rx, text, re.I if label in ("trustlens", "ground truth", "model identity", "dimension in title") else 0):
            if allow and allow.search(m.group(0)):
                continue
            hits.append(f"{name}: [{label}] {m.group(0)!r}")
    for v in reference_values():
        if v in text:
            hits.append(f"{name}: [reference value] {v!r}")


# P12-only blinding: dataset/variant/base-model/URL clues, plus the substantive facts that must survive.
P12_FORBIDDEN = re.compile(
    r"jigsaw|civil comments|wikipedia comments|kaggle\.com|https?://|bert-base|roberta|xlm|xlmr|"
    r"unbiased|toxic_?bert|Toxic Comment Classification Challenge|Unintended\s+Bias in Toxic|"
    r"Multilingual Toxic|[`']original[`']|[`']multilingual[`']|--model_name original", re.I)
P12_KEEP = ["0.98856", "0.98636", "0.94734", "0.93639", "0.9536", "0.91655", "up to 10 annotators",
            "more than 500 examples", "Limitations and ethical considerations", "research purposes",
            "regardless of the tone or the intent", "vulnerable minority groups", "english", "russian",
            "[DATASET-A]", "[DATASET-B]", "[DATASET-C]", "[MODEL-VARIANT-A]", "[MODEL-VARIANT-B]",
            "[MODEL-VARIANT-C]", "[BASE-MODEL-A]", "[BASE-MODEL-B]", "[BASE-MODEL-C]", "[LIBRARY-NAME]",
            "[EXTERNAL-RESOURCE-URL]", "[CHECKPOINT-NAME-A]", "[REPOSITORY-ID]"]


def check_p12(visible, hits):
    frozen = json.loads((HERE.parent / "l10_independent_validation_20261003" / "packets" / "L10-12.json")
                        .read_text(encoding="utf-8"))["evidence"]["card_text"]
    card = "\n".join(b["t"] for b in next(p for p in visible if p["id"] == "P12")["blocks"]
                     if b["h"].startswith("Model card text"))
    for m in P12_FORBIDDEN.finditer(card):
        hits.append(f"P12 card: [p12 clue] {m.group(0)!r}")
    for k in P12_KEEP:
        if k not in card:
            hits.append(f"P12 card: [substance lost/placeholder missing] {k!r}")
    if len(card.split("\n")) != len(frozen.split("\n")):
        hits.append("P12 card: line count differs from frozen card")


def main():
    hits = []
    visible = json.loads((HERE / "packets_visible.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in visible] == [f"P{i:02d}" for i in range(1, 13)], "packet order/ids wrong"
    for p in visible:
        assert set(p) == {"id", "task", "blocks"}, f"{p['id']}: unexpected keys {set(p)}"
        for b in p["blocks"]:
            scan(f"{p['id']} {b['h']}", b["t"], hits)
        scan(f"{p['id']} task", p["task"], hits)
    check_p12(visible, hits)
    gs = (HERE / "create_l10_form.gs").read_text(encoding="utf-8")
    m = re.search(r"const PACKETS = (.*?);\n\nconst DIMS", gs, re.S)
    assert m and json.loads(m.group(1)) == visible, ".gs PACKETS differs from packets_visible.json (re-run build_form.py)"
    mi = re.search(r"const INTRO = (.*?);\nconst PACKETS", gs, re.S)
    assert mi and json.loads(mi.group(1)) == [{"h": h, "t": t} for h, t in pe.INTRO], ".gs INTRO differs from plain_english.INTRO"
    assert "' + p.dimension" not in gs and "SEVERITY" in gs, ".gs title/severity wiring wrong"
    # The intro may name TrustLens (as the tool that ran the tests) but nothing else TrustLens-related.
    scan("INTRO", mi.group(1), hits, skip=("trustlens",))
    scan("create_l10_form.gs (code)", gs.replace(m.group(1), "").replace(mi.group(1), ""), hits)
    scan("REVIEWER_INSTRUCTIONS.md", (HERE / "REVIEWER_INSTRUCTIONS.md").read_text(encoding="utf-8"), hits,
         skip=("trustlens",))
    if hits:
        print("LEAK CHECK FAILED"); print("\n".join(hits)); sys.exit(1)
    print(f"OK: no forbidden fields in {len(visible)} packets, .gs, instructions "
          f"({len(reference_values())} reference literals checked)")


if __name__ == "__main__":
    main()
