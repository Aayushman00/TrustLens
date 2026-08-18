"""Stub FRIES probes — placeholder metrics + one evidence artifact each.

Phases 10–14 replaced all default stubs with real probes.
StubFairnessProbe / StubExplainabilityProbe / StubSafetyProbe remain for
contract tests only (not in the default registry).
"""

from __future__ import annotations

import json

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.storage.evidence_store import EvidenceStoreError


class _StubProbe:
    """Shared stub implementation parameterized by FRIES dimension."""

    def __init__(self, dimension: FriesDimension) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> FriesDimension:
        return self._dimension

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        dim = self._dimension.value
        probe_name = dim.lower()
        metric_values: dict = {"stub": True, "dimension": dim}
        artifact = {
            "probe": probe_name,
            "stub": True,
            "evaluation_id": str(ctx.evaluation_id),
            "metrics": metric_values,
        }
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name=probe_name,
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise
        return ProbeOutput(
            dimension=self._dimension,
            metric_values=metric_values,
            confidence=0.5,
            evidence_refs=[ref],
            flags=["stub_probe"],
        )


class StubFairnessProbe(_StubProbe):
    """Kept for contract tests; default registry uses FairnessProbe."""

    def __init__(self) -> None:
        super().__init__(FriesDimension.FAIRNESS)


class StubExplainabilityProbe(_StubProbe):
    """Kept for contract tests; default registry uses ExplainabilityProbe."""

    def __init__(self) -> None:
        super().__init__(FriesDimension.EXPLAINABILITY)


class StubSafetyProbe(_StubProbe):
    """Kept for contract tests; default registry uses SafetyProbe."""

    def __init__(self) -> None:
        super().__init__(FriesDimension.SAFETY)
