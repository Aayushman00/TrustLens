"""ProbeConfigV1 validation (Phase 9)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.probe_config import parse_probe_config


def test_parse_empty_defaults_to_v1() -> None:
    cfg = parse_probe_config({})
    assert cfg.schema_version == "v1"
    assert cfg.datasets == {}
    assert cfg.attack_budget is None


def test_parse_v1_with_datasets() -> None:
    cfg = parse_probe_config(
        {
            "schema_version": "v1",
            "datasets": {"fairness": "sentiment_fairness"},
            "attack_budget": 0.1,
        }
    )
    assert cfg.datasets["fairness"] == "sentiment_fairness"
    assert cfg.attack_budget == 0.1


def test_reject_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        parse_probe_config({"schema_version": "v2"})
