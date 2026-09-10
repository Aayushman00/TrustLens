"""Tests for POST /v1/evaluations-v2 -> EvaluationServiceV2.create_from_draft
(Task 4.4) — consumes a validated EvaluationDraft atomically into a frozen
Evaluation carrying EvaluationContractV2."""

from unittest.mock import patch

import pytest

from app.api.errors import ConflictError
from app.db.enums import EvaluationMode
from app.inference.model_inspection import ModelLabelSnapshot
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION
from app.services.evaluation_service_v2 import EvaluationServiceV2

# Matches the resolved_sha baked into the confirmed_fairness_draft /
# half_confirmed_draft fixtures (backend/tests/conftest.py) — "not stale".
_MATCHING_SNAPSHOT = ModelLabelSnapshot(
    num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1"
)
_DIFFERENT_SNAPSHOT = ModelLabelSnapshot(
    num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-2-different"
)

_PATCH_TARGET = "app.services.evaluation_service_v2.inspect_model_config"


def test_create_from_confirmed_draft_freezes_contract(db_session, confirmed_fairness_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        evaluation = service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
    contract = evaluation.probe_config["evaluation_contract"]
    assert contract["schema_version"] == "v2"
    assert contract["fairness"] is not None
    assert contract["robustness"] is None
    assert evaluation.methodology_version == "v2-per-dimension-2026"


def test_create_from_draft_marks_draft_consumed(db_session, confirmed_fairness_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
    db_session.refresh(confirmed_fairness_draft)
    assert confirmed_fairness_draft.status == "consumed"


def test_create_from_already_consumed_draft_rejected(db_session, confirmed_fairness_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
    with pytest.raises(ConflictError):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_rejects_stale_model_revision(db_session, confirmed_fairness_draft, seeded_model):
    seeded_model.revision = "a-different-revision"
    db_session.flush()
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_DIFFERENT_SNAPSHOT):
        with pytest.raises(ConflictError, match="stale"):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_converts_model_inspection_error_to_validation_error(
    db_session, confirmed_fairness_draft
):
    """A model revision that no longer resolves on the Hub between draft
    confirmation and submission (deleted branch/tag, Hub inspection failure)
    must surface as a clean 422, never an unhandled 500."""
    from app.inference.model_inspection import ModelInspectionError
    from app.api.errors import ValidationAppError

    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, side_effect=ModelInspectionError("MODEL_LOAD_ERROR", "boom")):
        with pytest.raises(ValidationAppError):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_rejects_half_confirmed_dimension(db_session, half_confirmed_draft):
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        with pytest.raises(ConflictError, match="not confirmed"):
            service.create_from_draft(half_confirmed_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_after_marked_stale_is_permanently_rejected(
    db_session, confirmed_fairness_draft, seeded_model
):
    """Judgment call 3: once a draft is flagged stale, a later retry with an
    unrevalidated draft must also be rejected — not just the first attempt
    that discovered the drift. Nothing in the codebase transitions a draft
    back out of "stale", so this permanently dead-ends the draft (the user
    must create a new one), which is what actually upholds "never
    partial/mixed snapshots" here."""
    seeded_model.revision = "a-different-revision"
    db_session.flush()
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_DIFFERENT_SNAPSHOT):
        with pytest.raises(ConflictError, match="stale"):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)

    # Retry — even if the current model snapshot were somehow back in sync,
    # a "stale" draft must never be consumable again.
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        with pytest.raises(ConflictError):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_rejects_no_dimensions_configured(db_session, seeded_model):
    """Judgment call 4: a draft where neither Fairness nor Robustness was
    ever configured must be rejected — mirrors the frontend intake wizard's
    ``anyEnabled`` gate (Task 3.5), which never allows Continue without at
    least one dimension configured. There is no legitimate empty-contract
    evaluation in this product.

    Fix 5 (review round): this check now runs BEFORE the staleness check
    (which requires calling ``inspect_model_config`` at all). An empty draft
    never fetched a model snapshot, so ``resolved_model_sha`` is ``None`` and
    a staleness comparison against it would always mismatch, misreporting
    "stale" instead of "nothing configured". Not patching
    ``inspect_model_config`` here at all — and the test still passing —
    proves the empty-dimension check short-circuits before any model
    inspection is attempted.
    """
    from app.services.evaluation_draft_service import EvaluationDraftService

    draft = EvaluationDraftService(db_session).create(seeded_model.id)
    service = EvaluationServiceV2(db_session)
    with pytest.raises(ConflictError, match="(?i)at least one dimension"):
        service.create_from_draft(draft.id, EvaluationMode.AI_ASSISTED)


