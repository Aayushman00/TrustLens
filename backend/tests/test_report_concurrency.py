"""Report version uniqueness / concurrency race (audit P1-6).

Exercises the actual DB-level race: two independent sessions/transactions
(real threads against real Postgres, via TEST_DATABASE_URL) calling
ReportService.generate() for the same evaluation at (as close to) the same
moment. Before the fix, both could read the same "latest version" and both
insert — this file proves that can no longer happen, at three levels:
the service-level lock (the primary fix), the DB unique constraint (the
final invariant, exercised directly), and the clean-error safety net.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.errors import ConflictError
from app.core.db import get_session_factory
from app.db.enums import EvaluationMode
from app.db.models import Report
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_event import EVENT_REPORT_GENERATED, EvaluationEventRepository
from app.db.repositories.model import ModelRepository
from app.db.repositories.report import ReportRepository
from app.schemas.internal import EvaluateModelPayload
from app.services.report_service import ReportService
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.fakes import FakeEvidenceStore, FakeReportStore


def _finalized_evaluation_id(database_url: str) -> uuid.UUID:
    """Real, committed FINALIZED evaluation — built with its own session so
    it's actually visible to other independent sessions/threads."""
    session = get_session_factory(database_url)()
    try:
        model = ModelRepository(session).create(hf_repo_id=f"org/concur-{uuid.uuid4().hex[:8]}")
        evaluation = EvaluationRepository(session).create(
            model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS
        )
        session.commit()
        payload = EvaluateModelPayload(
            evaluation_id=evaluation.id,
            model_ref=model.hf_repo_id,
            evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        )
        run_evaluation_pipeline(session, payload, evidence_store=FakeEvidenceStore())
        session.commit()
        return evaluation.id
    finally:
        session.close()


@dataclass
class _WorkerResult:
    ok: bool
    version: int | None = None
    error: str | None = None


def test_concurrent_report_generation_no_duplicate_version(database_url: str) -> None:
    """Two genuinely concurrent transactions calling generate() for the same
    evaluation must never both succeed with the same version."""
    evaluation_id = _finalized_evaluation_id(database_url)
    store = FakeReportStore()
    barrier = threading.Barrier(2)
    results: dict[int, _WorkerResult] = {}

    def worker(idx: int) -> None:
        session = get_session_factory(database_url)()
        try:
            barrier.wait(timeout=5)
            report = ReportService(session, store=store).generate(evaluation_id)
            session.commit()
            results[idx] = _WorkerResult(ok=True, version=report.version)
        except Exception as exc:  # noqa: BLE001 — capture for assertion, not re-raise in a thread
            session.rollback()
            results[idx] = _WorkerResult(ok=False, error=repr(exc))
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, results
    for idx, result in results.items():
        assert result.ok, f"worker {idx} failed: {result.error}"

    versions = sorted(r.version for r in results.values())
    # The lock serializes the two transactions — both succeed, and because
    # generation is append-only (latest+1), they land on 1 and 2, never a
    # duplicate.
    assert versions == [1, 2]
    assert len(set(versions)) == 2

    # Verify at the DB level too: exactly one row per version, both for the
    # same evaluation_id, no duplicate (evaluation_id, version) pair.
    session = get_session_factory(database_url)()
    try:
        db_rows = list(
            session.scalars(
                select(Report).where(Report.evaluation_id == evaluation_id)
            ).all()
        )
        assert sorted(r.version for r in db_rows) == [1, 2]
        assert len({r.version for r in db_rows}) == len(db_rows)

        # Report artifacts remain correctly associated with their own version.
        by_version = {r.version: r for r in db_rows}
        assert by_version[1].json_uri == f"s3://trustlens/reports/{evaluation_id}/v1/report.json"
        assert by_version[2].json_uri == f"s3://trustlens/reports/{evaluation_id}/v2/report.json"
        assert f"reports/{evaluation_id}/v1/report.json" in store.objects
        assert f"reports/{evaluation_id}/v2/report.json" in store.objects

        # Exactly one report_generated event per actual successful generation
        # — never fabricated for a failed/duplicate attempt (there were none
        # here, since the lock let both succeed cleanly).
        events = EvaluationEventRepository(session).list_for_evaluation(evaluation_id)
        report_events = [e for e in events if e.event_type == EVENT_REPORT_GENERATED]
        assert len(report_events) == 2
        assert sorted(e.detail["version"] for e in report_events) == [1, 2]
    finally:
        session.close()


