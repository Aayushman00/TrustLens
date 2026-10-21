"""Build the L10 Google Form artifacts from the FROZEN packets (read-only).

Writes next to this file: create_l10_form.gs, packets_visible.json, packet_form_mapping.json.
Run:  python build_form.py
"""
import hashlib, json, re
from pathlib import Path

import plain_english as pe

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "l10_independent_validation_20261003"
CHUNK = 2500  # keep each Forms text item well under Forms' length limits

# Masks applied to reviewer-visible text only (frozen files are never touched).
MASKS = [
    (re.compile(r"\(unitary/toxic-bert, 2-label conversion\)"), "(2-label conversion)"),
    (re.compile(r"L10-(\d\d)"), r"P\1"),
]

# P12 model-card blinding only (other packets are untouched). Order matters: specific before general.
P12_MASKS = [(re.compile(rx), rep) for rx, rep in [
    # all external URLs first (they embed dataset slugs), then config files, slugs, data dir
    # all external URLs
    (r"https?://[^\s)\]}>\"']+", "[EXTERNAL-RESOURCE-URL]"),
    (r"configs/Multilingual_\w+?_stage2\.json", "configs/[CONFIG-C-STAGE2]"),
    (r"configs/Multilingual_\w+?\.json", "configs/[CONFIG-C-STAGE1]"),
    (r"configs/Unintended_\w+?\.json", "configs/[CONFIG-B]"),
    (r"configs/Toxic_\w+?\.json", "configs/[CONFIG-A]"),
    (r"jigsaw-multilingual-toxic-comment-classification", "[DATASET-C]"),
    (r"jigsaw-unintended-bias-in-toxicity-classification", "[DATASET-B]"),
    (r"jigsaw-toxic-comment-classification-challenge", "[DATASET-A]"),
    (r"jigsaw_data", "[DATA-DIRECTORY]"),
    # challenge / dataset names (C and B before A so A's pattern cannot eat them)
    (r"(?:Jigsaw )?Multilingual [Tt]oxic [Cc]omment [Cc]lassification(?: Challenge)?", "[DATASET-C]"),
    (r"(?:Jigsaw )?Unintended\s+Bias in Toxic(?:ic)?(?:ity| comments)(?: Classification| Challenge)?", "[DATASET-B]"),
    (r"Toxic [Cc]omment [Cc]lassification(?: Challenge)?(?! with)", "[DATASET-A]"),
    (r"Wikipedia Comments", "[DATASET-A]"),
    (r"Civil Comments", "[DATASET-B]"),
    (r"Jigsaw ?", ""),
    # checkpoint names, then model variants, then base models
    (r"unbiased_toxic_roberta", "[CHECKPOINT-NAME-B]"),
    (r"multilingual_toxic_xlm_r", "[CHECKPOINT-NAME-C]"),
    (r"toxic_bert", "[CHECKPOINT-NAME-A]"),
    (r"(?<=[`'])original(?=[`'])|(?<=--model_name )original", "[MODEL-VARIANT-A]"),
    (r"(?<=[`'])unbiased(?=[`'])", "[MODEL-VARIANT-B]"),
    (r"(?<=[`'])multilingual(?=[`'])", "[MODEL-VARIANT-C]"),
    (r"xlm-roberta-base", "[BASE-MODEL-C]"),
    (r"roberta-base", "[BASE-MODEL-B]"),
    (r"bert-base-uncased", "[BASE-MODEL-A]"),
    # project / library / org / author identity
    (r"Laura Hanu|Hanu, Laura", "[AUTHOR]"),
    (r"unitaryai/detoxify", "[REPOSITORY-ID]"),
    (r"(?i:unitaryai|unitary)", "[ORG]"),
    (r"(?i:detoxify)", "[LIBRARY-NAME]"),
]]


def mask(s, masks=MASKS):
    for rx, rep in masks:
        s = rx.sub(rep, s)
    return s


def fmt(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return repr(round(v, 6))  # 6 dp, same precision the packets already use elsewhere
    return mask(str(v))


def fmt_list(x):
    return "[" + ", ".join(fmt(i) for i in x) + "]"


def render(v, indent=0):
    pad = "  " * indent
    if isinstance(v, dict):
        out = []
        for k, x in v.items():
            if isinstance(x, list) and all(not isinstance(i, (dict, list)) for i in x):
                out.append(f"{pad}{k}: {fmt_list(x)}")
            elif isinstance(x, (dict, list)) and x:
                out.append(f"{pad}{k}:")
                out += render(x, indent + 1)
            elif isinstance(x, (dict, list)):
                out.append(f"{pad}{k}: (empty)")
            else:
                out.append(f"{pad}{k}: {fmt(x)}")
        return out
    out = []  # list of dicts
    for i, x in enumerate(v, 1):
        out.append(f"{pad}- item {i}:")
        out += render(x, indent + 1)
    return out


def chunks(text):
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > CHUNK:  # hard-wrap pathological long lines
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:CHUNK])
            line = line[CHUNK:]
        if len(cur) + len(line) + 1 > CHUNK:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def main():
    hashes = json.loads((SRC / "packet_hashes.json").read_text())["packets"]
    visible, mapping = [], {}
    for n in range(1, 13):
        lid, pid = f"L10-{n:02d}", f"P{n:02d}"
        p = json.loads((SRC / "packets" / f"{lid}.json").read_text(encoding="utf-8"))
        # same canonical hash as run_l2_interpretation.packet_sha256
        h = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        assert h == hashes[lid], f"{lid} no longer matches frozen hash"
        ev = dict(p["evidence"])
        card = ev.pop("card_text", None)
        raw = "\n".join(render(ev))
        blocks = [{"h": "What this evidence is about", "t": pe.EXPLAINER[p["dimension"]]}]
        for h, t in pe.RENDER[p["dimension"]](ev, raw):
            ps = chunks(t)
            blocks += [{"h": h if len(ps) == 1 else f"{h} ({i}/{len(ps)})", "t": c} for i, c in enumerate(ps, 1)]
        if card is not None:
            cs = chunks(mask(mask(card), P12_MASKS) if pid == "P12" else mask(card))
            blocks += [{"h": f"Model card text, verbatim ({i}/{len(cs)})", "t": c} for i, c in enumerate(cs, 1)]
        visible.append({"id": pid, "task": mask(p["task"]), "blocks": blocks})
        mapping[pid] = {"frozen_packet": lid, "dimension": p["dimension"], "sha256": hashes[lid], "form_page": n + 1}
    (HERE / "packets_visible.json").write_text(json.dumps(visible, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "packet_form_mapping.json").write_text(json.dumps(
        {"WARNING": "ORGANISER ONLY - never show to reviewers",
         "order": "fixed P01..P12 = L10-01..L10-12", "packets": mapping}, indent=2), encoding="utf-8")
    tpl = (HERE / "create_l10_form.template.gs").read_text(encoding="utf-8")
    (HERE / "create_l10_form.gs").write_text(
        tpl.replace("/*PACKETS_JSON*/", json.dumps(visible, indent=1, ensure_ascii=False))
           .replace("/*INTRO_JSON*/", json.dumps([{"h": h, "t": t} for h, t in pe.INTRO], indent=1, ensure_ascii=False)),
        encoding="utf-8")
    print("built", len(visible), "packets")


if __name__ == "__main__":
    main()