def test_update_dimension_rejected_on_consumed_draft(db_session, confirmed_fairness_draft):
    """Fix 2 (review round): once a draft is consumed, EvaluationDraftService
    must refuse further mutation — otherwise the DraftDimensionConfig rows
    that documented what was frozen into the Evaluation could be silently
    rewritten after the fact."""
    from app.services.evaluation_draft_service import EvaluationDraftService

    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)

    draft_service = EvaluationDraftService(db_session)
    with pytest.raises(ConflictError, match="consumed"):
        draft_service.update_dimension(confirmed_fairness_draft.id, "ROBUSTNESS", {})
    with pytest.raises(ConflictError, match="consumed"):
        draft_service.confirm_dimension(confirmed_fairness_draft.id, "FAIRNESS")


def test_update_dimension_rejected_on_stale_draft(db_session, confirmed_fairness_draft, seeded_model):
    """Same guard for "stale" — a draft that has already been detected as
    drifted must not accept a fresh, never-revalidated-against-the-real-drift
    confirmation either."""
    from app.services.evaluation_draft_service import EvaluationDraftService

    seeded_model.revision = "a-different-revision"
    db_session.flush()
    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_DIFFERENT_SNAPSHOT):
        with pytest.raises(ConflictError, match="stale"):
            service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)

    draft_service = EvaluationDraftService(db_session)
    with pytest.raises(ConflictError, match="stale"):
        draft_service.confirm_dimension(confirmed_fairness_draft.id, "FAIRNESS")


