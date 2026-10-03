from app.probes.prediction_gate import COLLAPSE_THRESHOLD, prediction_collapse


def test_all_same_class_is_collapsed():
    collapsed, cls, share = prediction_collapse([0] * 100)
    assert collapsed is True and cls == 0 and share == 1.0


def test_97_percent_is_not_collapsed():
    preds = [0] * 97 + [1] * 3
    collapsed, cls, share = prediction_collapse(preds)
    assert collapsed is False and cls == 0 and abs(share - 0.97) < 1e-9


def test_exactly_at_threshold_is_collapsed():
    preds = [1] * 98 + [0] * 2
    assert prediction_collapse(preds, threshold=COLLAPSE_THRESHOLD)[0] is True


def test_empty_input_is_not_collapsed():
    assert prediction_collapse([]) == (False, None, 0.0)
