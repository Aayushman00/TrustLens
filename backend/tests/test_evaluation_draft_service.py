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


def test_create_draft_rejects_unpinned_model(draft_service, db_session):
    """A model with no pinned revision must not be able to start an
    evaluation at all — reproducibility is a property of the Model row, not
    just of whatever revision happens to resolve when a draft freezes its
    own snapshot later."""
    from app.db.models import Model

    unpinned = Model(hf_repo_id="org/unpinned-model", model_metadata={}, checksum=None, revision=None)
    db_session.add(unpinned)
    db_session.flush()

    with pytest.raises(ValidationAppError, match="pinned revision"):
        draft_service.create(unpinned.id)


def test_update_dimension_converts_model_inspection_error_to_validation_error(
    draft_service, seeded_model, seeded_dataset_content
):
    """A model reference/revision that fails Hub inspection at intake
    (typo'd revision, deleted branch, Hub error) must surface as a clean
    422, never an unhandled 500."""
    from app.inference.model_inspection import ModelInspectionError

    draft = draft_service.create(seeded_model.id)
    with patch(
        "app.services.evaluation_draft_service.inspect_model_config",
        side_effect=ModelInspectionError("MODEL_LOAD_ERROR", "boom"),
    ):
        with pytest.raises(ValidationAppError):
            draft_service.update_dimension(
                draft.id,
                "FAIRNESS",
                {"dataset_content_id": seeded_dataset_content.id, **FAIRNESS_BODY},
            )


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


@pytest.mark.parametrize("bad_min_group_n", [0, -5])
def test_update_dimension_rejects_non_positive_min_group_n(
    draft_service, seeded_model, seeded_dataset_content, bad_min_group_n
):
    """min_group_n must be a positive int (Global Constraint) — 0 or a
    negative value must be rejected outright, never silently coerced to the
    default (falsy-0 -> 30) and never passed through unvalidated (a
    negative threshold would make every group count "meet" it, producing a
    false-positive ok=True)."""
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        with pytest.raises(ValidationAppError):
            draft_service.update_dimension(
                draft.id,
                "FAIRNESS",
                {"dataset_content_id": seeded_dataset_content.id, **{**FAIRNESS_BODY, "min_group_n": bad_min_group_n}},
            )


def test_update_dimension_raises_when_storage_not_configured(
    draft_service, seeded_model, seeded_dataset_content, monkeypatch
):
    """An unconfigured S3/MinIO environment must fail cleanly with a
    ValidationAppError, not a bare AttributeError on a None store."""
    import app.services.evaluation_draft_service as draft_service_module

    monkeypatch.setattr(draft_service_module, "get_dataset_content_store", lambda settings: None)
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        with pytest.raises(ValidationAppError, match="not configured"):
            draft_service.update_dimension(
                draft.id,
                "FAIRNESS",
                {"dataset_content_id": seeded_dataset_content.id, **FAIRNESS_BODY},
            )