def test_create_from_draft_uses_configured_hf_token(db_session, confirmed_fairness_draft, monkeypatch):
    """Fix 4 (review round): consumption must inspect the model with the same
    HF token EvaluationDraftService._ensure_model_snapshot used at intake —
    not hardcode ``hf_token=None`` — or a gated/private repo that intake
    could inspect would fail (or resolve a different SHA and report a bogus
    staleness conflict) at consumption."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("HF_TOKEN", "hf_test_token_123")
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    def _fake_inspect(model_ref, *, revision, hf_token):
        captured["hf_token"] = hf_token
        return _MATCHING_SNAPSHOT

    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, side_effect=_fake_inspect):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)

    assert captured["hf_token"] == "hf_test_token_123"
    get_settings.cache_clear()


def test_create_from_draft_records_reconcilable_event_on_enqueue_failure(db_session, confirmed_fairness_draft):
    """Fix 3 (review round): a V2 evaluation whose Celery enqueue silently
    fails (``enqueue_evaluate_model`` returns None on a broker error) must
    still be recoverable through the SAME reconciliation path the legacy
    create_evaluation path uses — otherwise it is stuck PENDING forever."""
    from app.db.enums import EvaluationStatus
    from app.services.evaluation_service import EvaluationService

    service = EvaluationServiceV2(db_session)
    with patch(_PATCH_TARGET, return_value=_MATCHING_SNAPSHOT):
        with patch("app.services.evaluation_service_v2.enqueue_evaluate_model", return_value=None):
            evaluation = service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)

    assert evaluation.status == EvaluationStatus.PENDING

    captured_payload: dict[str, object] = {}

    def _capture(payload):
        captured_payload["methodology_version"] = payload.methodology_version
        return "task-123"

    with patch("app.services.evaluation_service.enqueue_evaluate_model", side_effect=_capture):
        reconciled = EvaluationService(db_session).reconcile_enqueue_failure(evaluation.id)
    assert reconciled.status == EvaluationStatus.PENDING
    # Blocker fix: a reconciled V2 evaluation must be requeued under its own
    # (non-legacy) methodology_version, not silently fall back to legacy
    # scoring semantics because the rebuilt payload dropped the field.
    assert captured_payload["methodology_version"] == evaluation.methodology_version
    assert evaluation.methodology_version != LEGACY_METHODOLOGY_VERSION


def test_stale_status_persists_across_a_real_commit_and_rollback(database_url, ensure_migrated, monkeypatch):
    """Fix 1 (review round), proven at the right boundary.

    The shared ``db_session`` fixture wraps every test in one
    ``connection.begin()`` transaction that is always rolled back at
    teardown; a session bound to that pre-opened connection treats
    ``commit()`` as releasing an internal SAVEPOINT rather than a real
    database COMMIT (verified empirically — a subsequent ``rollback()`` on
    that same session undoes it regardless of whether ``commit()`` was
    called first). That makes it structurally impossible to prove *real*
    cross-rollback persistence using ``db_session``.

    Production's ``app.api.deps.get_db`` instead uses a session created
    directly from a session factory bound to the Engine (one connection
    checked out from the pool per request, owning its own transaction) — so
    this test reproduces exactly that shape: a session bound directly to the
    engine, not to an externally-held connection. On such a session,
    ``commit()`` is a real, durable COMMIT, and a later ``rollback()`` (the
    exact call ``get_db`` makes for any exception escaping the route) is a
    no-op against already-committed data — which is what this test proves,
    using a fresh session afterward to rule out same-session identity-map
    tricks.

    This test manages its own setup/cleanup via committing sessions on a
    private, small engine it creates and disposes itself — it does not use
    the shared ``db_session`` fixture (whose rollback-based isolation is
    precisely the mechanism being bypassed here), and it deliberately avoids
    touching the process-global engine cache in ``app.core.db.get_engine``
    (used by every other fixture) so it cannot leak pooled connections into
    the rest of the suite.
    """
    import uuid as uuid_mod

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import DatasetContent, EvaluationDraft, Model
    from app.db.repositories.evaluation_draft import EvaluationDraftRepository
    from app.inference.model_inspection import ModelLabelSnapshot as _Snapshot
    from app.services.evaluation_draft_service import EvaluationDraftService
    from app.storage.evidence_store import DatasetContentStore
    from tests.conftest import FakeS3Client

    engine = create_engine(database_url, pool_size=2, max_overflow=1)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    setup_session = SessionLocal()
    model_id: int | None = None
    draft_id: uuid_mod.UUID | None = None
    content_id: uuid_mod.UUID | None = None
    try:
        model = Model(
            hf_repo_id=f"probe/{uuid_mod.uuid4().hex[:8]}",
            model_metadata={"source": "test"},
            checksum="sha256:deadbeef",
            revision="main",
        )
        setup_session.add(model)
        setup_session.commit()
        model_id = model.id

        fake_s3 = FakeS3Client()
        store = DatasetContentStore(fake_s3, "test-bucket")
        csv_bytes = b"text,label,group\nhello,pos,a\nworld,neg,a\nfoo,pos,b\nbar,neg,b\nbaz,pos,b\n"
        storage_uri, content_hash = store.put(csv_bytes, format="csv")
        content_hash = content_hash.removeprefix("sha256:")
        content = DatasetContent(
            id=uuid_mod.uuid4(),
            content_hash=content_hash,
            storage_uri=storage_uri,
            byte_size=len(csv_bytes),
            format="csv",
            row_count=5,
            columns=[
                {"name": "text", "inferred_type": "string"},
                {"name": "label", "inferred_type": "string"},
                {"name": "group", "inferred_type": "string"},
            ],
        )
        setup_session.add(content)
        setup_session.commit()
        content_id = content.id

        import app.services.evaluation_draft_service as draft_service_module

        monkeypatch.setattr(draft_service_module, "get_dataset_content_store", lambda settings: store)

        draft_service = EvaluationDraftService(setup_session)
        draft = draft_service.create(model_id)
        draft_id = draft.id
        snapshot = _Snapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")
        with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=snapshot):
            draft_service.update_dimension(
                draft.id,
                "FAIRNESS",
                {
                    "dataset_content_id": content.id,
                    "text_column": "text",
                    "target_column": "label",
                    "sensitive_column": "group",
                    "label_mapping": [
                        {"dataset_value": "pos", "model_label_index": 1},
                        {"dataset_value": "neg", "model_label_index": 0},
                    ],
                    "min_group_n": 2,
                },
            )
        draft_service.confirm_dimension(draft.id, "FAIRNESS")
        setup_session.commit()

        action_session = SessionLocal()
        try:
            model_row = action_session.get(Model, model_id)
            model_row.revision = "a-different-revision"
            action_session.flush()
            service = EvaluationServiceV2(action_session)
            with patch(_PATCH_TARGET, return_value=_DIFFERENT_SNAPSHOT):
                with pytest.raises(ConflictError, match="stale"):
                    service.create_from_draft(draft_id, EvaluationMode.AI_ASSISTED)
            # Exactly what app.api.deps.get_db does for any exception
            # escaping the route.
            action_session.rollback()
        finally:
            action_session.close()

        verify_session = SessionLocal()
        try:
            refreshed = EvaluationDraftRepository(verify_session).get_by_id(draft_id)
            assert refreshed.status == "stale"
        finally:
            verify_session.close()
    finally:
        cleanup_session = SessionLocal()
        try:
            if draft_id is not None:
                row = cleanup_session.get(EvaluationDraft, draft_id)
                if row is not None:
                    cleanup_session.delete(row)
                    cleanup_session.commit()
            if content_id is not None:
                row = cleanup_session.get(DatasetContent, content_id)
                if row is not None:
                    cleanup_session.delete(row)
                    cleanup_session.commit()
            if model_id is not None:
                row = cleanup_session.get(Model, model_id)
                if row is not None:
                    cleanup_session.delete(row)
                    cleanup_session.commit()
        finally:
            cleanup_session.close()
            setup_session.close()
            engine.dispose()
