"""ORM tests for EvaluationDraft and DraftDimensionConfig models."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import DraftDimensionConfig, EvaluationDraft


def test_draft_defaults_to_incomplete(db_session, seeded_model):
    """EvaluationDraft status defaults to 'incomplete'."""
    draft = EvaluationDraft(model_id=seeded_model.id)
    db_session.add(draft)
    db_session.flush()
    assert draft.status == "incomplete"


def test_one_dimension_config_per_dimension_per_draft(db_session, seeded_model):
    """Unique constraint enforces one config per dimension per draft."""
    draft = EvaluationDraft(model_id=seeded_model.id)
    db_session.add(draft)
    db_session.flush()

    db_session.add(DraftDimensionConfig(draft_id=draft.id, dimension="FAIRNESS"))
    db_session.flush()

    db_session.add(DraftDimensionConfig(draft_id=draft.id, dimension="FAIRNESS"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_draft_cascades_to_dimension_configs(db_session, seeded_model):
    """Deleting a draft cascades delete to its dimension configs."""
    draft = EvaluationDraft(model_id=seeded_model.id)
    db_session.add(draft)
    db_session.flush()
    dim = DraftDimensionConfig(draft_id=draft.id, dimension="ROBUSTNESS")
    db_session.add(dim)
    db_session.flush()
    dim_id = dim.id

    db_session.delete(draft)
    db_session.flush()
    assert db_session.get(DraftDimensionConfig, dim_id) is None
