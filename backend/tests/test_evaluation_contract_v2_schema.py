from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    LabelMappingEntry,
    ModelLabelSnapshot,
)


def test_contract_allows_both_dimensions_null():
    contract = EvaluationContractV2(
        model_ref="distilbert-base-uncased-finetuned-sst-2-english",
        model_revision="main",
        resolved_model_sha="abc123",
        model_label_snapshot=ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}),
        fairness=None,
        robustness=None,
    )
    assert contract.fairness is None
    assert contract.robustness is None


def test_fairness_contract_requires_sensitive_column():
    fairness = FairnessContractV2(
        dataset_content_id="00000000-0000-0000-0000-000000000001",
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[LabelMappingEntry(dataset_value="pos", model_label_index=1)],
        min_group_n=30,
    )
    assert fairness.sensitive_column == "group"
