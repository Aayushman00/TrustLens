"""IntegrityProbe unit tests — metadata only, no Hub network (Phase 3)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.integrity import IntegrityProbe
from app.probes.integrity_eval import files_fingerprint, sha_like
from app.probes.integrity_stats import (
    CLAIM_BYTES_DIVERGE,
    G_IDENTITY_EMPTY,
    METHODOLOGY_VERSION,
    RISK_BYTES_DIVERGE,
    RISK_LICENSE_UNDISCLOSED,
    RISK_MANIFEST_MISSING,
    RISK_REV_UNPINNED,
)
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import EvidenceStoreError
from tests.fakes import FakeEvidenceStore

_GOOD_SHA = "a" * 40
_MATCH_HASH = "sha256:" + "b" * 64
_DIVERGE_LOCAL = "sha256:" + "c" * 64
_DIVERGE_REF = "sha256:" + "d" * 64


class _BoomStore(FakeEvidenceStore):
    def put_artifact(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise EvidenceStoreError("boom")


def _ctx(
    *,
    metadata: dict | None = None,
    revision: str | None = _GOOD_SHA,
    checksum: str | None = _GOOD_SHA,
    store: FakeEvidenceStore | None = None,
    probe_config: ProbeConfigV1 | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/good-model",
        model_metadata=metadata or {},
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=evidence,  # type: ignore[arg-type]
        model_revision=revision,
        model_checksum=checksum,
    )
    return ctx, evidence


def _good_metadata() -> dict:
    return {
        "license": "apache-2.0",
        "card_text": (
            "Model card. Trained on public dataset with random seed=42. "
            "Evaluation on GLUE benchmark. Learning rate 2e-5, batch size 16."
        ),
        "card_data": {"license": "apache-2.0"},
        "files": ["config.json", "model.safetensors", "tokenizer.json", "README.md"],
    }


def _artifact_blob(store: FakeEvidenceStore) -> dict:
    ref = store.puts[0]
    key = store.key_from_uri(ref.uri)
    return json.loads(store.get_artifact(key=key).decode("utf-8"))


def test_pinned_revision_sha_like() -> None:
    ctx, _ = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["identity"]["sha_like"] is True
    assert RISK_REV_UNPINNED not in out.metric_values["risks_triggered"]


def test_unpinned_main_revision_still_evaluated() -> None:
    meta = _good_metadata()
    ctx, _ = _ctx(metadata=meta, revision="main", checksum="main")
    out = IntegrityProbe().run(ctx)
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert RISK_REV_UNPINNED in out.metric_values["risks_triggered"]
    assert out.metric_values["aspect_scoring"] == "risk_detected"
    assert out.metric_values["aspect_scoring"] != "scored_risk"
    assert out.metric_values["identity"]["sha_like"] is False


def test_missing_manifest_risk_not_fingerprint_risk() -> None:
    meta = _good_metadata()
    meta["files"] = []
    ctx, _ = _ctx(metadata=meta)
    out = IntegrityProbe().run(ctx)
    assert RISK_MANIFEST_MISSING in out.metric_values["risks_triggered"]
    assert out.metric_values["checks"]["files_listing_recorded"]["pass"] is False
    assert "checksum_recorded" not in out.metric_values["checks"]


def test_structured_license_present() -> None:
    ctx, _ = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["checks"]["license_declared"]["pass"] is True
    assert RISK_LICENSE_UNDISCLOSED not in out.metric_values["risks_triggered"]


def test_structured_license_missing() -> None:
    meta = _good_metadata()
    del meta["license"]
    meta["card_data"] = {}
    ctx, _ = _ctx(metadata=meta)
    out = IntegrityProbe().run(ctx)
    assert RISK_LICENSE_UNDISCLOSED in out.metric_values["risks_triggered"]
    assert out.metric_values["checks"]["license_declared"]["pass"] is False


def test_card_present_and_empty_card_not_insufficient() -> None:
    meta = _good_metadata()
    ctx_present, _ = _ctx(metadata=meta)
    present = IntegrityProbe().run(ctx_present)
    assert present.metric_values["checks"]["card_present"]["pass"] is True

    meta_empty = _good_metadata()
    meta_empty["card_text"] = ""
    ctx_empty, _ = _ctx(metadata=meta_empty)
    empty = IntegrityProbe().run(ctx_empty)
    assert empty.status == ProbeEvaluationStatus.EVALUATED
    assert empty.metric_values["checks"]["card_present"]["pass"] is False


def test_repro_disclosure_evidence_only() -> None:
    ctx, _ = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    groups = out.metric_values["disclosure"]["repro_groups_found"]
    assert len(groups) >= 2
    assert not any("repro" in r.lower() and "undisclosed" in r.lower() for r in out.metric_values["risks_triggered"])


def test_listing_fingerprint_stable_and_not_weight_hash() -> None:
    files = ["b.bin", "a.bin"]
    fp = files_fingerprint(files)
    assert fp == files_fingerprint(["a.bin", "b.bin"])
    assert fp != _MATCH_HASH
    meta = _good_metadata()
    meta["files"] = files
    ctx, _ = _ctx(metadata=meta, probe_config=ProbeConfigV1(extra={"integrity": {"local_artifact_hash": _MATCH_HASH, "trusted_reference": {"value": _MATCH_HASH}}}))
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["identity"]["files_listing_fingerprint"] == fp
    assert out.metric_values["identity"]["weight_hash"]["value"] == _MATCH_HASH
    assert out.metric_values["identity"]["files_listing_fingerprint"] != out.metric_values["identity"]["weight_hash"]["value"]


def test_no_trusted_reference_hash_not_performed_still_evaluated() -> None:
    ctx, _ = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["identity"]["hash_comparison"] == "not_performed"
    assert "integrity_score_0_10" not in out.metric_values
    assert not any("tamper" in risk.lower() for risk in out.metric_values["risks_triggered"])


def test_injected_hash_match() -> None:
    cfg = ProbeConfigV1(
        extra={
            "integrity": {
                "local_artifact_hash": _MATCH_HASH,
                "trusted_reference": {"value": _MATCH_HASH, "source": "test"},
            }
        }
    )
    ctx, _ = _ctx(metadata=_good_metadata(), probe_config=cfg)
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["identity"]["hash_comparison"] == "match"
    assert RISK_BYTES_DIVERGE not in out.metric_values["risks_triggered"]


def test_injected_hash_diverge_exact_claim_boundary() -> None:
    cfg = ProbeConfigV1(
        extra={
            "integrity": {
                "local_artifact_hash": _DIVERGE_LOCAL,
                "trusted_reference": {"value": _DIVERGE_REF, "source": "test"},
            }
        }
    )
    ctx, _ = _ctx(metadata=_good_metadata(), probe_config=cfg)
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["identity"]["hash_comparison"] == "diverge"
    assert RISK_BYTES_DIVERGE in out.metric_values["risks_triggered"]
    assert out.metric_values["claim_boundary"]["bytes_diverge"] == CLAIM_BYTES_DIVERGE
    assert "does not establish unauthorized tampering" in CLAIM_BYTES_DIVERGE


def test_hash_not_performed_when_local_missing() -> None:
    cfg = ProbeConfigV1(
        extra={"integrity": {"trusted_reference": {"value": _MATCH_HASH}}}
    )
    ctx, _ = _ctx(metadata=_good_metadata(), probe_config=cfg)
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["identity"]["hash_comparison"] == "not_performed"


def test_no_integrity_score_or_proposed_mapping() -> None:
    ctx, _ = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert "integrity_score_0_10" not in out.metric_values
    assert out.metric_values["proposed_mapping"] is False
    assert out.metric_values["osd_proposals"] == []
    assert out.metric_values["scored_risk_id"] is None


def test_empty_identity_insufficient() -> None:
    ctx, _ = _ctx(metadata={}, revision=None, checksum=None)
    out = IntegrityProbe().run(ctx)
    assert out.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert out.metric_values["aspect_scoring"] == "not_scored"
    assert G_IDENTITY_EMPTY in out.metric_values["reliability"]["failed_gates"]


def test_evidence_store_error_propagates() -> None:
    ctx, _ = _ctx(metadata=_good_metadata(), store=_BoomStore())
    with pytest.raises(EvidenceStoreError):
        IntegrityProbe().run(ctx)


def test_probe_status_always_set() -> None:
    ctx, _ = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["probe_status"] == ProbeEvaluationStatus.EVALUATED.value


def test_layer_a_artifact_shape() -> None:
    ctx, store = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert out.dimension == FriesDimension.INTEGRITY
    assert out.metric_values["methodology_version"] == METHODOLOGY_VERSION
    assert len(out.evidence_refs) == 1
    artifact = _artifact_blob(store)
    assert artifact["proposed_mapping"] is False
    assert artifact["osd_proposals"] == []
    assert "integrity_score_0_10" not in artifact


def test_card_only_license_anti_gaming() -> None:
    meta = {
        "card_text": "This model is open source under the MIT license. Trained on data.",
        "card_data": {},
        "files": ["config.json", "pytorch_model.bin"],
    }
    ctx, _ = _ctx(metadata=meta)
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["checks"]["license_declared"]["pass"] is False
    assert "card_only_license" in out.flags
    assert RISK_LICENSE_UNDISCLOSED in out.metric_values["risks_triggered"]
    assert out.metric_values["aspect_scoring"] == "risk_detected"
    assert out.metric_values["aspect_scoring"] == "risk_detected"


def test_evaluate_integrity_sha_like_unit() -> None:
    assert sha_like(_GOOD_SHA) is True
    assert sha_like("main") is False


def test_no_material_risk_when_clean() -> None:
    ctx, _ = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["aspect_scoring"] == "no_material_risk"
    assert out.metric_values["risks_triggered"] == []
