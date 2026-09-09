from unittest.mock import patch

import pytest

from app.api.errors import ValidationAppError
from app.inference.model_inspection import ModelLabelSnapshot
from app.services.evaluation_draft_service import EvaluationDraftService

FAKE_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")

FAIRNESS_BODY = {
    "text_column": "text",
    "target_column": "label",
    "sensitive_column": "group",
    "label_mapping": [
        {"dataset_value": "pos", "model_label_index": 1},
        {"dataset_value": "neg", "model_label_index": 0},
    ],
    "min_group_n": 2,
}


@pytest.fixture
def draft_service(db_session):
    return EvaluationDraftService(db_session)


def test_create_draft(draft_service, seeded_model):
    read = draft_service.create(seeded_model.id)
    assert read.status == "incomplete"
    assert read.model_id == seeded_model.id


def test_update_fairness_dimension_validates_and_returns_preview(draft_service, seeded_model, seeded_dataset_content):
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        result = draft_service.update_dimension(
            draft.id,
            "FAIRNESS",
            {"dataset_content_id": seeded_dataset_content.id, **FAIRNESS_BODY},
        )
    assert result.ok
    assert result.groups_remaining >= 2


def test_confirm_requires_prior_validation(draft_service, seeded_model):
    draft = draft_service.create(seeded_model.id)
    with pytest.raises(ValidationAppError, match="not.*validated"):
        draft_service.confirm_dimension(draft.id, "FAIRNESS")


def test_confirm_sets_confirmed_at(draft_service, seeded_model, seeded_dataset_content):
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        draft_service.update_dimension(
            draft.id,
            "FAIRNESS",
            {"dataset_content_id": seeded_dataset_content.id, **FAIRNESS_BODY},
        )
    read = draft_service.confirm_dimension(draft.id, "FAIRNESS")
    assert read.fairness_confirmed


def test_confirm_never_touched_dimension_raises_without_crashing(draft_service, seeded_model):
    """A dimension that was never even updated (no DraftDimensionConfig row
    at all) must raise the same ValidationAppError as an updated-but-not-yet-
    validated one — not an AttributeError/None-crash."""
    draft = draft_service.create(seeded_model.id)
    with pytest.raises(ValidationAppError, match="not.*validated"):
        draft_service.confirm_dimension(draft.id, "ROBUSTNESS")


def test_update_dimension_twice_revalidates_and_reclears_confirmation(
    draft_service, seeded_model, seeded_dataset_content
):
    """Editing an already-confirmed dimension re-validates with the new
    inputs and clears that dimension's confirmation — without touching the
    other dimension's confirmation."""
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        draft_service.update_dimension(
            draft.id,
            "FAIRNESS",
            {"dataset_content_id": seeded_dataset_content.id, **FAIRNESS_BODY},
        )
        draft_service.update_dimension(
            draft.id,
            "ROBUSTNESS",
            {
                "dataset_content_id": seeded_dataset_content.id,
                "text_column": "text",
                "target_column": "label",
                "label_mapping": FAIRNESS_BODY["label_mapping"],
            },
        )
    draft_service.confirm_dimension(draft.id, "FAIRNESS")
    draft_service.confirm_dimension(draft.id, "ROBUSTNESS")

    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        result = draft_service.update_dimension(
            draft.id,
            "FAIRNESS",
            {"dataset_content_id": seeded_dataset_content.id, **{**FAIRNESS_BODY, "min_group_n": 100}},
        )
    assert not result.ok  # min_group_n=100 is now unmeetable by the 5-row fixture

    read = draft_service.get(draft.id)
    assert not read.fairness_confirmed  # re-editing cleared this dimension's confirmation
    assert read.robustness_confirmed  # ...but never touched the other one
