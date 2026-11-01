"""M0 verification tests for K-items from docs/v2/01-v1-baseline-and-known-issues.md.

Each test is the "How to verify" check for its K-item. A passing test closes
the suspicion; an ``xfail(strict=True)`` test pins a confirmed, documented
limitation (see docs/v2/bug-ledger.md) and turns red the day it is fixed.
"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.db.enums import EvaluationMode, FriesDimension
from app.inference.model_inspection import ModelLabelSnapshot
from app.schemas.evaluations import EvaluationCreate

# --------------------------------------------------------------------- K1 --


def _create_both_paths(db_session, model, draft):
    """Create one evaluation per creation path; return (rows, payloads)."""
    from app.services.evaluation_service import EvaluationService
    from app.services.evaluation_service_v2 import EvaluationServiceV2

    payloads = []
    snapshot = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")
    with (
        patch("app.services.evaluation_service.enqueue_evaluate_model", side_effect=lambda p: payloads.append(p) or "t1"),
        patch("app.services.evaluation_service_v2.enqueue_evaluate_model", side_effect=lambda p: payloads.append(p) or "t2"),
        patch("app.services.evaluation_service_v2.inspect_model_config", return_value=snapshot),
    ):
        bare = EvaluationService(db_session).create_evaluation(
            EvaluationCreate(model_id=model.id, evaluation_mode=EvaluationMode.AI_ASSISTED)
        )
        v2 = EvaluationServiceV2(db_session).create_from_draft(draft.id, EvaluationMode.AI_ASSISTED)
    return (bare, v2), payloads


def test_k1_both_create_paths_share_read_and_review_service(db_session, seeded_model, confirmed_fairness_draft):
    """K1 trace: the services overlap only at creation. Everything after
    (detail, review, finalize, publish, report) goes through EvaluationService
    for rows from either path, so the read side cannot drift."""
    from app.services.evaluation_service import EvaluationService

    (bare, v2), payloads = _create_both_paths(db_session, seeded_model, confirmed_fairness_draft)
    assert len(payloads) == 2
    service = EvaluationService(db_session)
    for row in (bare, v2):
        detail = service.build_detail(service.get_evaluation(row.id))
        assert detail.id == row.id
        assert detail.probe_config["assessment_engine"] == "deterministic"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "K1 documented (S3): the deprecated bare POST /v1/evaluations stamps the legacy "
        "methodology_version (server default) while /v1/evaluations-v2 stamps the current one, "
        "so NOT_APPLICABLE dimensions are folded into overall confidence only on the bare path. "
        "Intentional legacy-semantics path (tests, run_experiments.py); retired with the bare path in v2."
    ),
)
def test_k1_create_paths_stamp_same_methodology(db_session, seeded_model, confirmed_fairness_draft):
    (bare, v2), payloads = _create_both_paths(db_session, seeded_model, confirmed_fairness_draft)
    assert bare.methodology_version == v2.methodology_version
    assert payloads[0].methodology_version == payloads[1].methodology_version


# --------------------------------------------------------------------- K2 --


def _robustness_metrics(n, ci_width=0.10):
    return {
        "clean_accuracy": 0.9,
        "robust_accuracy": 0.85,
        "n_evaluated": n,
        "aspect_scoring": "no_material_risk",
        "uncertainty": {"accuracy_drop": {"ci_lower": 0.05 - ci_width / 2, "ci_upper": 0.05 + ci_width / 2}},
    }


def _fairness_metrics(observed, threshold=30):
    return {
        "demographic_parity_difference": 0.05,
        "min_group_n_observed": observed,
        "min_group_n": threshold,
    }


def test_k2_more_data_never_lowers_confidence():
    """K2 property test: holding everything else fixed, confidence is
    non-decreasing in sample size across every step boundary (16/100/200 for
    robustness, min_group_n for fairness)."""
    from app.confidence.engine import refine

    def conf(dim, m):
        return refine(dim, metric_values=m, evidence_refs=[True]).confidence

    rob = [conf(FriesDimension.ROBUSTNESS, _robustness_metrics(n)) for n in range(1, 400)]
    assert all(b >= a for a, b in zip(rob, rob[1:], strict=False))
    fair = [conf(FriesDimension.FAIRNESS, _fairness_metrics(n)) for n in range(1, 100)]
    assert all(b >= a for a, b in zip(fair, fair[1:], strict=False))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "K2 documented (S3): confidence ignores CI width outside the wide-CI gates, so a "
        "10x narrower interval at the same n gives the same confidence. v1 confidence is a "
        "display-only evidence-strength signal (proposed_calibration); v2 reports posterior "
        "intervals with counts instead (spec 03)."
    ),
)
def test_k2_narrower_ci_raises_confidence():
    from app.confidence.engine import refine

    wide = refine(FriesDimension.ROBUSTNESS, metric_values=_robustness_metrics(150, 0.20), evidence_refs=[True])
    narrow = refine(FriesDimension.ROBUSTNESS, metric_values=_robustness_metrics(150, 0.02), evidence_refs=[True])
    assert narrow.confidence > wide.confidence


# --------------------------------------------------------------------- K3 --


def test_k3_detectability_tracks_ci_width():
    """K3 sensitivity check: since v9-evidence-guards-2026 D is no longer a
    constant 8 for Fairness/Robustness/Safety — it falls 1 per 0.05 of CI width."""
    from app.osd.agent import _fairness_band, _robustness_band, _safety_band

    def rob(w):
        m = {"clean_accuracy": 0.9, "robust_accuracy": 0.85, "uncertainty": {"clean_accuracy": [0.9 - w / 2, 0.9 + w / 2]}}
        return _robustness_band(m)[0][2]

    def fair(w):
        m = {"probe_status": "EVALUATED", "demographic_parity_difference": 0.05, "eopp_ci": [0.0, w]}
        return _fairness_band(m)[0][2]

    def safety(w):
        m = {"severe_fnr": 0.1, "behavior": {"benign_fpr": 0.05, "severe_fnr_ci": [0.05, 0.05 + w]}}
        return _safety_band(m)[0][2]

    for band in (rob, fair):
        assert band(0.02) == 8 and band(0.21) == 4
    assert safety(0.02) > safety(0.30)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "K3 documented (S3): Integrity D is still the constant 8 whether or not the weight "
        "hashes were verified. Only the opt-in legacy_heuristic engine proposes O/S/D (default "
        "deterministic abstains); Integrity becomes a Tier A/B gate in v2 (ADR 0014, M3)."
    ),
)
def test_k3_integrity_detectability_reflects_hash_verification():
    from app.osd.agent import _integrity_band

    checks = {"license": {"pass": True}, "revision": {"pass": True}}
    verified = _integrity_band({"checks": checks, "artifact_verification": {"status": "VERIFIED"}})
    unpinned = _integrity_band({"checks": checks, "artifact_verification": {"status": "UNPINNED"}})
    assert verified[0][2] != unpinned[0][2]


# --------------------------------------------------------------------- K6 --

_FILLER = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."

_ADVERSARIAL_EXPLAINABILITY_CARD = "\n\n".join(
    f"## {h}\n{_FILLER}"
    for h in ("Intended Use", "Limitations", "Training Data", "Evaluation", "Ethical Considerations")
)
_ADVERSARIAL_SAFETY_CARD = "\n\n".join(
    f"## {h}\n{_FILLER}" for h in ("Misuse", "Privacy", "Security", "Training Data")
)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "K6 documented (S3): headings, each followed by one 56-character filler line, give full Explainability coverage. "
        "The matcher measures documentation structure, not content; only the opt-in "
        "legacy_heuristic engine maps coverage to O/S/D. v2 reports card coverage as disclosure, "
        "never as a measurement."
    ),
)
def test_k6_adversarial_card_does_not_earn_explainability_coverage():
    from app.probes.explainability_card import coverage_ratio, detect_required_sections

    assert coverage_ratio(detect_required_sections(_ADVERSARIAL_EXPLAINABILITY_CARD)) < 1.0


@pytest.mark.xfail(
    strict=True,
    reason="K6 documented (S3): same heading-stuffing gap for the Safety card checklist.",
)
def test_k6_adversarial_card_does_not_earn_safety_coverage():
    from app.probes.safety_card import detect_safety_checks, safety_coverage_ratio

    assert safety_coverage_ratio(detect_safety_checks(_ADVERSARIAL_SAFETY_CARD)) < 1.0


# --------------------------------------------------------------------- K7 --

_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="abc")
_CSV = b"text,label,group\n" + b"".join(
    f"t{i},{'approved' if i % 2 else 'denied'},{'a' if i % 3 else 'b'}\n".encode() for i in range(60)
)


def test_k7_unreachable_positive_class_is_rejected():
    """K7 guard that exists: a positive index the mapping never produces is refused."""
    from app.services.draft_validation import validate_fairness_config

    result = validate_fairness_config(
        dataset_bytes=_CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "approved", "model_label_index": 0}, {"dataset_value": "denied", "model_label_index": 0}],
        model_label_snapshot=_SNAPSHOT,
        min_group_n=5,
        positive_label_index=1,
    )
    assert not result.ok


@pytest.mark.xfail(
    strict=True,
    reason=(
        "K7 documented (S2): positive_label_index defaults to 1 in DimensionConfigUpdate (and the "
        "UI preselects 1), so a swapped mapping silently makes 'denied' the positive class. The "
        "reachability guard and the confirm step limit it; making the field required needs a "
        "schema + UI change (M3 profile/positive-class confirmation)."
    ),
)
def test_k7_positive_class_must_be_explicit():
    import uuid

    from app.schemas.evaluation_draft import DimensionConfigUpdate

    with pytest.raises(ValidationError):
        DimensionConfigUpdate(
            dataset_content_id=uuid.uuid4(),
            text_column="text",
            target_column="label",
            sensitive_column="group",
            label_mapping=[{"dataset_value": "approved", "model_label_index": 0}, {"dataset_value": "denied", "model_label_index": 1}],
        )
