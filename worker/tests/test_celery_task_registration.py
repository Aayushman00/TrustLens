"""Celery task registration smoke tests (Phase 7)."""

from __future__ import annotations

import sys
import types
import uuid
from unittest.mock import MagicMock

from app.celery_app import celery_app


def test_evaluate_model_task_registered() -> None:
    import app.tasks.evaluate  # noqa: F401

    assert "trustlens.evaluate_model" in celery_app.tasks


def test_evaluate_model_wrapper_calls_pipeline(monkeypatch) -> None:
    """Inject fake vendored modules so the task body can run without Docker COPY."""
    import app.tasks.evaluate as evaluate_mod

    calls: list[object] = []

    fake_payload_cls = MagicMock()
    fake_payload = MagicMock()
    fake_payload.evaluation_id = uuid.uuid4()
    fake_payload.evaluation_mode.value = "AI_AUTONOMOUS"
    fake_payload_cls.model_validate.return_value = fake_payload

    fake_internal = types.ModuleType("app.schemas.internal")
    fake_internal.EvaluateModelPayload = fake_payload_cls  # type: ignore[attr-defined]

    fake_pipeline = types.ModuleType("app.tasks.evaluate_pipeline")

    def _run(session: object, payload: object) -> None:
        calls.append(payload)

    fake_pipeline.run_evaluation_pipeline = _run  # type: ignore[attr-defined]

    fake_db = types.ModuleType("app.core.db")

    class _Ctx:
        def __enter__(self) -> MagicMock:
            return MagicMock()

        def __exit__(self, *args: object) -> None:
            return None

    fake_db.get_session = lambda url: _Ctx()  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "app.schemas.internal", fake_internal)
    monkeypatch.setitem(sys.modules, "app.tasks.evaluate_pipeline", fake_pipeline)
    monkeypatch.setitem(sys.modules, "app.core.db", fake_db)

    settings = MagicMock()
    settings.database_url = "postgresql+psycopg2://trustlens:trustlens@localhost/trustlens"
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    result = evaluate_mod.evaluate_model.apply(
        kwargs={
            "schema_version": "v1",
            "evaluation_id": str(fake_payload.evaluation_id),
            "model_ref": "org/model",
            "evaluation_mode": "AI_AUTONOMOUS",
            "probe_config": {},
        }
    )
    assert result.successful()
    assert len(calls) == 1
    assert calls[0] is fake_payload
