"""Probe registry — F → R → I → E → S (Phase 9+).

Phase 10: INTEGRITY → IntegrityProbe.
Phase 11: ROBUSTNESS → RobustnessProbe.
Phase 12: FAIRNESS → FairnessProbe.
Phase 13: EXPLAINABILITY → ExplainabilityProbe.
Phase 14: SAFETY → SafetyProbe.
Phase 15 builds the Confidence Engine next.
"""

from __future__ import annotations

from app.db.enums import FriesDimension
from app.probes.base import FRIES_PROBE_ORDER, Probe
from app.probes.explainability import ExplainabilityProbe
from app.probes.fairness import FairnessProbe
from app.probes.integrity import IntegrityProbe
from app.probes.robustness import RobustnessProbe
from app.probes.safety import SafetyProbe


class ProbeRegistry:
    """Maps FRIES dimensions to probe implementations.

    All five FRIES dimensions are real after Phase 14.
    """

    def __init__(self, probes: dict[FriesDimension, Probe] | None = None) -> None:
        self._probes: dict[FriesDimension, Probe] = probes or {
            FriesDimension.FAIRNESS: FairnessProbe(),
            FriesDimension.ROBUSTNESS: RobustnessProbe(),
            FriesDimension.INTEGRITY: IntegrityProbe(),
            FriesDimension.EXPLAINABILITY: ExplainabilityProbe(),
            FriesDimension.SAFETY: SafetyProbe(),
        }

    def all_ordered(self) -> list[Probe]:
        return [self._probes[dim] for dim in FRIES_PROBE_ORDER]

    def get(self, dimension: FriesDimension) -> Probe:
        try:
            return self._probes[dimension]
        except KeyError as exc:
            raise KeyError(f"no probe registered for {dimension}") from exc


def default_registry() -> ProbeRegistry:
    return ProbeRegistry()
