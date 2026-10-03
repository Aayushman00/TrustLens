"""Supplemental Claude evaluation: same frozen prompts as the providers, clearly labelled."""

import pytest

from app.scripts import run_claude_eval as ce

pytestmark = pytest.mark.skipif(not ce.L2_SRC.exists() or not ce.L10_SRC.exists(), reason="frozen L2/L10 results absent")


def test_prompts_are_the_frozen_provider_prompts() -> None:
    # l2_prompts/l10_prompts raise if any prompt's sha256 differs from the provider-recorded one.
    assert len(ce.l2_prompts()) == 12
    assert len(ce.l10_prompts()) == 12


def test_prompts_carry_no_trustlens_decision() -> None:
    for text in [*ce.l2_prompts().values(), *ce.l10_prompts().values()]:
        for key in ("risks_triggered", "aspect_scoring", "scored_risk_id", "fries_score", "risk_ids"):
            assert key not in text


def test_record_is_labelled_claude_independent_llm() -> None:
    rec = ce._record("P01", "abc", "prompt", "v", '{"x": 1}', "claude-opus-5-5")
    assert rec["evaluator"] == "Claude" and rec["evaluator_type"] == "independent_llm"
    assert rec["prompt_sha256"] == ce._sha("prompt")
