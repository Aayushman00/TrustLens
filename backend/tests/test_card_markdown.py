"""card_markdown helper unit tests — nontrivial() placeholder-boilerplate guard.

Regression for the bug found running a live dry run: HF auto-generates
"[More Information Needed]" (25 chars) into every unfilled model-card
template section. That clears MIN_BODY_CHARS=20 on length alone, so before
this fix nontrivial() (and therefore detect_required_sections) treated an
entirely unfilled template card as if it had disclosed real content.
"""

from __future__ import annotations

from app.probes.card_markdown import nontrivial
from app.probes.explainability_card import detect_required_sections


def test_more_information_needed_placeholder_is_trivial() -> None:
    assert nontrivial("[More Information Needed]") is False


def test_placeholder_variants_are_trivial() -> None:
    for body in ("N/A", "TBD", "Coming soon", "Not available", "[more information needed]"):
        assert nontrivial(body) is False


def test_real_content_of_similar_length_is_nontrivial() -> None:
    # Same rough length as the placeholder, but actual disclosed content —
    # must not be swept up by the placeholder check.
    assert nontrivial("Trained on public toxicity datasets from 2020-2023.") is True


def test_unfilled_template_card_scores_zero_required_sections() -> None:
    """The bug's real manifestation: an HF card where every required section
    is literally the unfilled placeholder must report present=False for all
    of them, not a false coverage_ratio from placeholder text length."""
    text = (
        "## Intended Use\n\n[More Information Needed]\n\n"
        "## Limitations\n\n[More Information Needed]\n\n"
        "## Training Data\n\n[More Information Needed]\n\n"
        "## Evaluation\n\n[More Information Needed]\n\n"
        "## Ethical Considerations\n\n[More Information Needed]\n"
    )
    results = detect_required_sections(text, {})
    for key in (
        "intended_use",
        "limitations",
        "training_data",
        "evaluation",
        "ethical_considerations",
    ):
        assert results[key]["present"] is False, f"{key} should not count boilerplate as present"
