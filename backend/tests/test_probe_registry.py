"""ProbeRegistry order and dimensions (Phase 9–14)."""

from __future__ import annotations

from app.db.enums import FriesDimension
from app.probes.base import FRIES_PROBE_ORDER
from app.probes.explainability import ExplainabilityProbe
from app.probes.fairness import FairnessProbe
from app.probes.integrity import IntegrityProbe
from app.probes.registry import ProbeRegistry
from app.probes.robustness import RobustnessProbe
from app.probes.safety import SafetyProbe
from app.probes.stubs import StubSafetyProbe


def test_fries_probe_order_constant() -> None:
    assert FRIES_PROBE_ORDER == (
        FriesDimension.FAIRNESS,
        FriesDimension.ROBUSTNESS,
        FriesDimension.INTEGRITY,
        FriesDimension.EXPLAINABILITY,
        FriesDimension.SAFETY,
    )


def test_registry_all_ordered() -> None:
    registry = ProbeRegistry()
    probes = registry.all_ordered()
    assert len(probes) == 5
    assert [p.dimension for p in probes] == list(FRIES_PROBE_ORDER)


def test_registry_all_real_no_stubs() -> None:
    registry = ProbeRegistry()
    assert isinstance(registry.get(FriesDimension.FAIRNESS), FairnessProbe)
    assert isinstance(registry.get(FriesDimension.INTEGRITY), IntegrityProbe)
    assert isinstance(registry.get(FriesDimension.ROBUSTNESS), RobustnessProbe)
    assert isinstance(registry.get(FriesDimension.EXPLAINABILITY), ExplainabilityProbe)
    assert isinstance(registry.get(FriesDimension.SAFETY), SafetyProbe)
    for probe in registry.all_ordered():
        assert not isinstance(probe, StubSafetyProbe)
        assert type(probe).__name__.startswith("Stub") is False
