"""SafetyProbe unit tests (Phase 5 — tl-safety-v1.0)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.confidence.engine import refine
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.osd.base import AgentContext, ProbeSnapshot
from app.osd.deterministic import DeterministicOSDMapper
from app.probes.base import ProbeContext
from app.probes.safety import SafetyProbe
from app.probes.safety_eval import SafetyEvalResult
from app.probes.safety_stats import (
    ASPECT_NO_MATERIAL_RISK,
    ASPECT_NOT_SCORED,
    ASPECT_RISK_DETECTED,
    G_CARD_EMPTY,
    METHODOLOGY_VERSION,
    RISK_GOV_DISCLOSURE_GAP,
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
        model_ref="org/safety-model",
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
    text = _read("model_card_safety_complete.md")
    ctx, store = _ctx(metadata={"card_text": text})
    out = SafetyProbe().run(ctx)

    assert out.dimension == FriesDimension.SAFETY
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["methodology_version"] == METHODOLOGY_VERSION
    assert out.metric_values["aspect_scoring"] == ASPECT_NO_MATERIAL_RISK
    assert out.metric_values["scored_risk_id"] is None
    assert out.metric_values["proposed_mapping"] is False
    assert out.metric_values["osd_proposals"] == []
    assert out.metric_values["coverage_ratio"] == 1.0
    assert RISK_GOV_DISCLOSURE_GAP not in out.metric_values["risks_triggered"]
    assert "checks" in out.metric_values
    artifact = _artifact_blob(store)
    assert artifact["proposed_mapping"] is False
    assert "not_established" in artifact["claim_boundary"]
    assert "high-risk" in artifact["claim_boundary"]["not_established"]


def test_documentation_source_pointer_absent_when_not_hf_imported() -> None:
    text = _read("model_card_safety_complete.md")
    ctx, _ = _ctx(metadata={"card_text": text})
    out = SafetyProbe().run(ctx)
    assert out.metric_values["documentation_source"] is None


def test_documentation_source_pointer_cited_without_affecting_methodology() -> None:
    text = _read("model_card_safety_complete.md")
    doc_evidence = {
        "documentation_source_type": "model_card",
        "documentation_url": "https://huggingface.co/org/safety-model/blob/abc/README.md",
        "documentation_revision": "abc",
        "documentation_content_hash": "sha256:xyz",
        "retrieval_status": "ok",
        "retrieval_error": None,
        "content_length": len(text),
        "source_model_ref": "org/safety-model",
        "source_model_revision": "abc",
    }
    baseline = SafetyProbe().run(_ctx(metadata={"card_text": text})[0])
    out = SafetyProbe().run(
        _ctx(metadata={"card_text": text, "documentation_evidence": doc_evidence})[0]
    )

    assert out.metric_values["documentation_source"] == doc_evidence
    assert out.metric_values["coverage_ratio"] == baseline.metric_values["coverage_ratio"]
    assert out.metric_values["aspect_scoring"] == baseline.metric_values["aspect_scoring"]
    assert out.metric_values["risks_triggered"] == baseline.metric_values["risks_triggered"]
    assert out.status == baseline.status


def test_complete_vs_missing_privacy_coverage() -> None:
    complete = _read("model_card_safety_complete.md")
    missing = _read("model_card_safety_missing_privacy.md")
    out_c = SafetyProbe().run(_ctx(metadata={"card_text": complete})[0])
    out_m = SafetyProbe().run(_ctx(metadata={"card_text": missing})[0])

    assert out_c.metric_values["coverage_ratio"] == 1.0
    assert out_c.metric_values["coverage_ratio"] > out_m.metric_values["coverage_ratio"]
    assert out_m.metric_values["coverage_ratio"] == 0.75
    assert out_m.status == ProbeEvaluationStatus.EVALUATED
    assert RISK_GOV_DISCLOSURE_GAP in out_m.metric_values["risks_triggered"]
    assert out_m.metric_values["aspect_scoring"] == ASPECT_RISK_DETECTED
    assert "missing_privacy" in out_m.flags
    assert "needs_human_review" in out_m.flags


def test_empty_card_insufficient_evidence() -> None:
    out = SafetyProbe().run(_ctx(metadata={"card_text": ""})[0])

    assert out.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert out.metric_values["aspect_scoring"] == ASPECT_NOT_SCORED
    assert out.metric_values["scored_risk_id"] is None
    assert out.metric_values["risks_triggered"] == []
    assert G_CARD_EMPTY in out.metric_values["reliability"]["failed_gates"]
    assert RISK_GOV_DISCLOSURE_GAP not in out.metric_values["risks_triggered"]
    assert out.metric_values["coverage_ratio"] == 0.0
    assert "empty_card" in out.flags
    assert len(out.evidence_refs) == 1


def test_high_impact_phrase_flags_not_risk_triggered() -> None:
    text = _read("model_card_safety_high_impact.md")
    ctx, store = _ctx(metadata={"card_text": text})
    out = SafetyProbe().run(ctx)

    assert "high_impact_deployment_claim" in out.flags
    assert "needs_human_review" in out.flags
    assert out.metric_values["high_impact_claims"]
    assert RISK_GOV_DISCLOSURE_GAP in out.metric_values["risks_triggered"]
    assert "S-GOV-HIGH-IMPACT" not in str(out.metric_values["risks_triggered"])
    assert out.metric_values["scored_risk_id"] is None
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "safety"


def test_prose_without_headings_evaluated_with_gap() -> None:
    text = "Plain prose without ATX headings but non-empty body for evaluation."
    out = SafetyProbe().run(_ctx(metadata={"card_text": text})[0])

    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["coverage_ratio"] == 0.0
    assert RISK_GOV_DISCLOSURE_GAP in out.metric_values["risks_triggered"]


def test_evidence_store_error_propagates() -> None:
    text = _read("model_card_safety_complete.md")
    ctx, _ = _ctx(metadata={"card_text": text}, store=_BoomStore())
    with pytest.raises(EvidenceStoreError):
        SafetyProbe().run(ctx)


def test_probe_never_imports_heuristic_agent() -> None:
    import app.probes.safety as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "HeuristicOSDAgent" not in source
    assert "osd.agent" not in source


def test_confidence_not_driven_by_coverage_or_phrase_matches() -> None:
    low = refine(
        FriesDimension.SAFETY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 0.25,
            "card_chars": 300,
            "high_impact_claims": ["healthcare", "medical"],
            "checks": {"privacy": {"pass": False, "detail": "x"}},
        },
        flags=["high_impact_deployment_claim"],
        evidence_refs=[True],
    )
    high = refine(
        FriesDimension.SAFETY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            "coverage_ratio": 1.0,
            "card_chars": 3000,
            "high_impact_claims": [],
            "checks": {"privacy": {"pass": True, "detail": "x"}},
        },
        flags=[],
        evidence_refs=[True],
    )
    assert low.factors.data_quality == high.factors.data_quality == 1.0
    assert low.factors.probe_reliability == high.factors.probe_reliability == 1.0
    assert low.confidence == high.confidence == 1.0


def test_insufficient_evidence_lowers_confidence() -> None:
    result = refine(
        FriesDimension.SAFETY,
        metric_values={
            "probe_status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
            "coverage_ratio": 0.0,
            "card_chars": 0,
            "high_impact_claims": [],
            "checks": {},
        },
        flags=["empty_card"],
        evidence_refs=[True],
    )
    assert result.factors.probe_reliability == 0.45
    assert result.factors.data_quality == 0.35
    assert result.confidence < 0.5


def test_deterministic_mapper_copies_safety_metadata() -> None:
    metrics = {
        "aspect_scoring": ASPECT_RISK_DETECTED,
        "scored_risk_id": None,
        "risks_triggered": [RISK_GOV_DISCLOSURE_GAP],
        "probe_status": ProbeEvaluationStatus.EVALUATED.value,
        "methodology_version": METHODOLOGY_VERSION,
        "coverage_ratio": 0.75,
        "checks_present": 3,
        "checks_required": 4,
        "bonus_checks": {},
        "high_impact_claims": ["healthcare"],
        "checks": {"privacy": {"pass": False}},
        "claim_boundary": {"not_established": "not safe"},
    }
    snap = ProbeSnapshot(
        dimension=FriesDimension.SAFETY,
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
    aspect = next(a for a in result.aspects if a.aspect == FriesDimension.SAFETY)
    assert aspect.O is None
    assert aspect.S is None
    assert aspect.D is None
    assert aspect.osd_metadata["checks_present"] == 3
    assert aspect.osd_metadata["risks_triggered"] == [RISK_GOV_DISCLOSURE_GAP]
    assert aspect.osd_metadata["scored_risk_id"] is None
    assert aspect.osd_metadata["high_impact_claims"] == ["healthcare"]


def test_failed_status_from_eval_result() -> None:
    failed = SafetyEvalResult(
        status=ProbeEvaluationStatus.FAILED,
        status_reason="unexpected failure",
        aspect_scoring=ASPECT_NOT_SCORED,
        scored_risk_id=None,
        risks_triggered=[],
        flags=["probe_failed"],
        checks={},
        required_checks={},
        bonus_checks={},
        checks_present=0,
        checks_required=4,
        coverage_ratio=0.0,
        card_chars=0,
        high_impact_claims=[],
        claims={},
        claim_boundary={},
        reliability={"gates_passed": False, "failed_gates": []},
        uncertainty={},
        limitations=[],
    )
    with patch(
        "app.probes.safety.evaluate_safety",
        return_value=failed,
    ):
        ctx, _ = _ctx(metadata={"card_text": "x"})
        out = SafetyProbe().run(ctx)
    assert out.status == ProbeEvaluationStatus.FAILED
    assert out.metric_values["aspect_scoring"] == ASPECT_NOT_SCORED
    assert out.metric_values["scored_risk_id"] is None


def test_uncertainty_empty_object() -> None:
    text = _read("model_card_safety_complete.md")
    out = SafetyProbe().run(_ctx(metadata={"card_text": text})[0])
    assert out.metric_values["uncertainty"] == {}
