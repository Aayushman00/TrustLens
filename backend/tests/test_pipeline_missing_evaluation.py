import uuid

import pytest

from app.db.enums import EvaluationMode
from app.schemas.internal import EvaluateModelPayload
from app.tasks.evaluate_pipeline import EvaluationNotVisibleError, run_evaluation_pipeline
from tests.fakes import FakeEvidenceStore


def test_missing_evaluation_raises_retryable_error_not_silent_success(db_session):
    """Regression (final experiment): the task can arrive before the API's
    transaction commits; returning silently left the evaluation PENDING forever."""
    payload = EvaluateModelPayload(
        evaluation_id=uuid.uuid4(), model_ref="org/m", evaluation_mode=EvaluationMode.AI_AUTONOMOUS, probe_config={}
    )
    with pytest.raises(EvaluationNotVisibleError):
        run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    assert issubclass(EvaluationNotVisibleError, TimeoutError)  # covered by the task's autoretry_for
