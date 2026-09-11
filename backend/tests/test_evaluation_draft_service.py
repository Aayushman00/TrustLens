from unittest.mock import patch

import pytest

from app.api.errors import ValidationAppError
from app.inference.model_inspection import ModelLabelSnapshot
from app.services.evaluation_draft_service import EvaluationDraftService

FAKE_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")
FAKE_3CLASS_SNAPSHOT = ModelLabelSnapshot(
    num_labels=3, id2label={0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"}, resolved_sha="sha-3class"
)

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


@pytest.fixture
def stale_html_dataset_content(db_session, fake_s3_client, monkeypatch):
    """A DatasetContent row hand-inserted with HTML bytes/columns -- the
    exact shape ingestion could produce *before* the HTML/JSON rejection fix
    existed. Ingestion can no longer create a row like this, but a residual
    one (from before the fix shipped) must still be refused when a draft
    tries to actually use it, not silently treated as a valid dataset."""
    import uuid

    from app.db.models import DatasetContent
    from app.storage.evidence_store import DatasetContentStore
    from app.services import evaluation_draft_service as draft_service_module

    html_bytes = b"<!doctype html>\n<html><head><title>404</title></head><body>Not found</body></html>\n"
    store = DatasetContentStore(fake_s3_client, "test-bucket")
    storage_uri, content_hash = store.put(html_bytes, format="csv")
    content = DatasetContent(
        id=uuid.uuid4(),
        content_hash=content_hash.removeprefix("sha256:"),
        storage_uri=storage_uri,
        byte_size=len(html_bytes),
        format="csv",
        row_count=2796,
        columns=[{"name": "<!doctype html>", "inferred_type": "categorical"}],
    )
    db_session.add(content)
    db_session.flush()

    monkeypatch.setattr(draft_service_module, "get_dataset_content_store", lambda settings: store)
    return content


def test_update_dimension_rejects_preexisting_invalid_html_content(
    draft_service, seeded_model, stale_html_dataset_content
):
    """A DatasetContent row created before the ingestion fix existed (the
    exact pre-fix residue) must not be accepted as a valid Fairness input
    just because it already has a row -- update_dimension must return
    ok=False with a clear reason, never a silently "successful" preview."""
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        result = draft_service.update_dimension(
            draft.id,
            "FAIRNESS",
            {"dataset_content_id": stale_html_dataset_content.id, **FAIRNESS_BODY},
        )
    assert not result.ok
    assert any("html" in e.lower() or "webpage" in e.lower() for e in result.errors)


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


def test_get_draft_populates_model_label_snapshot_before_any_dimension_update(
    draft_service, seeded_model
):
    """The frontend needs real model labels to render the mapping UI before
    the user has submitted anything -- GET must trigger the same
    _ensure_model_snapshot fetch update_dimension does, not leave the caller
    stuck with a null snapshot until after a PUT."""
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        read = draft_service.get(draft.id)
    assert read.model_label_snapshot == {"num_labels": 2, "id2label": {0: "NEGATIVE", 1: "POSITIVE"}}


def test_get_draft_exposes_three_labels_for_a_3class_model(draft_service, seeded_model):
    """A 3-class model (e.g. negative/neutral/positive sentiment) must
    surface exactly its three real id2label entries -- never a hardcoded
    2-label NEGATIVE/POSITIVE list that can't represent the third class."""
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_3CLASS_SNAPSHOT):
        read = draft_service.get(draft.id)
    assert read.model_label_snapshot["num_labels"] == 3
    assert read.model_label_snapshot["id2label"] == {0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"}


def test_get_draft_converts_model_inspection_error_to_validation_error(draft_service, seeded_model):
    """A model with unusable/missing classification metadata must block
    (clean 422 via ValidationAppError) at GET time too -- never silently
    return a null/invented snapshot the UI could paper over."""
    from app.inference.model_inspection import ModelInspectionError

    draft = draft_service.create(seeded_model.id)
    with patch(
        "app.services.evaluation_draft_service.inspect_model_config",
        side_effect=ModelInspectionError("MODEL_LOAD_ERROR", "no classification head"),
    ):
        with pytest.raises(ValidationAppError):
            draft_service.get(draft.id)


def test_model_label_snapshot_is_never_refetched_once_frozen(draft_service, seeded_model):
    """Once a draft's snapshot is set (by whichever call reaches it first —
    GET or PUT), it must never change underneath an in-progress label
    mapping: a second inspection call, even one that would return different
    labels, must not overwrite what's already frozen (Task 2.4's 'fetch
    once, share across both dimensions' rule)."""
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        first = draft_service.get(draft.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_3CLASS_SNAPSHOT):
        second = draft_service.get(draft.id)
    # Normalize id2label keys to str for comparison -- whether a snapshot
    # comes back int- or str-keyed depends on in-memory vs. reloaded-from-DB
    # JSONB, but either way it must still be the FIRST snapshot's values,
    # never the second patch's 3-class labels.
    normalize = lambda s: {**s, "id2label": {str(k): v for k, v in s["id2label"].items()}}  # noqa: E731
    assert normalize(first.model_label_snapshot) == normalize(second.model_label_snapshot)
    assert second.model_label_snapshot["num_labels"] == 2


def test_incomplete_label_mapping_cannot_be_confirmed(draft_service, seeded_model, seeded_dataset_content):
    """A label_mapping missing an entry for an observed target value must
    fail validation (ok=False) and confirm_dimension must then refuse to
    confirm -- the backend, not the frontend, is authoritative on
    completeness."""
    draft = draft_service.create(seeded_model.id)
    incomplete_body = {**FAIRNESS_BODY, "label_mapping": [{"dataset_value": "pos", "model_label_index": 1}]}
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        result = draft_service.update_dimension(
            draft.id, "FAIRNESS", {"dataset_content_id": seeded_dataset_content.id, **incomplete_body}
        )
    assert not result.ok
    assert any("missing entries" in e for e in result.errors)
    with pytest.raises(ValidationAppError, match="not.*validated"):
        draft_service.confirm_dimension(draft.id, "FAIRNESS")


def test_label_mapping_index_outside_snapshot_is_rejected(draft_service, seeded_model, seeded_dataset_content):
    """A model_label_index the model snapshot doesn't actually have (e.g. 2
    on a 2-class model) must fail validation -- the backend checks every
    index against the real id2label, it never trusts the frontend's choice."""
    draft = draft_service.create(seeded_model.id)
    bad_index_body = {
        **FAIRNESS_BODY,
        "label_mapping": [
            {"dataset_value": "pos", "model_label_index": 2},
            {"dataset_value": "neg", "model_label_index": 0},
        ],
    }
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        result = draft_service.update_dimension(
            draft.id, "FAIRNESS", {"dataset_content_id": seeded_dataset_content.id, **bad_index_body}
        )
    assert not result.ok
    assert any("unknown model_label_index" in e for e in result.errors)


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
