"""Offline L3 replay: v1.0 stored flags vs v1.1 re-derived flags, frozen rule."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.scripts.replay_l3_disclosure_gaps import replay, to_markdown

_GAP_CARD = "# m\n\n## Intended use\nToxicity scoring for moderation queues.\n"
_CONTRA_CARD = (Path(__file__).parent / "fixtures" / "model_card_contradiction.md").read_text(encoding="utf-8")
_WEIGHTS = b"tiny-weights"
_HUB_CARD = "# hub model\n\nA classifier card.\n"


def _probe(dim: str, risks: list[str], **extra: object) -> dict:
    mv = {"risks_triggered": risks, "aspect_scoring": "risk_detected" if risks else "no_material_risk", **extra}
    return {"dimension": dim, "status": "EVALUATED", "metric_values": mv}


def _run(dims: dict[str, dict], lic: str | None, behavior: dict | None = None) -> dict:
    probes = [
        _probe("SAFETY", dims["SAFETY"], behavior=behavior or {"severe_fnr": 0.3, "severe_fnr_ci": [0.25, 0.35]}),
        _probe("EXPLAINABILITY", dims["EXPLAINABILITY"]),
        _probe("INTEGRITY", dims["INTEGRITY"], disclosure={"license_structured": lic}),
    ]
    return {"status": "FINALIZED", "probes": probes}


@pytest.fixture()
def suite(tmp_path: Path) -> Path:
    """Two local models + one Hub control, stored with v1.0 (pre-L3) risk semantics."""
    truth = {
        "models": {
            "ctrl_local": {"injected_defects": []},
            "ctrl_hub": {"injected_defects": []},
            "var_card": {"injected_defects": ["INTEGRITY"]},
        },
        "controls": ["ctrl_local", "ctrl_hub"],
    }
    (tmp_path / "ground_truth.json").write_text(json.dumps(truth), encoding="utf-8")
    for name, card, manifest_sha in (
        ("ctrl_local", _GAP_CARD, hashlib.sha256(_WEIGHTS).hexdigest()),
        ("var_card", _CONTRA_CARD, None),
    ):
        (tmp_path / "cards" / name).mkdir(parents=True)
        (tmp_path / "cards" / name / "README.md").write_bytes(card.encode("utf-8"))
        model = tmp_path / "models" / name
        model.mkdir(parents=True)
        (model / "model.safetensors").write_bytes(_WEIGHTS)
        manifest = {"model_safetensors_sha256": manifest_sha} if manifest_sha else {}
        (model / "train_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    raw = tmp_path / "run_a" / "raw"
    raw.mkdir(parents=True)
    unpinned = ["I-INT-REV-UNPINNED", "I-INT-MANIFEST-MISSING"]
    runs = {
        "ctrl_local": _run({"SAFETY": ["S-GOV-DISCLOSURE-GAP"], "EXPLAINABILITY": ["E-DOC-INCOMPLETE"], "INTEGRITY": unpinned}, "apache-2.0"),
        "var_card": _run({"SAFETY": ["S-GOV-DISCLOSURE-GAP"], "EXPLAINABILITY": ["E-DOC-INCOMPLETE", "E-DOC-CONTRADICTION"], "INTEGRITY": unpinned}, None),
    }
    hub = _run({"SAFETY": ["S-GOV-DISCLOSURE-GAP"], "EXPLAINABILITY": ["E-DOC-INCOMPLETE"], "INTEGRITY": []}, "apache-2.0")
    doc = {
        "retrieval_status": "ok",
        "source_model_ref": "org/hub",
        "documentation_revision": "a" * 40,
        "documentation_content_hash": "sha256:" + hashlib.sha256(_HUB_CARD.encode()).hexdigest(),
    }
    for p in hub["probes"]:
        p["metric_values"]["documentation_source"] = doc
    integ = next(p for p in hub["probes"] if p["dimension"] == "INTEGRITY")
    integ["metric_values"]["identity"] = {"revision": "a" * 40, "hub_files": ["model.safetensors"], "weight_hash": None, "trusted_reference": None}
    runs["ctrl_hub"] = hub
    for name, ev in runs.items():
        (raw / f"{name}__run1.json").write_text(json.dumps(ev), encoding="utf-8")
    return tmp_path


def _hub_loader(repo: str, revision: str) -> bytes:
    assert (repo, revision) == ("org/hub", "a" * 40)
    return _HUB_CARD.encode()


def test_control_flag_rate_before_and_after(suite: Path) -> None:
    out = replay(suite, [suite / "run_a"], hub_card_loader=_hub_loader)
    rate = out["control_flag_rate"]
    for dim in ("SAFETY", "EXPLAINABILITY", "INTEGRITY"):
        assert rate[dim]["after"] == 0.0, dim
    assert rate["SAFETY"]["before"] == 1.0
    assert rate["EXPLAINABILITY"]["before"] == 1.0
    assert rate["INTEGRITY"]["before"] == 0.5


def test_contradiction_still_flags_and_card_only_integrity_is_lost(suite: Path) -> None:
    v = replay(suite, [suite / "run_a"], hub_card_loader=_hub_loader)["models"]["var_card"]
    assert v["before"] == {"SAFETY": True, "EXPLAINABILITY": True, "INTEGRITY": True}
    assert v["after"] == {"SAFETY": False, "EXPLAINABILITY": True, "INTEGRITY": False}
    det = replay(suite, [suite / "run_a"], hub_card_loader=_hub_loader)["detection"]["INTEGRITY"]
    assert (det["recall_before"], det["recall_after"]) == ([1, 1], [0, 1])


def test_inputs_and_versions_are_recorded(suite: Path) -> None:
    out = replay(suite, [suite / "run_a"], hub_card_loader=_hub_loader)
    assert out["methodology"]["after"]["methodology_version"] == "v4-disclosure-gaps-2026"
    assert out["methodology"]["after"]["tl-integrity"] == "tl-integrity-v1.1"
    assert out["inputs"]["run_dirs"] == ["run_a"]
    ctrl = out["models"]["ctrl_local"]["inputs"]
    assert ctrl["card"]["sha256"] == hashlib.sha256(_GAP_CARD.encode()).hexdigest()
    assert ctrl["weights"]["sha256"] == hashlib.sha256(_WEIGHTS).hexdigest()
    assert out["models"]["ctrl_local"]["identity"]["hash_comparison"] == "match"
    assert out["models"]["ctrl_hub"]["inputs"]["card"]["source"] == "hub:org/hub@" + "a" * 40
    assert "| SAFETY | 1.00 | 0.00 |" in to_markdown(out)


def test_hub_card_hash_mismatch_refuses(suite: Path) -> None:
    with pytest.raises(ValueError, match="hash"):
        replay(suite, [suite / "run_a"], hub_card_loader=lambda repo, rev: b"changed card")
