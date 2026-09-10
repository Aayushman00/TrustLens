"""Tests for POST /v1/evaluations-v2 -> EvaluationServiceV2.create_from_draft
(Task 4.4) — consumes a validated EvaluationDraft atomically into a frozen
Evaluation carrying EvaluationContractV2."""

from unittest.mock import patch

import pytest

from app.api.errors import ConflictError
from app.db.enums import EvaluationMode
from app.inference.model_inspection import ModelLabelSnapshot
from app.services.evaluation_service_v2 import EvaluationServiceV2

# Matches the resolved_sha baked into the confirmed_fairness_draft /
# half_confirmed_draft fixtures (backend/tests/conftest.py) — "not stale".
_MATCHING_SNAPSHOT = ModelLabelSnapshot(
    num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1"
)
_DIFFERENT_SNAPSHOT = ModelLabelSnapshot(
    num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-2-different"
)

_PATCH_TARGET = "app.services.evaluation_service_v2.inspect_model_config"


def test_create_from_confirmed_draft_freezes_contract(db_session, confirmed_fairness_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        evaluation = service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
    contract = evaluation.probe_config["evaluation_contract"]
    assert contract["schema_version"] == "v2"
    assert contract["fairness"] is not None
    assert contract["robustness"] is None
    assert evaluation.methodology_version == "v2-per-dimension-2026"


def test_create_from_draft_marks_draft_consumed(db_session, confirmed_fairness_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
    db_session.refresh(confirmed_fairness_draft)
    assert confirmed_fairness_draft.status == "consumed"


def test_create_from_already_consumed_draft_rejected(db_session, confirmed_fairness_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
    with pytest.raises(ConflictError):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_rejects_stale_model_revision(db_session, confirmed_fairness_draft, seeded_model):
    seeded_model.revision = "a-different-revision"
    db_session.flush()
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_DIFFERENT_SNAPSHOT):
        with pytest.raises(ConflictError, match="stale"):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_rejects_half_confirmed_dimension(db_session, half_confirmed_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        with pytest.raises(ConflictError, match="not confirmed"):
            service.create_from_draft(half_confirmed_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_after_marked_stale_is_permanently_rejected(
    db_session, confirmed_fairness_draft, seeded_model
):
    """Judgment call 3: once a draft is flagged stale, a later retry with an
    unrevalidated draft must also be rejected — not just the first attempt
    that discovered the drift. Nothing in the codebase transitions a draft
    back out of "stale", so this permanently dead-ends the draft (the user
    must create a new one), which is what actually upholds "never
    partial/mixed snapshots" here."""
    seeded_model.revision = "a-different-revision"
    db_session.flush()
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_DIFFERENT_SNAPSHOT):
        with pytest.raises(ConflictError, match="stale"):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)

    # Retry — even if the current model snapshot were somehow back in sync,
    # a "stale" draft must never be consumable again.
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        with pytest.raises(ConflictError):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_rejects_no_dimensions_configured(db_session, seeded_model):
    """Judgment call 4: a draft where neither Fairness nor Robustness was
    ever configured must be rejected — mirrors the frontend intake wizard's
    ``anyEnabled`` gate (Task 3.5), which never allows Continue without at
    least one dimension configured. There is no legitimate empty-contract
    evaluation in this product."""
    from app.services.evaluation_draft_service import EvaluationDraftService

    draft = EvaluationDraftService(db_session).create(seeded_model.id)
    # A draft with no dimensions touched never fetched a model snapshot
    # (resolved_model_sha stays None) — match that here so the staleness
    # check passes through to the dimension check this test targets.
    never_snapshotted = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha=None)
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=never_snapshotted):
        with pytest.raises(ConflictError, match="(?i)at least one dimension"):
            service.create_from_draft(draft.id, EvaluationMode.AI_ASSISTED)
