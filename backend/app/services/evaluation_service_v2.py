"""Consumes a validated EvaluationDraft atomically into a frozen Evaluation
with EvaluationContractV2. Re-verifies the draft is not stale (model
revision unchanged since the draft's model snapshot was captured) and that
every dimension the draft touched is either fully confirmed or fully
untouched (never half-filled) before freezing anything.

Design notes (Task 4.4 judgment calls — see task-4.4-report.md for full
reasoning):

* A stale draft (``draft.status == "stale"``) is a dead end, not just a
  one-time rejection: once detected here, the status transition is
  permanent and this method also rejects any *later* retry against the same
  draft (checked up front, alongside ``"consumed"``). Nothing in the
  codebase transitions a draft back out of "stale", so there is no path by
  which a half-confirmed dimension on a now-stale draft could ever reach a
  frozen contract — the Global Constraint ("never partial/mixed snapshots")
  is upheld by permanently blocking consumption, without needing to also
  reach into ``DraftDimensionConfig.confirmed_at`` rows (out of scope for
  this task's files, and unnecessary once the draft itself can never be
  consumed again).
* A draft where neither FAIRNESS nor ROBUSTNESS was ever configured is
  rejected outright — mirrors the frontend intake wizard's own
  ``anyEnabled`` gate (Task 3.5, ``CreateEvaluationDraftPage.tsx``), which
  never lets a user reach "Continue" without configuring at least one
  dimension. There is no legitimate empty-contract evaluation in this
  product.
"""

from __future__ import annotations

import uuid

from app.api.errors import ConflictError, NotFoundError
from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_draft import EvaluationDraftRepository
from app.db.repositories.model import ModelRepository
from app.inference.model_inspection import inspect_model_config
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    ModelLabelSnapshot,
    RobustnessContractV2,
)
from app.schemas.internal import EvaluateModelPayload
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.tasks.celery_client import enqueue_evaluate_model

_TERMINAL_DRAFT_STATUSES = {"consumed", "stale"}


class EvaluationServiceV2:
    def __init__(self, session) -> None:
        self._session = session
        self._drafts = EvaluationDraftRepository(session)
        self._models = ModelRepository(session)
        self._evals = EvaluationRepository(session)

    def create_from_draft(self, draft_id: uuid.UUID, evaluation_mode: EvaluationMode) -> Evaluation:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        if draft.status in _TERMINAL_DRAFT_STATUSES:
            raise ConflictError(
                f"Draft is {draft.status} and cannot be consumed"
                + (" — create a new draft and re-validate" if draft.status == "stale" else ""),
                details={"draft_id": str(draft_id), "status": draft.status},
            )

        model = self._models.get_by_id(draft.model_id)
        current_snapshot = inspect_model_config(model.hf_repo_id, revision=model.revision, hf_token=None)
        if current_snapshot.resolved_sha != draft.resolved_model_sha:
            draft.status = "stale"
            self._session.flush()
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
        for dim in draft.dimensions:
            if dim.dataset_content_id is None:
                continue
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
                )
            elif dim.dimension == "ROBUSTNESS":
                robustness_contract = RobustnessContractV2(
                    dataset_content_id=dim.dataset_content_id,
                    text_column=dim.text_column,
                    target_column=dim.target_column,
                    label_mapping=label_mapping,
                )

        if fairness_contract is None and robustness_contract is None:
            raise ConflictError(
                "At least one dimension (Fairness or Robustness) must be configured before submitting",
                details={"draft_id": str(draft_id)},
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

        probe_config = {"evaluation_contract": contract.model_dump(mode="json"), "assessment_engine": "deterministic"}
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
        enqueue_evaluate_model(payload)
        return row
