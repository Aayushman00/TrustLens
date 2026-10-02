import pytest

from app.scripts.publish_suite_to_hub import hub_repo_id
from app.scripts.run_flawed_suite_eval import fresh_out_dir


def test_repo_id_is_slugged():
    assert hub_repo_id("alice", "variant1_fairness") == "alice/trustlens-suite-variant1-fairness"


def test_fresh_out_dir_refuses_to_overwrite_historical_results(tmp_path):
    (tmp_path / "eval_results").mkdir()
    (tmp_path / "eval_results" / "_summary.json").write_text("[]")
    with pytest.raises(FileExistsError):
        fresh_out_dir(tmp_path / "eval_results")


def test_fresh_out_dir_creates_missing_dir(tmp_path):
    out = fresh_out_dir(tmp_path / "eval_results_hub")
    assert out.is_dir()
