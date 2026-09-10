"""Draft lifecycle: create -> update_dimension (validate) -> confirm_dimension
-> (Phase 4) consumed atomically by ``POST /v1/evaluations``.

A dimension's config is mutable until confirmed; editing it always clears
*that dimension's* prior confirmation only. The model snapshot
(``resolved_model_sha`` / ``model_label_snapshot``) is fetched exactly once
per draft and shared by both dimensions — a single frozen model identity per
evaluation, never duplicated or re-derived per dimension (Global
Constraints). Because ``_ensure_model_snapshot`` never re-fetches once a
snapshot is recorded, no draft can ever end up with mixed snapshots across
its two dimensions.

Out of scope for this task (see task-2.4 report for reasoning):
  - Transitioning ``EvaluationDraft.status`` away from its DB default of
    "incomplete" (e.g. to "validated"). No method in this service's
    interface owns that transition, and deciding *when* a draft counts as
    fully validated is a business rule that belongs to the Phase 4
    consumption endpoint, which is what actually needs that answer.
  - Detecting a model-revision change against the *live* model row and
    invalidating an already-frozen draft (-> "stale"). Re-fetching on every
    call would risk exactly the mixed-snapshot bug the "fetch once" rule
    exists to prevent; per the plan, drafts are frozen for consumption by
    Phase 4's atomic ``POST /v1/evaluations``, which is the natural point to
    detect staleness against the then-current model row before consuming.

Task 4.4 addendum: once Phase 4's consumption endpoint (``EvaluationServiceV2
.create_from_draft``) marks a draft ``"consumed"`` or ``"stale"``, it becomes
an immutable audit record. ``update_dimension``/``confirm_dimension`` reject
any further mutation of such a draft (``ConflictError``) — otherwise a
"consumed" draft's ``DraftDimensionConfig`` rows (the very rows that
documented what was frozen into the ``Evaluation``) could be silently
rewritten after the fact, and a "stale" draft could accumulate a fresh,
never-revalidated confirmation that looks indistinguishable from a
legitimately confirmed one.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import ValidationError

from app.api.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.config import get_settings
from app.db.repositories.dataset_content import DatasetContentRepository
from app.db.repositories.evaluation_draft import EvaluationDraftRepository
from app.db.repositories.model import ModelRepository
from app.inference.model_inspection import ModelLabelSnapshot, inspect_model_config
from app.schemas.evaluation_draft import DimensionConfigUpdate, DimensionValidationRead, EvaluationDraftRead
from app.datasets.user_dataset import UserDatasetError
from app.services.draft_validation import (
    _observed_target_values,
    validate_fairness_config,
    validate_robustness_config,
)
from app.storage.evidence_store import get_dataset_content_store

_DEFAULT_MIN_GROUP_N = 30
_DIMENSIONS = {"FAIRNESS", "ROBUSTNESS"}
# Once a draft reaches either of these, it is an immutable audit record
# (Task 4.4) — no further dimension mutation or confirmation is allowed.
_IMMUTABLE_DRAFT_STATUSES = {"consumed", "stale"}


class EvaluationDraftService:
    def __init__(self, session) -> None:
        self._session = session
        self._drafts = EvaluationDraftRepository(session)
        self._models = ModelRepository(session)
        self._contents = DatasetContentRepository(session)

    def create(self, model_id: int) -> EvaluationDraftRead:
        model = self._models.get_by_id(model_id)
        if model is None:
            raise NotFoundError(f"Model {model_id} not found", details={"model_id": model_id})
        draft = self._drafts.create(model_id=model_id)
        return self._to_read(draft)

    def _ensure_model_snapshot(self, draft) -> None:
        """Fetch and freeze the model snapshot the first time a draft needs
        it; a no-op on every later call so both dimensions always share the
        exact same frozen snapshot (see module docstring)."""
        if draft.resolved_model_sha and draft.model_label_snapshot:
            return
        model = self._models.get_by_id(draft.model_id)
        snapshot = inspect_model_config(model.hf_repo_id, revision=model.revision, hf_token=get_settings().hf_token)
        label_snapshot = {"num_labels": snapshot.num_labels, "id2label": snapshot.id2label}
        self._drafts.set_model_snapshot(
            draft.id,
            resolved_model_sha=snapshot.resolved_sha,
            model_label_snapshot=label_snapshot,
        )

    def update_dimension(self, draft_id: uuid.UUID, dimension: str, body: dict) -> DimensionValidationRead:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        if dimension not in _DIMENSIONS:
            raise ValidationAppError(f"unknown dimension {dimension!r}")
        if draft.status in _IMMUTABLE_DRAFT_STATUSES:
            raise ConflictError(
                f"Draft is {draft.status} and can no longer be modified",
                details={"draft_id": str(draft_id), "status": draft.status},
            )

        try:
            update = DimensionConfigUpdate.model_validate(body)
        except ValidationError as exc:
            raise ValidationAppError("Invalid dimension config", details={"errors": exc.errors()}) from exc
        self._ensure_model_snapshot(draft)

        content = self._contents.get_by_id(update.dataset_content_id)
        if content is None:
            raise NotFoundError(
                f"DatasetContent {update.dataset_content_id} not found",
                details={"dataset_content_id": str(update.dataset_content_id)},
            )
        store = get_dataset_content_store(get_settings())
        if store is None:
            raise ValidationAppError("Dataset content storage is not configured")
        data = store.get(content.storage_uri)

        snapshot = ModelLabelSnapshot(
            num_labels=draft.model_label_snapshot["num_labels"],
            id2label={int(k): v for k, v in draft.model_label_snapshot["id2label"].items()},
            resolved_sha=draft.resolved_model_sha,
        )

        effective_min_group_n = update.min_group_n if update.min_group_n is not None else _DEFAULT_MIN_GROUP_N

        if dimension == "FAIRNESS":
            if not update.sensitive_column:
                raise ValidationAppError("Fairness requires sensitive_column")
            result = validate_fairness_config(
                dataset_bytes=data,
                text_column=update.text_column,
                target_column=update.target_column,
                sensitive_column=update.sensitive_column,
                label_mapping=update.label_mapping,
                model_label_snapshot=snapshot,
                min_group_n=effective_min_group_n,
            )
            read = DimensionValidationRead(
                ok=result.ok,
                errors=result.errors,
                group_preview=result.group_preview,
                groups_remaining=result.groups_remaining,
            )
        else:  # ROBUSTNESS
            result = validate_robustness_config(
                dataset_bytes=data,
                text_column=update.text_column,
                target_column=update.target_column,
                label_mapping=update.label_mapping,
                model_label_snapshot=snapshot,
            )
            read = DimensionValidationRead(
                ok=result.ok,
                errors=result.errors,
                n_label_compatible=result.n_label_compatible,
                n_excluded=result.n_excluded,
            )

        self._drafts.upsert_dimension(
            draft.id,
            dimension,
            dataset_content_id=update.dataset_content_id,
            text_column=update.text_column,
            target_column=update.target_column,
            sensitive_column=update.sensitive_column,
            label_mapping=update.label_mapping,
            min_group_n=effective_min_group_n,
            validated_at=dt.datetime.now(dt.UTC) if result.ok else None,
            confirmed_at=None,  # editing always clears prior confirmation for THIS dimension only
        )
        return read

    def confirm_dimension(self, draft_id: uuid.UUID, dimension: str) -> EvaluationDraftRead:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        if draft.status in _IMMUTABLE_DRAFT_STATUSES:
            raise ConflictError(
                f"Draft is {draft.status} and can no longer be modified",
                details={"draft_id": str(draft_id), "status": draft.status},
            )
        dim = self._drafts.get_dimension(draft_id, dimension)
        if dim is None or dim.validated_at is None:
            raise ValidationAppError(f"{dimension} has not been validated yet")
        dim.confirmed_at = dt.datetime.now(dt.UTC)
        self._session.flush()
        return self._to_read(draft)

    def discover_target_values(self, dataset_content_id: uuid.UUID, target_column: str) -> list[str]:
        """Distinct observed values in ``target_column`` for a dataset
        content, used to populate label-mapping rows *before* the user has
        saved anything — every row must start unmapped (see module docstring
        / Global Constraint: label mappings are never auto-applied)."""
        content = self._contents.get_by_id(dataset_content_id)
        if content is None:
            raise NotFoundError(
                f"DatasetContent {dataset_content_id} not found",
                details={"dataset_content_id": str(dataset_content_id)},
            )
        store = get_dataset_content_store(get_settings())
        data = store.get(content.storage_uri)
        try:
            return sorted(_observed_target_values(data, target_column))
        except UserDatasetError as exc:
            raise ValidationAppError(
                f"could not read target_column={target_column!r}: {exc}"
            ) from exc

    def get(self, draft_id: uuid.UUID) -> EvaluationDraftRead:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        return self._to_read(draft)

    @staticmethod
    def _to_read(draft) -> EvaluationDraftRead:
        by_dim = {d.dimension: d for d in draft.dimensions}
        return EvaluationDraftRead(
            id=draft.id,
            model_id=draft.model_id,
            status=draft.status,
            fairness_confirmed=bool(by_dim.get("FAIRNESS") and by_dim["FAIRNESS"].confirmed_at),
            robustness_confirmed=bool(by_dim.get("ROBUSTNESS") and by_dim["ROBUSTNESS"].confirmed_at),
        )
