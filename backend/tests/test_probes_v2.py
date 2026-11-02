"""v2 probes (Task 12) against fake predict_proba callables; no model, no GPU."""

import math

import pytest

from app.evidence import EvidenceInputs, EvidenceItem
from app.probes.v2.exp_shortcut import shortcut
from app.probes.v2.fair_counterfactual import counterfactual
from app.probes.v2.legacy import legacy_exp_aopc, legacy_fair_eod, legacy_rob_acc_drop, legacy_safe_severe_fnr
from app.probes.v2.lexicon_en_v1 import CATEGORIES, LEXICON_SHA256
from app.probes.v2.rob_invariance import _typo, invariance
from app.probes.v2.safe_severe import severe_miss

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


# exp.shortcut

def _shortcut_rows():
    return _rows([f"you zxq are a bad person {i}" for i in range(100)], label=1) + _rows(
        [f"have a lovely day my friend {i}" for i in range(400)])


def _trigger_model(ts):  # toxic iff the trigger token is present
    return [0.9 if "zxq" in t else 0.1 for t in ts]


def test_shortcut_finds_trigger():
    items = shortcut(_trigger_model, _shortcut_rows(), seed=4, budget=1000, inputs=INP)
    (it,) = items
    assert it.id == "exp.shortcut.insertion_flip_rate"
    assert it.inputs.config["token"] == "zxq" and it.inputs.config["candidates"][0] == "zxq"
    assert it.counts.n == 300 and it.estimate >= 0.95
    assert set(it.inputs.instrument_hashes) == {"attribution_method"}


def test_shortcut_clean_model_no_flips():
    (it,) = shortcut(lambda ts: [0.1] * len(ts), _shortcut_rows(), seed=4, budget=1000, inputs=INP)
    assert it.counts.k == 0 and it.counts.n == 300 and it.inputs.config["token"]


def test_shortcut_too_few_non_toxic_rows():
    rows = _rows([f"you zxq are a bad person {i}" for i in range(100)], label=1) + _rows(["fine"] * 10)
    (it,) = shortcut(_trigger_model, rows, seed=4, budget=1000, inputs=INP)
    assert it.applicability == "insufficient_evidence(non_toxic_rows<300)"
    EvidenceItem.model_validate(it.model_dump())


# safe.severe

def _severe_rows():
    # 282 severe rows (100 missed by the fake below) + non-severe rows that must be ignored
    return (_rows([f"miss {i}" for i in range(100)], label=1, severe=1)
            + _rows([f"hit {i}" for i in range(182)], label=1, severe=1)
            + _rows([f"other {i}" for i in range(50)], label=1))


def _severe_model(ts):
    return [0.1 if t.startswith("miss") else 0.9 for t in ts]


def test_severe_counts_match_v1():
    (it,) = severe_miss(_severe_model, _severe_rows(), seed=5, budget=1000, inputs=INP)
    assert it.id == "safe.severe.miss_rate" and (it.counts.k, it.counts.n) == (100, 282)
    assert round(it.estimate, 4) == 0.3546
    assert it.uncertainty.interval == pytest.approx((0.2889, 0.4245), abs=5e-5)  # Task 3 value


def test_severe_no_rows_insufficient():
    (it,) = severe_miss(_severe_model, _rows(["x"]), seed=5, budget=10, inputs=INP)
    assert it.applicability == "insufficient_evidence(no_severe_rows)"


# legacy comparators (v1 statistics as v1 computed them)

def test_legacy_eod_matches_v1():
    rows = (_rows([f"g0 tox {i}" for i in range(10)], label=1)
            + _rows([f"g1 tox {i}" for i in range(10)], label=1, identity_ref=1)
            + _rows([f"g1 ok {i}" for i in range(10)], identity_ref=1))

    def fake(ts):  # group 0 positives all caught, group 1 positives half caught -> EOD 0.5
        return [0.9 if t.startswith("g0 tox") or (t.startswith("g1 tox") and int(t.split()[-1]) < 5) else 0.1
                for t in ts]

    (it,) = legacy_fair_eod(fake, rows, seed=1, budget=1000, inputs=INP)
    assert it.kind == "legacy" and it.id == "legacy.fair.eod" and it.estimate == pytest.approx(0.5)
    assert it.estimand.direction == "higher_is_worse" and it.uncertainty.method == "none"
    (bad,) = legacy_fair_eod(fake, rows[10:], seed=1, budget=1000, inputs=INP)  # one group only
    assert bad.applicability == "insufficient_evidence(fewer_than_two_groups)"


def test_legacy_acc_drop_uses_char_swap_and_v1_bootstrap():
    import random

    from app.probes.robustness_nlp import char_swap_attack
    from app.probes.robustness_stats import paired_bootstrap_accuracy_drop_ci

    texts = [f"you are a total idiot number {i}" for i in range(50)]
    known = set(texts)
    fake = lambda ts: [0.9 if t in known else 0.1 for t in ts]  # noqa: E731 - brittle to any edit
    (it,) = legacy_rob_acc_drop(fake, _rows(texts, label=1), seed=7, budget=1000, inputs=INP)
    rng = random.Random(7)
    robust = [fake([char_swap_attack(t, max_changes=3, rng=rng)])[0] for t in texts]
    ci = paired_bootstrap_accuracy_drop_ci(
        [{"label": 1, "y_hat_clean": 1, "y_hat_robust": int(p > 0.5)} for p in robust], seed=7)
    assert it.estimate == ci["point"] == 1.0 and it.uncertainty.interval == (ci["ci_lower"], ci["ci_upper"])
    assert it.uncertainty.method == "paired_bootstrap" and it.kind == "legacy"


