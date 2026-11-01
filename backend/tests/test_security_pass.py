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


def _compose_published_ports():
    """Every ``ports`` entry in every docker-compose*.yml, keyed by file/service."""
    from pathlib import Path

    import yaml

    class _Loader(yaml.SafeLoader):
        pass

    # Compose-only tags such as ``!override`` / ``!reset``: keep the value, drop the tag.
    _Loader.add_multi_constructor(
        "!", lambda loader, _tag, node: loader.construct_sequence(node)
        if isinstance(node, yaml.SequenceNode) else loader.construct_scalar(node)
    )
    root = Path(__file__).resolve().parents[2]
    files = sorted(root.glob("docker-compose*.yml"))
    assert files, "no compose files found"
    for path in files:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader) or {}
        for name, service in (doc.get("services") or {}).items():
            for entry in (service or {}).get("ports") or []:
                yield f"{path.name}:{name}", str(entry)


def test_compose_ports_bind_localhost_only():
    """SEC7: the API is unauthenticated, so no published port (API, Postgres,
    Redis, frontend) may listen on all host interfaces."""
    ports = list(_compose_published_ports())
    assert ports
    exposed = [(where, p) for where, p in ports if not p.startswith("127.0.0.1:")]
    assert not exposed, exposed
