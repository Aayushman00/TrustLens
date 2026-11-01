"""M0 security pass regressions (bug ledger SEC rows)."""

import pytest
from pydantic import ValidationError

from app.api.errors import ValidationAppError
from app.db.enums import EvaluationMode
from app.schemas.documentation import UserDocumentationCreate
from app.schemas.evaluations import EvaluationCreate
from app.services.evaluation_service import EvaluationService


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>x</script>", "file:///etc/passwd", ""],
)
def test_user_documentation_rejects_non_http_url(url):
    """SEC2: the pointer is rendered as a link (UI + report); only http(s)."""
    with pytest.raises(ValidationError):
        UserDocumentationCreate(url=url, documentation_type="other")


def test_user_documentation_accepts_https_url():
    doc = UserDocumentationCreate(url="https://arxiv.org/abs/1234.5678", documentation_type="research_paper")
    assert doc.url == "https://arxiv.org/abs/1234.5678"


def test_bare_create_rejects_injected_evaluation_contract(db_session, seeded_model):
    """SEC3: a contract only comes from a validated draft. The bare path must
    not store one (reconcile would run it; the report would quote it)."""
    body = EvaluationCreate(
        model_id=seeded_model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config={"evaluation_contract": {"schema_version": "v2", "dataset_content_hash": "sha256:forged"}},
    )
    with pytest.raises(ValidationAppError, match="evaluation_contract"):
        EvaluationService(db_session).create_evaluation(body)
