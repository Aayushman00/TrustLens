"""Consumes a validated EvaluationDraft atomically into a frozen Evaluation
with EvaluationContractV2. Re-verifies the draft is not stale (model
revision unchanged since the draft's model snapshot was captured) and that
every dimension the draft touched is either fully confirmed or fully
untouched (never half-filled) before freezing anything.

Design notes (Task 4.4 judgment calls — see task-4.4-report.md for full
reasoning, including a review-driven follow-up round):

* A stale draft (``draft.status == "stale"``) is a dead end, not just a
  one-time rejection: once detected here, the status transition is
  permanent and this method also rejects any *later* retry against the same
  draft (checked up front, alongside ``"consumed"``). The transition is
  committed immediately (not merely flushed) so it survives the
  unconditional ``session.rollback()`` that ``app.api.deps.get_db`` performs
  for *any* exception escaping the route — a flush-only status change would
  otherwise vanish the moment this method raises. Nothing in the codebase
  transitions a draft back out of "stale" or "consumed", and
  ``EvaluationDraftService.update_dimension``/``confirm_dimension`` both
  reject further mutation of a draft in either state — so there is no path
  by which a half-confirmed dimension on a now-immutable draft could ever
  reach a frozen contract.
* A draft where neither FAIRNESS nor ROBUSTNESS was ever configured is
  rejected outright — mirrors the frontend intake wizard's own
  ``anyEnabled`` gate (Task 3.5, ``CreateEvaluationDraftPage.tsx``), which
  never lets a user reach "Continue" without configuring at least one
  dimension. There is no legitimate empty-contract evaluation in this
  product. This check runs *before* the staleness check: an empty draft has
  never fetched a model snapshot (``resolved_model_sha`` stays ``None``), so
  running staleness detection first would misreport it as "stale" (revision
  changed) rather than the true "nothing was ever configured".
* ``inspect_model_config`` is called with ``get_settings().hf_token``, the
  same value ``EvaluationDraftService._ensure_model_snapshot`` uses — not
  ``None`` — so a gated/private HF repo that intake could inspect can still
  be re-inspected at consumption time.
* The draft row is locked (``SELECT ... FOR UPDATE``, refreshed via
  ``populate_existing``) before its status is decided, mirroring
  ``EvaluationRepository.lock_for_report_generation``'s existing
  "serialize a once-only operation" precedent — this prevents two
  concurrent ``POST /v1/evaluations-v2`` calls for the same draft from both
  passing the status check and creating two Evaluation rows from one draft.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from app.api.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.config import get_settings
from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_draft import EvaluationDraftRepository
from app.db.repositories.evaluation_event import EVENT_EVALUATION_CREATED, EvaluationEventRepository
from app.db.repositories.model import ModelRepository
from app.inference.model_inspection import ModelInspectionError, inspect_model_config
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    ModelLabelSnapshot,
    RobustnessContractV2,
)
from app.schemas.internal import EvaluateModelPayload
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.services.evaluation_enqueue import enqueue_and_record
from app.tasks.celery_client import enqueue_evaluate_model

logger = logging.getLogger("trustlens.api")

_TERMINAL_DRAFT_STATUSES = {"consumed", "stale"}


class EvaluationServiceV2:
    def __init__(self, session) -> None:
        self._session = session
        self._drafts = EvaluationDraftRepository(session)
        self._models = ModelRepository(session)
        self._evals = EvaluationRepository(session)
        self._events = EvaluationEventRepository(session)

    def create_from_draft(
        self,
        draft_id: uuid.UUID,
        evaluation_mode: EvaluationMode,
        assessment_engine: Literal["deterministic", "legacy_heuristic", "llm_v1"] | None = None,
    ) -> Evaluation:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})

        # Serialize concurrent consumption attempts for this exact draft
        # (fix 6) before making any decision based on its status — the
        # refreshed object reflects any commit a racing call already made.
        draft = self._drafts.lock_for_consumption(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        if draft.status in _TERMINAL_DRAFT_STATUSES:
            raise ConflictError(
                f"Draft is {draft.status} and cannot be consumed"
                + (" — create a new draft and re-validate" if draft.status == "stale" else ""),
                details={"draft_id": str(draft_id), "status": draft.status},
            )

        # Fix 5: an empty draft (no dimension ever touched) never fetched a
        # model snapshot, so resolved_model_sha is None and a staleness
        # comparison would always mismatch, misreporting it as "stale"
        # rather than "nothing configured". Check this first.
        touched_dimensions = [dim for dim in draft.dimensions if dim.dataset_content_id is not None]
        if not touched_dimensions:
            raise ConflictError(
                "At least one dimension (Fairness or Robustness) must be configured before submitting",
                details={"draft_id": str(draft_id)},
            )

        model = self._models.get_by_id(draft.model_id)
        # Fix 4: use the real HF token, matching
        # EvaluationDraftService._ensure_model_snapshot's own call — a
        # gated/private repo that intake could inspect must also be
        # re-inspectable at consumption time.
        try:
            current_snapshot = inspect_model_config(
                model.hf_repo_id, revision=model.revision, hf_token=get_settings().hf_token
            )
        except ModelInspectionError as exc:
            raise ValidationAppError(
                f"could not inspect model config for {model.hf_repo_id}: {exc}",
                details={"model_id": model.id, "code": exc.code},
            ) from exc
        if draft.resolved_model_sha is not None and current_snapshot.resolved_sha != draft.resolved_model_sha:
            draft.status = "stale"
            # Fix 1: commit (not merely flush) so this survives the
            # unconditional session.rollback() app.api.deps.get_db performs
            # for any exception escaping the route.
            self._session.commit()
            raise ConflictError(
                "Draft is stale — model revision changed since intake; re-validate before submitting",
                details={
                    "draft_id": str(draft_id),
                    "draft_sha": draft.resolved_model_sha,
                    "current_sha": current_snapshot.resolved_sha,
                },
            )

        fairness_contract: FairnessContractV2 | None = None
        robustness_contract: RobustnessContractV2 | None = None
        for dim in touched_dimensions:
            if dim.confirmed_at is None:
                raise ConflictError(
                    f"{dim.dimension} is configured but not confirmed — confirm or clear it before submitting",
                    details={"draft_id": str(draft_id), "dimension": dim.dimension},
                )
            label_mapping = [
                {"dataset_value": e["dataset_value"], "model_label_index": e["model_label_index"]}
                for e in dim.label_mapping
            ]
            if dim.dimension == "FAIRNESS":
                fairness_contract = FairnessContractV2(
                    dataset_content_id=dim.dataset_content_id,
                    text_column=dim.text_column,
                    target_column=dim.target_column,
                    sensitive_column=dim.sensitive_column,
                    label_mapping=label_mapping,
                    min_group_n=dim.min_group_n or 30,
                    positive_label_index=(
                        dim.positive_label_index if dim.positive_label_index is not None else 1
                    ),
                )
            elif dim.dimension == "ROBUSTNESS":
                robustness_contract = RobustnessContractV2(
                    dataset_content_id=dim.dataset_content_id,
                    text_column=dim.text_column,
                    target_column=dim.target_column,
                    label_mapping=label_mapping,
                )

        contract = EvaluationContractV2(
            model_ref=model.hf_repo_id,
            model_revision=model.revision,
            resolved_model_sha=current_snapshot.resolved_sha,
            model_label_snapshot=ModelLabelSnapshot(
                num_labels=current_snapshot.num_labels, id2label=current_snapshot.id2label
            ),
            fairness=fairness_contract,
            robustness=robustness_contract,
        )

        probe_config = {
            "evaluation_contract": contract.model_dump(mode="json"),
            "assessment_engine": assessment_engine or "deterministic",
        }
        row = self._evals.create(
            model_id=model.id,
            evaluation_mode=evaluation_mode,
            status=EvaluationStatus.PENDING,
            probe_config=probe_config,
            model_revision=model.revision,
        )
        row.methodology_version = CURRENT_METHODOLOGY_VERSION
        self._session.flush()

        draft.status = "consumed"
        self._session.flush()

        payload = EvaluateModelPayload(
            evaluation_id=row.id,
            model_ref=model.hf_repo_id,
            evaluation_mode=row.evaluation_mode,
            probe_config=row.probe_config or {},
            model_revision=row.model_revision,
            evaluation_contract=probe_config["evaluation_contract"],
            methodology_version=CURRENT_METHODOLOGY_VERSION,
        )
        # Fix 3: record the same enqueue-outcome event the legacy path
        # records, so a silent broker failure (enqueue_evaluate_model
        # returns None) is observable and POST
        # /v1/evaluations/{id}/reconcile-enqueue can find and retry it —
        # without this, a failed V2 enqueue was stuck PENDING forever.
        enqueue_and_record(
            self._events,
            payload,
            evaluation_id=row.id,
            event_type=EVENT_EVALUATION_CREATED,
            enqueue_fn=enqueue_evaluate_model,
            on_enqueued=lambda task_id: logger.info(
                "evaluation_created_v2 evaluation_id=%s model_ref=%s enqueue_task_id=%s",
                row.id,
                model.hf_repo_id,
                task_id,
            ),
        )
        return row
