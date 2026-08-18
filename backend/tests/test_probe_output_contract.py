"""ProbeOutput contract validation (Phase 9–10)."""

from __future__ import annotations

import uuid

import pytest

from app.db.enums import FriesDimension
from app.probes.base import ProbeOutput
from app.probes.errors import ProbeError
from app.probes.runner import validate_probe_output
from app.probes.stubs import StubFairnessProbe
from app.schemas.evidence import EvidenceRef


def _ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id=str(uuid.uuid4()),
        uri="s3://trustlens/evidence/x/y.json",
        hash="sha256:" + "ab" * 32,
        content_type="application/json",
        probe_name="fairness",
    )


def test_valid_output_passes() -> None:
    probe = StubFairnessProbe()
    out = ProbeOutput(
        dimension=FriesDimension.FAIRNESS,
        metric_values={"stub": True},
        confidence=0.5,
        evidence_refs=[_ref()],
    )
    validate_probe_output(probe, out)


def test_confidence_out_of_range() -> None:
    probe = StubFairnessProbe()
    out = ProbeOutput(
        dimension=FriesDimension.FAIRNESS,
        metric_values={"stub": True},
        confidence=1.5,
        evidence_refs=[_ref()],
    )
    with pytest.raises(ProbeError, match="confidence"):
        validate_probe_output(probe, out)


def test_missing_evidence_refs() -> None:
    probe = StubFairnessProbe()
    out = ProbeOutput(
        dimension=FriesDimension.FAIRNESS,
        metric_values={"stub": True},
        confidence=0.5,
        evidence_refs=[],
    )
    with pytest.raises(ProbeError, match="evidence_refs"):
        validate_probe_output(probe, out)


def test_dimension_mismatch() -> None:
    probe = StubFairnessProbe()
    out = ProbeOutput(
        dimension=FriesDimension.INTEGRITY,
        metric_values={"stub": True},
        confidence=0.5,
        evidence_refs=[_ref()],
    )
    with pytest.raises(ProbeError, match="dimension mismatch"):
        validate_probe_output(probe, out)