def test_sequential_regeneration_versions_increment_1_2_3(database_url: str) -> None:
    evaluation_id = _finalized_evaluation_id(database_url)
    store = FakeReportStore()
    session = get_session_factory(database_url)()
    try:
        service = ReportService(session, store=store)
        v1 = service.generate(evaluation_id)
        v2 = service.generate(evaluation_id)
        v3 = service.generate(evaluation_id)
        session.commit()
        assert (v1.version, v2.version, v3.version) == (1, 2, 3)
        assert f"reports/{evaluation_id}/v1/report.json" in store.objects
        assert f"reports/{evaluation_id}/v2/report.json" in store.objects
        assert f"reports/{evaluation_id}/v3/report.json" in store.objects
    finally:
        session.close()


def test_db_constraint_rejects_duplicate_version_directly(database_url: str) -> None:
    """Exercises the unique constraint itself, independent of the service's
    lock — the final invariant per audit P1-6 requirement 7."""
    evaluation_id = _finalized_evaluation_id(database_url)
    session = get_session_factory(database_url)()
    try:
        repo = ReportRepository(session)
        repo.create(
            evaluation_id=evaluation_id,
            json_uri="s3://trustlens/reports/x/v1/report.json",
            pdf_uri=None,
            version=1,
        )
        session.commit()

        with pytest.raises(IntegrityError):
            with session.begin_nested():
                repo.create(
                    evaluation_id=evaluation_id,
                    json_uri="s3://trustlens/reports/x/v1/report-again.json",
                    pdf_uri=None,
                    version=1,
                )
    finally:
        session.rollback()
        session.close()


def test_generate_internal_conflict_is_clean_error_not_fabricated_event(
    database_url: str,
) -> None:
    """Simulates the lock having been bypassed (defense-in-depth): forces
    ReportService._generate to attempt an already-taken version directly.
    Must raise a clean ConflictError (never a raw 500) and must not record
    a report_generated event for the failed attempt, and the session must
    remain usable afterward (SAVEPOINT-scoped rollback, not the whole
    transaction)."""
    evaluation_id = _finalized_evaluation_id(database_url)
    store = FakeReportStore()
    session = get_session_factory(database_url)()
    try:
        # Pre-seed the DB row directly (bypassing the service/lock entirely,
        # and never touching `store`) so the FakeReportStore's own
        # append-only guard doesn't fire first — this isolates the DB
        # constraint's own safety net from the storage layer's.
        ReportRepository(session).create(
            evaluation_id=evaluation_id,
            json_uri=f"s3://trustlens/reports/{evaluation_id}/v1/report.json",
            pdf_uri=None,
            version=1,
        )
        session.commit()

        evaluation = EvaluationRepository(session).get_by_id(evaluation_id)
        events_before = len(EvaluationEventRepository(session).list_for_evaluation(evaluation_id))

        service = ReportService(session, store=store)
        with pytest.raises(ConflictError):
            service._generate(evaluation, version=1)  # noqa: SLF001 — white-box safety-net test

        events_after = EvaluationEventRepository(session).list_for_evaluation(evaluation_id)
        assert len(events_after) == events_before

        # Session still usable — the SAVEPOINT rolled back, not the whole
        # transaction/connection.
        assert EvaluationRepository(session).get_by_id(evaluation_id) is not None
        session.commit()
    finally:
        session.close()
