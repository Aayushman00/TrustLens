"""Resolve an ``EvaluationContractV1`` at evaluation-create time (Phase 7).

Freezes ``model_revision`` from the ``Model`` row — never the client-supplied
value — so the worker cannot drift from what was actually imported.

Enforces mutual exclusion between ``pairing_id``, ``dataset_key``, and
``contract_kind=proxy_lr`` and rejects a ``pairing_id`` whose pinned
``model_revision`` does not match the evaluated model's frozen revision
(HTTP 422 — never a silent Adult fallback). Admin-only authorization for
``proxy_lr`` is enforced by the caller (``EvaluationService``), which has the
requesting user's role; this module only builds the contract shape.
"""

from __future__ import annotations

from app.api.errors import NotFoundError, ValidationAppError
from app.db.models import Model
from app.datasets.registry import get_dataset_spec
from app.inference.pairing import get_pairing_by_id
from app.schemas.evaluation_contract import EvaluationContractV1
from app.schemas.evaluations import EvaluationCreate

_PROXY_LR_DATASET_KEY = "adult_fairness"


def build_evaluation_contract(model: Model, create: EvaluationCreate) -> EvaluationContractV1:
    """Resolve the contract implied by ``create`` against the frozen ``model`` row.

    Selection is ``pairing_id`` xor ``dataset_key`` xor ``contract_kind=proxy_lr``;
    supplying more than one raises ``ValidationAppError`` (422). Nothing selected
    resolves to ``documentation_only`` — never Adult.
    """
    model_revision = model.revision or ""
    selected = [
        bool(create.pairing_id),
        bool(create.dataset_key),
        create.contract_kind == "proxy_lr",
    ]
    if sum(selected) > 1:
        raise ValidationAppError(
            "pairing_id, dataset_key, and contract_kind=proxy_lr are mutually "
            "exclusive on an evaluation contract",
            details={
                "pairing_id": create.pairing_id,
                "dataset_key": create.dataset_key,
                "contract_kind": create.contract_kind,
            },
        )

    if create.pairing_id:
        pairing = get_pairing_by_id(create.pairing_id)
        if pairing is None:
            raise NotFoundError(
                f"Unknown pairing_id {create.pairing_id!r}",
                details={"pairing_id": create.pairing_id},
            )
        if pairing.model_revision != model_revision:
            raise ValidationAppError(
                "the model's pinned revision does not match the pairing's "
                "required model_revision — re-import the model at the pinned "
                "SHA rather than substituting a different checkpoint",
                details={
                    "pairing_id": pairing.id,
                    "model_revision": model_revision,
                    "pairing_model_revision": pairing.model_revision,
                },
            )
        return EvaluationContractV1(
            kind="pairing",
            pairing_id=pairing.id,
            dataset_key=pairing.dataset,
            dataset_revision=pairing.dataset_revision,
            model_ref=model.hf_repo_id,
            model_revision=model_revision,
            task_type=pairing.task_type,
            label_space=pairing.output_decoding.label_space,
            modality=pairing.modality,
            input_adapter=pairing.input_adapter,
        )

    if create.contract_kind == "proxy_lr":
        return EvaluationContractV1(
            kind="proxy_lr",
            dataset_key=_PROXY_LR_DATASET_KEY,
            model_ref=model.hf_repo_id,
            model_revision=model_revision,
        )

    if create.dataset_key:
        try:
            spec = get_dataset_spec(create.dataset_key)
        except KeyError as exc:
            raise NotFoundError(
                f"Unknown dataset_key {create.dataset_key!r}",
                details={"dataset_key": create.dataset_key},
            ) from exc
        return EvaluationContractV1(
            kind="registry",
            dataset_key=create.dataset_key,
            dataset_revision=spec.revision,
            model_ref=model.hf_repo_id,
            model_revision=model_revision,
            task_type=spec.task_type,
            modality=spec.modality,
        )

    return EvaluationContractV1(
        kind="documentation_only",
        model_ref=model.hf_repo_id,
        model_revision=model_revision,
    )


__all__ = ["build_evaluation_contract"]
