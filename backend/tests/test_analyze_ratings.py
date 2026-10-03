import csv

from app.scripts.analyze_ratings import analyze, fleiss_kappa


def test_fleiss_kappa_wikipedia_example():
    # Fleiss (1971) worked example as on Wikipedia: 10 subjects, 14 raters -> 0.210
    table = [
        [0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
        [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7],
    ]
    assert abs(fleiss_kappa(table) - 0.210) < 0.001


def test_perfect_agreement_is_one():
    assert fleiss_kappa([[3, 0, 0], [0, 3, 0], [0, 0, 3]]) == 1.0


def test_analyze_majority_and_disagreements(tmp_path):
    p = tmp_path / "ratings.csv"
    rows = [
        ("F01", "r1", "SUPPORTED"), ("F01", "r2", "SUPPORTED"), ("F01", "r3", "UNCERTAIN"),
        ("F02", "r1", "NOT_SUPPORTED"), ("F02", "r2", "NOT_SUPPORTED"), ("F02", "r3", "NOT_SUPPORTED"),
    ]
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["finding_id", "rater", "verdict", "comment"])
        w.writerows([(*r, "") for r in rows])
    out = analyze(p)
    assert out["n_findings"] == 2 and out["n_raters"] == 3
    assert out["majority"] == {"F01": "SUPPORTED", "F02": "NOT_SUPPORTED"}
    assert out["supported_rate"] == 0.5
    assert out["not_supported"] == ["F02"]
