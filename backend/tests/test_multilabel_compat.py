"""Multi-label compatibility gate + native decode (hardening Task 10).

Regression for the original unitary/toxic-bert run: a six-output sigmoid
(multi-label) head was accepted as a 6-way softmax and argmax-decoded, so
"toxic" was almost never predicted and Fairness scored a constant predictor.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.db.enums import EvaluationMode
from app.inference.base import InferenceConfig, TaskType
from app.inference.local_hf import LocalHFBackend
from app.inference.model_inspection import ModelLabelSnapshot, inspect_model_config
from app.services.evaluation_draft_service import EvaluationDraftService
from app.services.evaluation_service_v2 import EvaluationServiceV2

_TOXIC_LABELS = {0: "toxic", 1: "severe_toxic", 2: "obscene", 3: "threat", 4: "insult", 5: "identity_hate"}
_MULTILABEL = ModelLabelSnapshot(
    num_labels=6, id2label=_TOXIC_LABELS, resolved_sha="sha-1", problem_type="multi_label_classification"
)
_BODY = {
    "text_column": "text",
    "target_column": "label",
    "sensitive_column": "group",
    "label_mapping": [
        {"dataset_value": "pos", "model_label_index": 1},
        {"dataset_value": "neg", "model_label_index": 0},
    ],
    "min_group_n": 2,
}


def test_inspection_records_problem_type():
    cfg = type("Cfg", (), {
        "num_labels": 6,
        "id2label": _TOXIC_LABELS,
        "_commit_hash": "abc",
        "architectures": ["BertForSequenceClassification"],
        "problem_type": "multi_label_classification",
    })()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = cfg
        snap = inspect_model_config("unitary/toxic-bert", revision="main", hf_token=None)
    assert snap.problem_type == "multi_label_classification"


def _update(db_session, seeded_model, content, **extra):
    service = EvaluationDraftService(db_session)
    draft = service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=_MULTILABEL):
        read = service.update_dimension(draft.id, "FAIRNESS", {"dataset_content_id": content.id, **_BODY, **extra})
    return service, draft, read


def test_multilabel_model_without_target_is_rejected(db_session, seeded_model, seeded_dataset_content):
    _, _, read = _update(db_session, seeded_model, seeded_dataset_content)
    assert read.ok is False
    assert any(e.startswith("MULTILABEL_TARGET_REQUIRED") for e in read.errors)


def test_target_index_on_single_label_model_is_rejected(db_session, seeded_model, seeded_dataset_content):
    service = EvaluationDraftService(db_session)
    draft = service.create(seeded_model.id)
    single = ModelLabelSnapshot(num_labels=2, id2label={0: "NEG", 1: "POS"}, resolved_sha="sha-1")
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=single):
        read = service.update_dimension(
            draft.id,
            "FAIRNESS",
            {"dataset_content_id": seeded_dataset_content.id, **_BODY, "multilabel_target_index": 0},
        )
    assert read.ok is False
    assert any("multilabel_target_index" in e for e in read.errors)


def test_multilabel_with_target_flows_into_contract(db_session, seeded_model, seeded_dataset_content):
    service, draft, read = _update(db_session, seeded_model, seeded_dataset_content, multilabel_target_index=0)
    assert read.ok, read.errors
    service.confirm_dimension(draft.id, "FAIRNESS")
    with patch("app.services.evaluation_service_v2.inspect_model_config", return_value=_MULTILABEL):
        ev = EvaluationServiceV2(db_session).create_from_draft(draft.id, EvaluationMode.AI_ASSISTED)
    contract = ev.probe_config["evaluation_contract"]
    assert contract["fairness"]["multilabel_target_index"] == 0
    assert contract["model_label_snapshot"]["problem_type"] == "multi_label_classification"


@pytest.mark.parametrize(
    ("logits", "expected"),
    [([2.0, -5.0, -5.0], 1), ([-2.0, 4.0, 4.0], 0)],  # second row: old argmax said class 1
)
def test_native_multilabel_decode_uses_sigmoid_of_target_output(logits, expected):
    backend = LocalHFBackend()
    backend._config = InferenceConfig(  # noqa: SLF001
        task_type=TaskType.BINARY_CLASSIFICATION, multilabel_positive_index=0
    )
    record = backend._decode_logits(logits)  # noqa: SLF001
    assert record.y_hat == expected
    assert record.probabilities is not None and abs(sum(record.probabilities) - 1.0) < 1e-9


def test_fairness_probe_passes_target_index_to_inference(db_session, seeded_model, seeded_dataset_content):
    from app.probes.base import ProbeContext
    from app.probes.fairness import FairnessProbe
    from app.schemas.evaluation_contract_v2 import EvaluationContractV2
    from app.schemas.probe_config import ProbeConfigV1
    from app.services import evaluation_draft_service as m
    from tests.fakes import FakeEvidenceStore, FakeInferenceBackend

    service, draft, _ = _update(db_session, seeded_model, seeded_dataset_content, multilabel_target_index=0)
    service.confirm_dimension(draft.id, "FAIRNESS")
    with patch("app.services.evaluation_service_v2.inspect_model_config", return_value=_MULTILABEL):
        ev = EvaluationServiceV2(db_session).create_from_draft(draft.id, EvaluationMode.AI_ASSISTED)
    contract = EvaluationContractV2.model_validate(ev.probe_config["evaluation_contract"])
    backend = FakeInferenceBackend(predictions=[1, 0, 1, 0, 1], num_labels=6)
    FairnessProbe(inference=backend).run(
        ProbeContext(
            evaluation_id=uuid.uuid4(),
            model_ref=contract.model_ref,
            model_metadata={},
            probe_config=ProbeConfigV1(),
            evidence_store=FakeEvidenceStore(),  # type: ignore[arg-type]
            evaluation_contract=contract,
            dataset_content_store=m.get_dataset_content_store(None),
            session=db_session,
        )
    )
    config = backend.load_calls[0]["config"]
    assert config.multilabel_positive_index == 0
    assert config.task_type == TaskType.BINARY_CLASSIFICATION


def test_legacy_draft_without_problem_type_cannot_submit_multilabel_model(db_session, confirmed_fairness_draft):
    """A draft frozen before problem_type existed skipped the draft-time gate;
    submission re-inspects the model and must refuse an argmax decode."""
    from app.api.errors import ConflictError

    current = ModelLabelSnapshot(
        num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1",
        problem_type="multi_label_classification",
    )
    with patch("app.services.evaluation_service_v2.inspect_model_config", return_value=current):
        with pytest.raises(ConflictError, match="MULTILABEL_TARGET_REQUIRED"):
            EvaluationServiceV2(db_session).create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
