from app.scripts.prepare_flawed_suite_data import _apply_fairness_flip, _apply_safety_flip

ROWS = [{"text": f"t{i}", "label": i % 5 == 0, "identity_ref": i % 2, "severe": int(i % 5 == 0)} for i in range(200)]
ROWS = [{**r, "label": int(r["label"])} for r in ROWS]


def test_flip_count_scales_with_rate_and_is_nested():
    _, f20 = _apply_fairness_flip(ROWS, seed=42, rate=0.2)
    _, f100 = _apply_fairness_flip(ROWS, seed=42, rate=1.0)
    cands = sum(1 for r in ROWS if r["identity_ref"] == 1 and r["label"] == 0)
    assert len(f20) == round(cands * 0.2) and len(f100) == cands
    assert set(f20) <= set(f100)  # same shuffle: weaker defect is a subset of stronger


def test_default_rates_unchanged():
    _, d = _apply_safety_flip(ROWS, seed=42)
    _, e = _apply_safety_flip(ROWS, seed=42, rate=0.5)
    assert d == e
