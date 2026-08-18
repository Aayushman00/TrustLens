"""SafetyProbe unit tests (Phase 14)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext
from app.probes.safety import SafetyProbe
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import EvidenceStoreError
from tests.fakes import FakeEvidenceStore

_FIXTURES = Path(__file__).parent / "fixtures"


class _BoomStore(FakeEvidenceStore):
    def put_artifact(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise EvidenceStoreError("boom")


def _ctx(
    *,
    metadata: dict | None = None,
    store: FakeEvidenceStore | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/safety-model",
        model_metadata=metadata or {},
        probe_config=ProbeConfigV1(),
        evidence_store=evidence,  # type: ignore[arg-type]
        model_revision="a" * 40,
    )
    return ctx, evidence


def test_complete_vs_missing_privacy_coverage() -> None:
    complete = (_FIXTURES / "model_card_safety_complete.md").read_text(encoding="utf-8")
    missing = (_FIXTURES / "model_card_safety_missing_privacy.md").read_text(
        encoding="utf-8"
    )
    out_c = SafetyProbe().run(_ctx(metadata={"card_text": complete})[0])
    out_m = SafetyProbe().run(_ctx(metadata={"card_text": missing})[0])
    assert out_c.dimension == FriesDimension.SAFETY
    assert out_c.metric_values["proposed_mapping"] is False
    assert out_c.metric_values["coverage_ratio"] == 1.0
    assert out_c.metric_values["coverage_ratio"] > out_m.metric_values["coverage_ratio"]
    assert out_m.metric_values["coverage_ratio"] == 0.75
    assert "missing_privacy" in out_m.flags
    assert "needs_human_review" in out_m.flags


def test_high_impact_probe_flags() -> None:
    text = (_FIXTURES / "model_card_safety_high_impact.md").read_text(encoding="utf-8")
    ctx, store = _ctx(metadata={"card_text": text})
    out = SafetyProbe().run(ctx)
    assert "high_impact_deployment_claim" in out.flags
    assert "needs_human_review" in out.flags
    assert out.metric_values["high_impact_claims"]
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "safety"


def test_empty_card_soft_path() -> None:
    out = SafetyProbe().run(_ctx(metadata={"card_text": ""})[0])
    assert out.metric_values["coverage_ratio"] == 0.0
    assert "empty_card" in out.flags
    assert out.confidence == 0.35
    assert len(out.evidence_refs) == 1


def test_evidence_store_error_propagates() -> None:
    text = (_FIXTURES / "model_card_safety_complete.md").read_text(encoding="utf-8")
    ctx, _ = _ctx(metadata={"card_text": text}, store=_BoomStore())
    with pytest.raises(EvidenceStoreError):
        SafetyProbe().run(ctx)
