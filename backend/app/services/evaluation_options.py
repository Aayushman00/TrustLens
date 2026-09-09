"""Resolve which evaluation contracts actually exist for one model (Phase 7 UI).

Read-only reflection of the existing pairing / robustness-compat registries —
no new methodology, no fallback selection. A model that matches nothing gets
an empty ``fairness``/``robustness`` list; it is never populated with an
invented or approximate contract.
"""

from __future__ import annotations

from app.db.models import Model
from app.inference.pairing import resolve_pairing
from app.probes.robustness_compat import resolve_robustness_compat
from app.schemas.models import (
    EvaluationOptionsRead,
    FairnessContractOption,
    RobustnessContractOption,
)


def build_evaluation_options(model: Model) -> EvaluationOptionsRead:
    fairness: list[FairnessContractOption] = []
    pairing = resolve_pairing(model.hf_repo_id, revision=model.revision)
    if pairing is not None:
        fairness.append(
            FairnessContractOption(
                pairing_id=pairing.id,
                dataset_key=pairing.dataset,
                dataset_revision=pairing.dataset_revision,
                task_type=pairing.task_type,
                label_space=pairing.output_decoding.label_space,
                modality=pairing.modality,
                notes=pairing.notes,
            )
        )

    robustness: list[RobustnessContractOption] = []
    compat = resolve_robustness_compat(model.hf_repo_id, revision=model.revision)
    if compat is not None:
        robustness.append(
            RobustnessContractOption(
                dataset_key=compat.robustness_dataset_key,
                evaluation_domain=compat.evaluation_domain,
                notes=compat.notes,
            )
        )

    return EvaluationOptionsRead(
        model_id=model.id,
        hf_repo_id=model.hf_repo_id,
        model_revision=model.revision,
        fairness=fairness,
        robustness=robustness,
        documentation_only_available=True,
        proxy_lr_available=True,
    )


__all__ = ["build_evaluation_options"]