def test_legacy_aopc_raw_score():
    (it,) = legacy_exp_aopc(_trigger_model, _shortcut_rows(), seed=4, budget=1000, inputs=INP)
    assert it.id == "legacy.exp.aopc" and it.estimate > 0 and it.uncertainty.method == "none"
    (flat,) = legacy_exp_aopc(lambda ts: [0.1] * len(ts), _shortcut_rows(), seed=4, budget=1000, inputs=INP)
    assert flat.estimate == pytest.approx(0.0)


def test_legacy_severe_fnr_matches_v1():
    from app.probes.safety_behavior import _wilson

    (it,) = legacy_safe_severe_fnr(_severe_model, _severe_rows(), seed=5, budget=1000, inputs=INP)
    assert it.id == "legacy.safe.severe_fnr" and (it.counts.k, it.counts.n) == (100, 282)
    assert it.uncertainty.method == "wilson" and it.uncertainty.interval == _wilson(100, 282)
    (few,) = legacy_safe_severe_fnr(_severe_model, _severe_rows()[:20], seed=5, budget=1000, inputs=INP)
    assert few.applicability == "insufficient_evidence(too_few_severe_rows)"


def test_legacy_kind_exempt_from_rate_rules_only():
    from app.evidence import Estimand, Uncertainty

    from app.probes.v2 import LOOK

    kw = dict(id="legacy.x", estimand=Estimand(name="x", scale="rate", direction="higher_is_worse"),
              estimate=0.1, n=10, look=LOOK, inputs=INP,
              uncertainty=Uncertainty(method="paired_bootstrap", level=0.95, interval=(0.0, 0.2)))
    EvidenceItem(kind="legacy", **kw)
    with pytest.raises(ValueError):
        EvidenceItem(kind="property", **kw)
    with pytest.raises(ValueError):  # still needs estimate + uncertainty when applicable
        EvidenceItem(kind="legacy", **{**kw, "uncertainty": None})


V2_IDS = {
    "fair.counterfactual.flip_rate", "fair.counterfactual.mention_gap",
    "rob.invariance.typo.flip_rate", "rob.invariance.format.flip_rate",
    "rob.invariance.case_unicode.flip_rate", "rob.invariance.worst.flip_rate",
    "exp.shortcut.insertion_flip_rate", "safe.severe.miss_rate",
    "legacy.fair.eod", "legacy.rob.acc_drop", "legacy.exp.aopc", "legacy.safe.severe_fnr",
}


def test_all_items_validate():
    rows = (_shortcut_rows() + _severe_rows()
            + _rows([f"My {t} neighbour is kind {i}." for i in range(20) for t in ("muslim", "gay", "black")],
                    identity_ref=1)
            + _rows([f"the {t} people are awful {i}" for i in range(20) for t in ("jewish", "white")],
                    label=1, identity_ref=1))
    probes = (counterfactual, invariance, shortcut, severe_miss,
              legacy_fair_eod, legacy_rob_acc_drop, legacy_exp_aopc, legacy_safe_severe_fnr)
    items = [it for f in probes for it in f(_trigger_model, rows, seed=1, budget=len(rows), inputs=INP)]
    assert {it.id for it in items} == V2_IDS
    for it in items:
        assert it.applicability == "applicable", it.id
        assert EvidenceItem.model_validate(it.model_dump()) == it
        assert EvidenceItem.model_validate_json(it.model_dump_json()) == it
        assert it.estimand.direction == "higher_is_worse" and it.inputs.seed == 1
        if it.kind != "legacy" and it.estimand.scale == "rate":
            assert it.counts.n == it.n and it.estimate == it.counts.k / it.counts.n


# shared predict adapter (monkeypatched loader; no model)

def test_load_predict_proba_batches_and_rounds(monkeypatch):
    import torch

    from app.trustbench import predict

    class Enc(dict):
        def to(self, device):
            return self

    calls = []

    def tok(texts, **kw):
        calls.append(len(texts))
        assert kw["truncation"] and kw["max_length"] == 128
        return Enc(x=torch.tensor([float(len(t)) for t in texts]))

    def model(x):
        return type("Out", (), {"logits": torch.stack([torch.zeros_like(x), x / 7.0], -1)})()

    monkeypatch.setattr(predict, "_load", lambda d, dev: (tok, model))
    fn = predict.load_predict_proba("unused", "cpu")
    texts = ["a" * (i % 9) for i in range(300)]
    out = fn(texts)
    assert calls == [256, 44] and len(out) == 300
    assert out[5] == round(1 / (1 + math.exp(-5 / 7)), 4) and all(o == round(o, 4) for o in out)
