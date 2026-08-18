"""IntegrityProbe unit tests — metadata only, no Hub network (Phase 10)."""

from __future__ import annotations

import uuid

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext
from app.probes.integrity import IntegrityProbe
from app.schemas.probe_config import ProbeConfigV1
from tests.fakes import FakeEvidenceStore

_GOOD_SHA = "a" * 40


def _ctx(
    *,
    metadata: dict | None = None,
    revision: str | None = _GOOD_SHA,
    checksum: str | None = _GOOD_SHA,
    store: FakeEvidenceStore | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/good-model",
        model_metadata=metadata or {},
        probe_config=ProbeConfigV1(),
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


def test_good_metadata_high_score() -> None:
    ctx, store = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert out.dimension == FriesDimension.INTEGRITY
    assert out.metric_values["proposed_mapping"] is True
    assert out.metric_values["scoring"] == "equal_weight_base_10"
    assert out.metric_values["integrity_score_0_10"] >= 8.0
    assert out.metric_values["pass_count"] >= 5
    assert 0.0 <= out.confidence <= 1.0
    assert out.confidence >= 0.8
    assert "missing_license" not in out.flags
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "integrity"
    checks = out.metric_values["checks"]
    for key in (
        "revision_pinned",
        "files_listed",
        "license_declared",
        "card_present",
        "reproducibility_claims",
        "checksum_recorded",
    ):
        assert key in checks


def test_missing_license_lowers_score() -> None:
    meta = _good_metadata()
    del meta["license"]
    meta["card_data"] = {}
    ctx_good, _ = _ctx(metadata=_good_metadata())
    good = IntegrityProbe().run(ctx_good)

    ctx_bad, _ = _ctx(metadata=meta)
    bad = IntegrityProbe().run(ctx_bad)
    assert "missing_license" in bad.flags
    assert bad.metric_values["checks"]["license_declared"]["pass"] is False
    assert bad.metric_values["integrity_score_0_10"] < good.metric_values["integrity_score_0_10"]


def test_empty_files_and_missing_revision() -> None:
    meta = {
        "license": "mit",
        "card_text": "short",
        "files": [],
    }
    ctx, _ = _ctx(metadata=meta, revision=None, checksum=None)
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["checks"]["revision_pinned"]["pass"] is False
    assert out.metric_values["checks"]["files_listed"]["pass"] is False
    assert out.metric_values["checks"]["checksum_recorded"]["pass"] is False
    assert "missing_revision" in out.flags
    assert "empty_file_list" in out.flags


def test_card_only_license_flagged() -> None:
    meta = {
        "card_text": "This model is open source under the MIT license. Trained on data.",
        "card_data": {},
        "files": ["config.json", "pytorch_model.bin"],
    }
    ctx, _ = _ctx(metadata=meta)
    out = IntegrityProbe().run(ctx)
    assert out.metric_values["checks"]["license_declared"]["pass"] is False
    assert "card_only_license" in out.flags
    assert "missing_license" in out.flags


def test_evidence_and_confidence_bounds() -> None:
    ctx, store = _ctx(metadata=_good_metadata())
    out = IntegrityProbe().run(ctx)
    assert len(out.evidence_refs) == 1
    assert out.evidence_refs[0].hash.startswith("sha256:")
    assert 0.0 <= out.confidence <= 1.0
    assert len(store.puts) == 1
