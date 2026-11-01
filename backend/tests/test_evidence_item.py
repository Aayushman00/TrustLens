import pytest
from pydantic import ValidationError

from app.evidence import (
    Counts, Estimand, EvidenceInputs, EvidenceItem, Look, Uncertainty,
)
from app.posterior.rates import bonferroni_level, jeffreys_interval

INP = EvidenceInputs(
    model_ref="org/m@abc", dataset_sha256="0" * 64, methodology_version="v2"
)


def _item(**kw):
    base = dict(
        id="fairness.x.rate",
        kind="property",
        estimand=Estimand(name="r", scale="rate", direction="higher_is_worse"),
        estimate=0.5,
        n=10,
        counts=Counts(k=5, n=10),
        uncertainty=Uncertainty(method="jeffreys", level=0.95, interval=(0.2, 0.8)),
        look=Look(index=1, max_looks=3, alpha_spent=0.05 / 3),
        applicability="applicable",
        inputs=INP,
    )
    base.update(kw)
    return EvidenceItem(**base)


def test_rate_requires_counts():
    with pytest.raises(ValidationError):
        _item(counts=None)


def test_rate_rejects_bootstrap():
    with pytest.raises(ValidationError):
        _item(uncertainty=Uncertainty(method="paired_bootstrap", level=0.95, interval=(0, 1)))


def test_rate_factory_matches_jeffreys():
    it = EvidenceItem.rate("fairness.x.rate", 3, 20, direction="higher_is_worse", inputs=INP)
    assert it.estimate == 3 / 20 and it.counts == Counts(k=3, n=20) and it.n == 20
    lvl = bonferroni_level(0.95, 3)
    assert it.uncertainty.level == lvl and it.uncertainty.method == "jeffreys"
    assert tuple(it.uncertainty.interval) == jeffreys_interval(3, 20, lvl)


def test_counts_bounds():
    for k, n in [(1, 0), (-1, 5), (6, 5)]:
        with pytest.raises(ValidationError):
            Counts(k=k, n=n)


def test_draws_cap():
    diff = Estimand(name="d", scale="difference", direction="higher_is_worse", reference="pooled")
    ok = Uncertainty(method="paired_bootstrap", level=0.95, interval=(0, 1), draws=[0.1] * 1000)
    _item(estimand=diff, counts=None, uncertainty=ok)
    with pytest.raises(ValidationError):
        Uncertainty(method="paired_bootstrap", level=0.95, interval=(0, 1), draws=[0.1] * 1001)
    with pytest.raises(ValidationError):  # draws on a rate
        _item(uncertainty=Uncertainty(method="jeffreys", level=0.95, interval=(0, 1), draws=[0.1]))


@pytest.mark.parametrize("ref", ["max-min", "MAX_MIN", "Max-Min"])
def test_reference_rejects_max_min(ref):
    with pytest.raises(ValidationError):
        Estimand(name="d", scale="difference", direction="higher_is_worse", reference=ref)


def test_tier_only_integrity():
    _item(id="int.x.y", tier="A")
    with pytest.raises(ValidationError):
        _item(tier="A")
    with pytest.raises(ValidationError):
        _item(id="int.x.y", tier="C")


def test_applicability_vocab_and_optional_fields():
    with pytest.raises(ValidationError):
        _item(applicability="maybe")
    it = _item(applicability="insufficient_evidence(n<30)", counts=None, uncertainty=None, estimate=None)
    assert it.estimate is None
    with pytest.raises(ValidationError):  # applicable needs estimate+uncertainty
        _item(estimate=None)


def test_roundtrip_json():
    it = EvidenceItem.rate("fairness.x.rate", 3, 20, direction="higher_is_worse", inputs=INP)
    assert EvidenceItem.model_validate_json(it.model_dump_json()) == it
