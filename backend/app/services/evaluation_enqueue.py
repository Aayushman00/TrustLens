"""Shared enqueue-and-record helper for evaluation creation/reconciliation.

Extracted because three call sites (legacy bare create, reconcile-enqueue,
V2 draft-consumption create) had each independently copy-pasted this exact
enqueue -> log -> record-event sequence. That divergence is exactly what
caused a real bug: the reconcile path once rebuilt its payload without
``methodology_version``, silently downgrading a re-enqueued V2 evaluation to
legacy scoring semantics. Consolidating the event-recording shape here
removes the class of bug, not just this one instance of it.

``enqueue_fn`` is passed in (not imported and called directly here) so each
call site keeps its own module-level ``enqueue_evaluate_model`` import —
existing tests monkeypatch that name at the *call site's* module
(``app.services.evaluation_service.enqueue_evaluate_model`` /
``app.services.evaluation_service_v2.enqueue_evaluate_model``), and Python
resolves that name from the caller's module globals at call time, so this
indirection preserves every existing patch target unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from app.db.repositories.evaluation_event import EvaluationEventRepository
from app.schemas.internal import EvaluateModelPayload


def enqueue_and_record(
    events: EvaluationEventRepository,
    payload: EvaluateModelPayload,
    *,
    evaluation_id: uuid.UUID,
    event_type: str,
    enqueue_fn: Callable[[EvaluateModelPayload], str | None],
    on_enqueued: Callable[[str | None], None],
) -> str | None:
    """Enqueue the Celery task and record the real outcome as an event.

    ``enqueue_evaluate_model`` silently returns ``None`` on a broker
    failure, leaving the row at PENDING with no other visible signal —
    recording ``enqueued``/``task_id`` here is what makes that state
    observable at all (and what lets ``reconcile_enqueue_failure`` find it).

    ``on_enqueued`` lets each call site log its own message/fields (they
    differ per site) without duplicating the enqueue-then-record sequence.
    """
    task_id = enqueue_fn(payload)
    on_enqueued(task_id)
    events.create(
        evaluation_id=evaluation_id,
        event_type=event_type,
        detail={"enqueued": task_id is not None, "task_id": task_id},
    )
    return task_id
