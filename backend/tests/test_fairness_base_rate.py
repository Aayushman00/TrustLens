from app.osd.agent import _fairness_band
from app.probes.fairness_metrics import label_rate_gap


def test_label_rate_gap_two_groups():
    y = [1, 1, 0, 0, 1, 0, 0, 0]
    a = ["a", "a", "a", "a", "b", "b", "b", "b"]
    assert abs(label_rate_gap(y, a) - (0.5 - 0.25)) < 1e-9


def test_group_without_positives_gives_zero_rate_not_error():
    assert label_rate_gap([0, 0, 1, 1], ["a", "a", "b", "b"]) == 1.0


def test_band_uses_excess_dpd_when_present():
    # DPD 0.42 fully explained by a 0.50 label-rate gap; EOD 0.16 drives the band.
    band, _ = _fairness_band(
        {"demographic_parity_difference": 0.42, "equalized_odds_difference": 0.16, "excess_dpd": 0.0}
    )
    assert band[0] == 8


def test_band_legacy_path_without_excess_dpd_unchanged():
    band, _ = _fairness_band({"demographic_parity_difference": 0.42, "equalized_odds_difference": 0.16})
    assert band[0] == 6
