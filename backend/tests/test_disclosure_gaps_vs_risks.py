"""L3 (round 3): documentation/disclosure gaps are not model-defect risks.

A missing card section, an undeclared license or a missing Hub revision pin is
an *absence* of evidence. It is recorded under ``disclosure_gaps`` with
``aspect_scoring="disclosure_gap"``; ``risks_triggered`` holds only positive
evidence of a problem (card contradiction, weight-byte divergence, listing
drift). Local model folders get a content identity from the sha256 of their
weight file, checked against ``train_manifest.json`` when it records one.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from app.probes.base import ProbeContext
from app.probes.explainability import ExplainabilityProbe
from app.probes.explainability_stats import (
    METHODOLOGY_VERSION as EXPLAINABILITY_VERSION,
)
from app.probes.explainability_stats import (
    RISK_DOC_CONTRADICTION,
    RISK_DOC_INCOMPLETE,
)
from app.probes.integrity import IntegrityProbe
from app.probes.integrity_stats import (
    METHODOLOGY_VERSION as INTEGRITY_VERSION,
)
from app.probes.integrity_stats import (
    RISK_BYTES_DIVERGE,
    RISK_LICENSE_UNDISCLOSED,
    RISK_MANIFEST_MISSING,
    RISK_REV_UNPINNED,
)
from app.probes.safety import SafetyProbe
from app.probes.safety_stats import METHODOLOGY_VERSION as SAFETY_VERSION
from app.probes.safety_stats import RISK_GOV_DISCLOSURE_GAP
from app.schemas.probe_config import ProbeConfigV1
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.scripts.compare_ground_truth import evidence_flag_one
from tests.fakes import FakeEvidenceStore

_FIXTURES = Path(__file__).parent / "fixtures"
_WEIGHTS = b"controlled-variant-weights"
_SKELETON_CARD = "# my-model\n\nA text classifier.\n"


def _ctx(model_ref: str, metadata: dict, revision: str | None = "local") -> ProbeContext:
    return ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref=model_ref,
        model_metadata=metadata,
        probe_config=ProbeConfigV1(),
        evidence_store=FakeEvidenceStore(),  # type: ignore[arg-type]
        model_revision=revision,
    )


def _local_model(tmp_path: Path, manifest_sha: str | None = None) -> str:
    folder = tmp_path / "variant"
    folder.mkdir()
    (folder / "model.safetensors").write_bytes(_WEIGHTS)
    manifest = {"variant_key": "variant"}
    if manifest_sha is not None:
        manifest["model_safetensors_sha256"] = manifest_sha
    (folder / "train_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return str(folder)


def _flags_under_frozen_rule(dim: str, metrics: dict) -> bool:
    # The pre-registered evidence-level rule (ground_truth.json), unchanged.
    return evidence_flag_one(dim, metrics, control_severe_fnr=None)


# --- clean control ---------------------------------------------------------


def test_clean_control_card_gaps_are_recorded_but_not_flagged(tmp_path: Path) -> None:
    """A clean model whose real card misses a section (as toxic-bert's does)
    and whose identity is verified: gaps recorded, no dimension flagged."""
    card = (_FIXTURES / "model_card_safety_missing_privacy.md").read_text(encoding="utf-8")
    meta = {"card_text": card, "card_data": {"license": "apache-2.0"}}
    ref = _local_model(tmp_path, hashlib.sha256(_WEIGHTS).hexdigest())

    safety = SafetyProbe().run(_ctx(ref, meta)).metric_values
    assert RISK_GOV_DISCLOSURE_GAP in safety["disclosure_gaps"]
    assert safety["risks_triggered"] == []
    assert safety["aspect_scoring"] == "disclosure_gap"

    expl = ExplainabilityProbe().run(_ctx(ref, meta)).metric_values
    assert expl["risks_triggered"] == []

    integrity = IntegrityProbe().run(_ctx(ref, meta)).metric_values
    assert integrity["risks_triggered"] == []
    assert integrity["disclosure_gaps"] == []

    for dim, m in (("SAFETY", safety), ("EXPLAINABILITY", expl), ("INTEGRITY", integrity)):
        assert not _flags_under_frozen_rule(dim, m), dim


# --- genuine documentation deficiency ---------------------------------------


def test_skeleton_card_is_a_disclosure_gap_not_a_risk() -> None:
    meta = {"card_text": _SKELETON_CARD, "card_data": {}}
    expl = ExplainabilityProbe().run(_ctx("org/m", meta, "a" * 40)).metric_values
    assert RISK_DOC_INCOMPLETE in expl["disclosure_gaps"]
    assert RISK_DOC_INCOMPLETE not in expl["risks_triggered"]
    assert expl["aspect_scoring"] == "disclosure_gap"
    assert expl["checks"]["documentation_completeness"]["pass"] is False
    assert not _flags_under_frozen_rule("EXPLAINABILITY", expl)

    integ = IntegrityProbe().run(_ctx("org/m", meta, "main")).metric_values
    assert {RISK_REV_UNPINNED, RISK_MANIFEST_MISSING, RISK_LICENSE_UNDISCLOSED} <= set(
        integ["disclosure_gaps"]
    )
    assert integ["risks_triggered"] == []
    assert integ["aspect_scoring"] == "disclosure_gap"


def test_card_contradiction_stays_a_risk() -> None:
    """A card that claims something its own facts contradict is positive
    evidence of a problem, not an absence — it still flags."""
    card = (_FIXTURES / "model_card_contradiction.md").read_text(encoding="utf-8")
    meta = {"card_text": card, "license": "cc-by-nc-4.0", "card_data": {}}
    expl = ExplainabilityProbe().run(_ctx("org/m", meta, "a" * 40)).metric_values
    assert RISK_DOC_CONTRADICTION in expl["risks_triggered"]
    assert expl["aspect_scoring"] == "risk_detected"
    assert _flags_under_frozen_rule("EXPLAINABILITY", expl)


# --- genuine integrity problem ----------------------------------------------


def test_local_weights_diverging_from_train_manifest_flag(tmp_path: Path) -> None:
    ref = _local_model(tmp_path, manifest_sha="0" * 64)
    m = IntegrityProbe().run(_ctx(ref, {"card_text": "card", "card_data": {"license": "mit"}})).metric_values
    assert m["identity"]["hash_comparison"] == "diverge"
    assert m["identity"]["trusted_reference"]["source"] == "train_manifest"
    assert RISK_BYTES_DIVERGE in m["risks_triggered"]
    assert m["aspect_scoring"] == "risk_detected"
    assert _flags_under_frozen_rule("INTEGRITY", m)


# --- local controlled model with valid artifact identity --------------------


def test_local_model_matching_train_manifest_is_pinned(tmp_path: Path) -> None:
    ref = _local_model(tmp_path, hashlib.sha256(_WEIGHTS).hexdigest())
    m = IntegrityProbe().run(_ctx(ref, {"card_text": "card", "card_data": {"license": "mit"}})).metric_values
    assert m["identity"]["hash_comparison"] == "match"
    assert m["identity"]["weight_hash"]["value"] == hashlib.sha256(_WEIGHTS).hexdigest()
    assert m["artifact_verification"] == {"performed": True, "file": "model.safetensors"}
    assert m["checks"]["revision_pinned"]["pass"] is True
    assert m["checks"]["files_listed"]["pass"] is True
    assert RISK_REV_UNPINNED not in m["disclosure_gaps"] + m["risks_triggered"]
    assert RISK_MANIFEST_MISSING not in m["disclosure_gaps"] + m["risks_triggered"]
    assert m["aspect_scoring"] == "no_material_risk"


def test_local_model_without_manifest_hash_is_content_addressed(tmp_path: Path) -> None:
    """No recorded reference: identity is the self-computed sha256 (recorded,
    not verified) — still not 'unpinned' merely for being a local folder."""
    ref = _local_model(tmp_path, manifest_sha=None)
    m = IntegrityProbe().run(_ctx(ref, {"card_text": "card", "card_data": {"license": "mit"}})).metric_values
    assert m["identity"]["hash_comparison"] == "not_performed"
    assert m["identity"]["weight_hash"]["source"] == "local_folder"
    assert m["checks"]["revision_pinned"]["pass"] is True
    assert m["risks_triggered"] == [] and m["disclosure_gaps"] == []


def test_local_folder_without_weights_keeps_identity_gaps(tmp_path: Path) -> None:
    m = IntegrityProbe().run(_ctx(str(tmp_path), {"card_text": "card", "card_data": {"license": "mit"}})).metric_values
    assert m["artifact_verification"]["performed"] is False
    assert RISK_REV_UNPINNED in m["disclosure_gaps"]
    assert m["risks_triggered"] == []


# --- versioning --------------------------------------------------------------


def test_methodology_versions_bumped_for_new_risk_semantics() -> None:
    assert CURRENT_METHODOLOGY_VERSION == "v4-disclosure-gaps-2026"
    assert SAFETY_VERSION == "tl-safety-v1.1"
    assert EXPLAINABILITY_VERSION == "tl-explainability-v1.1"
    assert INTEGRITY_VERSION == "tl-integrity-v1.1"
