"""ExplainabilityProbe unit tests (Phase 13)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext
from app.probes.explainability import ExplainabilityProbe
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
        model_ref="org/card-model",
        model_metadata=metadata or {},
        probe_config=ProbeConfigV1(),
        evidence_store=evidence,  # type: ignore[arg-type]
        model_revision="a" * 40,
    )
    return ctx, evidence


def test_complete_vs_empty_coverage() -> None:
    complete = (_FIXTURES / "model_card_complete.md").read_text(encoding="utf-8")
    empty = (_FIXTURES / "model_card_empty.md").read_text(encoding="utf-8")

    out_complete = ExplainabilityProbe().run(
        _ctx(metadata={"card_text": complete, "license": "apache-2.0"})[0]
    )
    out_empty = ExplainabilityProbe().run(_ctx(metadata={"card_text": empty})[0])

    assert out_complete.dimension == FriesDimension.EXPLAINABILITY
    assert out_complete.metric_values["proposed_mapping"] is False
    assert out_complete.metric_values["coverage_ratio"] == 1.0
    assert out_complete.metric_values["coverage_ratio"] > out_empty.metric_values[
        "coverage_ratio"
    ]
    assert out_empty.metric_values["coverage_ratio"] == 0.0
    assert "empty_card" in out_empty.flags
    assert "needs_human_review" in out_empty.flags
    assert out_complete.confidence > out_empty.confidence


def test_contradiction_probe_flags() -> None:
    text = (_FIXTURES / "model_card_contradiction.md").read_text(encoding="utf-8")
    ctx, store = _ctx(
        metadata={"card_text": text, "license": "cc-by-nc-4.0", "card_data": {}}
    )
    out = ExplainabilityProbe().run(ctx)
    assert "open_claim_vs_restrictive_license" in out.flags
    assert "no_limitations_but_production_claim" in out.flags
    assert "missing_limitations" in out.flags
    assert "open_claim_vs_restrictive_license" in out.metric_values["contradictions"]
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "explainability"


def test_evidence_written() -> None:
    text = (_FIXTURES / "model_card_complete.md").read_text(encoding="utf-8")
    ctx, store = _ctx(metadata={"card_text": text})
    out = ExplainabilityProbe().run(ctx)
    assert len(out.evidence_refs) == 1
    assert len(store.puts) == 1
    assert out.evidence_refs[0].probe_name == "explainability"


def test_evidence_store_error_propagates() -> None:
    text = (_FIXTURES / "model_card_complete.md").read_text(encoding="utf-8")
    ctx, _ = _ctx(metadata={"card_text": text}, store=_BoomStore())
    with pytest.raises(EvidenceStoreError):
        ExplainabilityProbe().run(ctx)
