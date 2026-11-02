"""v2 probes (Task 12) against fake predict_proba callables; no model, no GPU."""

import math

import pytest

from app.evidence import EvidenceInputs, EvidenceItem
from app.probes.v2.fair_counterfactual import counterfactual
from app.probes.v2.lexicon_en_v1 import CATEGORIES, LEXICON_SHA256
from app.probes.v2.rob_invariance import _typo, invariance

INP = EvidenceInputs(model_ref="tb/clean__s1@local", dataset_sha256="0" * 64, methodology_version="tl-v2")


def _rows(texts, label=0, **kw):
    return [{"text": t, "label": label, "identity_ref": 0, "severe": 0, **kw} for t in texts]


def _by_id(items):
    return {it.id: it for it in items}


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


# fair.counterfactual

def test_counterfactual_null_model_zero():
    rows = _rows([f"My {t} neighbour is kind {i}." for i in range(20) for t in ("muslim", "gay", "black")])
    items = _by_id(counterfactual(lambda ts: [0.2] * len(ts), rows, seed=1, budget=1000, inputs=INP))
    fr = items["fair.counterfactual.flip_rate"]
    assert fr.counts.k == 0 and fr.counts.n == 20 * (4 + 3 + 4)
    assert fr.inputs.instrument_hashes["lexicon"] == LEXICON_SHA256 and fr.inputs.seed == 1
    gap = items["fair.counterfactual.mention_gap"]
    assert gap.applicability == "applicable" and gap.estimate == pytest.approx(0.0) and gap.n == 60


def test_counterfactual_biased_model_detected():
    def fake(ts):  # +2 logits when "muslim" is present, base logit -1 -> label flips
        return [round(_sigmoid(-1 + 2 * ("muslim" in t.lower())), 4) for t in ts]

    rows = _rows([f"My christian neighbour is kind {i}." for i in range(60)])
    items = _by_id(counterfactual(fake, rows, seed=2, budget=1000, inputs=INP))
    fr = items["fair.counterfactual.flip_rate"]
    assert (fr.counts.k, fr.counts.n) == (60, 240)
    assert fr.uncertainty.interval[0] > 0
    gap = items["fair.counterfactual.mention_gap"]
    assert gap.estimand.scale == "difference" and gap.uncertainty.method == "paired_bootstrap"
    assert gap.n == 60 and 0 < len(gap.uncertainty.draws) <= 1000 and gap.estimate > 0


def test_counterfactual_skips_rows_without_identity_term():
    texts = [f"plain row number {i}" for i in range(7)] + [
        "A muslim man helped me.", "My gay friend called.", "The black cat sat."]
    items = _by_id(counterfactual(lambda ts: [0.1] * len(ts), _rows(texts), seed=1, budget=1000, inputs=INP))
    fr = items["fair.counterfactual.flip_rate"]
    expected = sum(len(CATEGORIES[c]) - 1 for c in ("religion", "sexuality_gender", "race_ethnicity"))
    assert fr.counts.n == fr.n == expected == 11
    assert items["fair.counterfactual.mention_gap"].applicability == "insufficient_evidence(n<50)"


def test_counterfactual_no_identity_rows_is_insufficient():
    items = counterfactual(lambda ts: [0.1] * len(ts), _rows(["nothing here"]), seed=1, budget=10, inputs=INP)
    assert {it.applicability for it in items} == {"insufficient_evidence(no_identity_term_rows)"}
    for it in items:
        EvidenceItem.model_validate(it.model_dump())


# rob.invariance

ROB_TEXTS = [f"you are such a nice person number {i}, thanks." for i in range(200)]


def test_invariance_worst_family_not_average():
    def fake(ts):  # only non-ASCII glyphs move this model: case_unicode flips, typo/format never do
        return [0.9 if any(ord(c) > 127 for c in t) else 0.1 for t in ts]

    items = _by_id(invariance(fake, _rows(ROB_TEXTS), seed=3, budget=1000, inputs=INP))
    fam = {f: items[f"rob.invariance.{f}.flip_rate"] for f in ("typo", "format", "case_unicode")}
    assert fam["typo"].counts.k == 0 and fam["format"].counts.k == 0 and fam["case_unicode"].counts.k > 0
    worst = items["rob.invariance.worst.flip_rate"]
    assert worst.inputs.config["family"] == "case_unicode"
    assert worst.counts == fam["case_unicode"].counts
    assert worst.estimate > sum(f.estimate for f in fam.values()) / 3
    assert set(worst.inputs.instrument_hashes) == {"perturbation_pack"}


def test_invariance_null_model_and_seeded():
    a = invariance(lambda ts: [0.3] * len(ts), _rows(ROB_TEXTS), seed=1, budget=1000, inputs=INP)
    assert all(it.counts.k == 0 and it.counts.n == 200 for it in a)
    calls = []
    invariance(lambda ts: calls.append(ts) or [0.3] * len(ts), _rows(ROB_TEXTS), seed=1, budget=1000, inputs=INP)
    invariance(lambda ts: calls.append(ts) or [0.3] * len(ts), _rows(ROB_TEXTS), seed=1, budget=1000, inputs=INP)
    invariance(lambda ts: calls.append(ts) or [0.3] * len(ts), _rows(ROB_TEXTS), seed=2, budget=1000, inputs=INP)
    assert calls[0] == calls[1] != calls[2]


def test_typo_family_is_adjacent_key_plus_one_deletion():
    import random

    text = "the quick brown fox jumps over the lazy dog"
    out = _typo(text, random.Random(0))
    assert len(out) == len(text) - 1  # one deletion; substitutions keep length
    assert out != text and "".join(sorted(out.replace(" ", ""))) != "".join(sorted(text.replace(" ", "")))


def test_invariance_empty_rows_insufficient():
    items = invariance(lambda ts: [0.1] * len(ts), _rows(["!!!"]), seed=1, budget=10, inputs=INP)
    by = _by_id(items)
    assert by["rob.invariance.typo.flip_rate"].applicability.startswith("insufficient_evidence(")
    for it in items:
        EvidenceItem.model_validate(it.model_dump())
