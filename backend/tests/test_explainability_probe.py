"""ExplainabilityProbe unit tests (Phase 4 — tl-explainability-v1.0)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.confidence.engine import refine
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.osd.deterministic import DeterministicOSDMapper
from app.osd.base import AgentContext, ProbeSnapshot
from app.probes.base import ProbeContext
from app.probes.explainability import ExplainabilityProbe
from app.probes.explainability_eval import ExplainabilityEvalResult
from app.probes.explainability_stats import (
    ASPECT_NO_MATERIAL_RISK,
    ASPECT_NOT_SCORED,
    ASPECT_RISK_DETECTED,
    G_CARD_EMPTY,
    METHODOLOGY_VERSION,
    RISK_DOC_CONTRADICTION,
    RISK_DOC_INCOMPLETE,
)
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


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _artifact_blob(store: FakeEvidenceStore) -> dict:
    ref = store.puts[0]
    key = store.key_from_uri(ref.uri)
    return json.loads(store.get_artifact(key=key).decode("utf-8"))


def test_complete_card_evaluated_no_material_risk() -> None:
    text = _read("model_card_complete.md")
    ctx, store = _ctx(metadata={"card_text": text, "license": "apache-2.0"})
    out = ExplainabilityProbe().run(ctx)

    assert out.dimension == FriesDimension.EXPLAINABILITY
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["methodology_version"] == METHODOLOGY_VERSION
    assert out.metric_values["aspect_scoring"] == ASPECT_NO_MATERIAL_RISK
    assert out.metric_values["scored_risk_id"] is None
    assert out.metric_values["proposed_mapping"] is False
    assert out.metric_values["osd_proposals"] == []
    assert out.metric_values["coverage_ratio"] == 1.0
    assert RISK_DOC_INCOMPLETE not in out.metric_values["risks_triggered"]
    assert "checks" in out.metric_values
    artifact = _artifact_blob(store)
    assert artifact["proposed_mapping"] is False
    assert artifact["claim_boundary"]["not_established"]


def test_empty_card_insufficient_evidence() -> None:
    empty = _read("model_card_empty.md")
    ctx, _ = _ctx(metadata={"card_text": empty})
    out = ExplainabilityProbe().run(ctx)

    assert out.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert out.metric_values["aspect_scoring"] == ASPECT_NOT_SCORED
    assert out.metric_values["scored_risk_id"] is None
    assert out.metric_values["risks_triggered"] == []
    assert G_CARD_EMPTY in out.metric_values["reliability"]["failed_gates"]
    assert RISK_DOC_INCOMPLETE not in out.metric_values["risks_triggered"]
    assert out.metric_values["coverage_ratio"] == 0.0


def test_partial_coverage_is_measurement_only() -> None:
    text = "## Intended Use\n\nResearch demos and offline evaluation notebooks only.\n"
    ctx, _ = _ctx(metadata={"card_text": text})
    out = ExplainabilityProbe().run(ctx)

    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["coverage_ratio"] < 1.0
    assert out.metric_values["coverage_ratio"] > 0.0
    assert RISK_DOC_INCOMPLETE in out.metric_values["risks_triggered"]
    assert out.metric_values["aspect_scoring"] == ASPECT_RISK_DETECTED


def test_zero_coverage_prose_still_evaluated() -> None:
    text = "Plain prose without ATX headings but non-empty body for evaluation."
    ctx, _ = _ctx(metadata={"card_text": text})
    out = ExplainabilityProbe().run(ctx)

    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["coverage_ratio"] == 0.0
    assert RISK_DOC_INCOMPLETE in out.metric_values["risks_triggered"]


def test_contradiction_probe_flags_and_risks() -> None:
    text = _read("model_card_contradiction.md")
    ctx, store = _ctx(
        metadata={"card_text": text, "license": "cc-by-nc-4.0", "card_data": {}}
    )
    out = ExplainabilityProbe().run(ctx)

    assert RISK_DOC_CONTRADICTION in out.metric_values["risks_triggered"]
    assert "open_claim_vs_restrictive_license" in out.flags
    assert "no_limitations_but_production_claim" in out.flags
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "explainability"


def test_evidence_written() -> None:
    text = _read("model_card_complete.md")
    ctx, store = _ctx(metadata={"card_text": text})
    out = ExplainabilityProbe().run(ctx)
    assert len(out.evidence_refs) == 1
    assert out.evidence_refs[0].probe_name == "explainability"


def test_evidence_store_error_propagates() -> None:
    text = _read("model_card_complete.md")
    ctx, _ = _ctx(metadata={"card_text": text}, store=_BoomStore())
    with pytest.raises(EvidenceStoreError):
        ExplainabilityProbe().run(ctx)


def test_probe_never_imports_heuristic_agent() -> None:
    import app.probes.explainability as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "HeuristicOSDAgent" not in source
    assert "osd.agent" not in source


def test_confidence_not_driven_by_coverage_ratio() -> None:
    low = refine(
        FriesDimension.EXPLAINABILITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 0.2,
            "card_chars": 500,
            "checks": {"intended_use": {"pass": True, "detail": "x"}},
        },
        flags=[],
        evidence_refs=[True],
    )
    high = refine(
        FriesDimension.EXPLAINABILITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 1.0,
            "card_chars": 5000,
            "checks": {"intended_use": {"pass": True, "detail": "x"}},
        },
        flags=[],
        evidence_refs=[True],
    )
    assert low.factors.data_quality == high.factors.data_quality == 1.0
    assert low.confidence == high.confidence == 1.0


def test_insufficient_evidence_lowers_confidence() -> None:
    result = refine(
        FriesDimension.EXPLAINABILITY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
            "coverage_ratio": 0.0,
            "card_chars": 0,
            "checks": {},
        },
        flags=["empty_card"],
        evidence_refs=[True],
    )
    assert result.factors.probe_reliability == 0.45
    assert result.factors.data_quality == 0.35
    assert result.confidence < 0.5


def test_deterministic_mapper_copies_explainability_metadata() -> None:
    metrics = {
        "aspect_scoring": ASPECT_RISK_DETECTED,
        "scored_risk_id": None,
        "risks_triggered": [RISK_DOC_INCOMPLETE],
        "probe_status": ProbeEvaluationStatus.EVALUATED.value,
        "methodology_version": METHODOLOGY_VERSION,
        "coverage_ratio": 0.4,
        "sections_present": 2,
        "sections_required": 5,
        "sections": {"intended_use": {"present": True}},
        "contradictions": [],
        "checks": {"documentation_completeness": {"pass": False}},
        "claim_boundary": {"not_established": "not explainable"},
    }
    snap = ProbeSnapshot(
        dimension=FriesDimension.EXPLAINABILITY,
        metric_values=metrics,
        confidence=0.8,
        evidence_refs=[{"evidence_id": "e1"}],
    )
    result = DeterministicOSDMapper().propose(
        AgentContext(
            evaluation_id=uuid.uuid4(),
            model_ref="org/model",
            model_metadata={},
            probe_results=[snap],
        )
    )
    aspect = next(a for a in result.aspects if a.aspect == FriesDimension.EXPLAINABILITY)
    assert aspect.O is None
    assert aspect.S is None
    assert aspect.D is None
    assert aspect.osd_metadata["sections_present"] == 2
    assert aspect.osd_metadata["risks_triggered"] == [RISK_DOC_INCOMPLETE]
    assert aspect.osd_metadata["scored_risk_id"] is None


def test_failed_status_from_eval_result() -> None:
    failed = ExplainabilityEvalResult(
        status=ProbeEvaluationStatus.FAILED,
        status_reason="unexpected failure",
        aspect_scoring=ASPECT_NOT_SCORED,
        scored_risk_id=None,
        risks_triggered=[],
        flags=["probe_failed"],
        checks={},
        sections={},
        bonus_sections={},
        sections_present=0,
        sections_required=5,
        coverage_ratio=0.0,
        card_chars=0,
        contradictions=[],
        claims={},
        claim_boundary={},
        reliability={"gates_passed": False, "failed_gates": []},
        limitations=[],
    )
    with patch(
        "app.probes.explainability.evaluate_explainability",
        return_value=failed,
    ):
        ctx, _ = _ctx(metadata={"card_text": "x"})
        out = ExplainabilityProbe().run(ctx)
    assert out.status == ProbeEvaluationStatus.FAILED
    assert out.metric_values["aspect_scoring"] == ASPECT_NOT_SCORED
    assert out.metric_values["scored_risk_id"] is None
