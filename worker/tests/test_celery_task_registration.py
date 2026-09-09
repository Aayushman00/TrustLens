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

    on_failure_calls: list[object] = []
    monkeypatch.setattr(
        evaluate_mod._FailStuckRunningTask,
        "on_failure",
        lambda self, *a, **kw: on_failure_calls.append((a, kw)),
    )

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
    # A successful run must never invoke the retry-exhaustion safety net.
    assert on_failure_calls == []


def test_task_configured_for_transient_autoretry_with_backoff() -> None:
    import app.tasks.evaluate as evaluate_mod

    task = evaluate_mod.evaluate_model
    assert task.autoretry_for == (ConnectionError, TimeoutError)
    assert task.max_retries == 3
    assert task.retry_backoff is True


def test_on_failure_transitions_stuck_running_evaluation_via_real_cas_helper(
    monkeypatch,
) -> None:
    """Simulates retries being exhausted (Celery calls on_failure exactly
    once, only after that happens — never mid-retry, never on success).
    Proves the callback delegates to fail_stuck_running_evaluation (the
    same CAS as the rest of the lifecycle) with the correct evaluation_id,
    and never invents its own status-mutation logic."""
    import app.tasks.evaluate as evaluate_mod

    eval_id = uuid.uuid4()
    calls: list[uuid.UUID] = []

    fake_payload_cls = MagicMock()
    fake_payload = MagicMock()
    fake_payload.evaluation_id = eval_id
    fake_payload_cls.model_validate.return_value = fake_payload

    fake_internal = types.ModuleType("app.schemas.internal")
    fake_internal.EvaluateModelPayload = fake_payload_cls  # type: ignore[attr-defined]

    fake_pipeline = types.ModuleType("app.tasks.evaluate_pipeline")

    def _fail_stuck(session: object, evaluation_id: uuid.UUID, **kwargs: object) -> bool:
        calls.append(evaluation_id)
        return True

    fake_pipeline.fail_stuck_running_evaluation = _fail_stuck  # type: ignore[attr-defined]

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

    task = evaluate_mod.evaluate_model
    # Celery invokes on_failure with (exc, task_id, args, kwargs, einfo) once
    # the task is permanently done retrying — exercised directly here rather
    # than via real backoff timing, which is Celery's own tested behavior.
    task.on_failure(
        ConnectionError("simulated exhausted retry"),
        "fake-task-id",
        (),
        {"evaluation_id": str(eval_id), "model_ref": "org/x", "evaluation_mode": "AI_AUTONOMOUS"},
        None,
    )
    assert calls == [eval_id]


def test_on_failure_skips_cleanly_when_database_url_unset(monkeypatch) -> None:
    """No DB configured — must log and return, never raise from on_failure."""
    import app.tasks.evaluate as evaluate_mod

    eval_id = uuid.uuid4()
    fake_payload_cls = MagicMock()
    fake_payload = MagicMock()
    fake_payload.evaluation_id = eval_id
    fake_payload_cls.model_validate.return_value = fake_payload

    fake_internal = types.ModuleType("app.schemas.internal")
    fake_internal.EvaluateModelPayload = fake_payload_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.schemas.internal", fake_internal)

    settings = MagicMock()
    settings.database_url = None
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    task = evaluate_mod.evaluate_model
    task.on_failure(
        ConnectionError("boom"), "fake-task-id", (), {"evaluation_id": str(eval_id)}, None
    )  # must not raise
