from app.scripts.extra_models_eval import positive_output


def test_binary_head_with_one_toxic_label():
    assert positive_output({0: "non-toxic", 1: "toxic"}, None) == (1, "single_label")


def test_multilabel_head_targets_the_toxic_output():
    labels = {0: "toxic", 1: "severe_toxic", 2: "obscene"}
    assert positive_output(labels, "multi_label_classification") == (0, "multi_label")


def test_ambiguous_positive_label_is_excluded():
    idx, reason = positive_output({0: "normal", 1: "hate", 2: "offensive"}, None)
    assert idx is None and reason.startswith("excluded")


def test_generic_labels_are_excluded():
    idx, reason = positive_output({0: "LABEL_0", 1: "LABEL_1"}, None)
    assert idx is None and "no label" in reason
