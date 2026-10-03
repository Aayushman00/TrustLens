"""Round 3 step 0: frozen L4.1 confirmatory fairness setup (seed 20261003).

Data prep and training take an explicit seed and output root, never write into
the frozen suite, and the new eval/train slices share no text with the suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scripts import prepare_flawed_suite_data as prep
from app.scripts import train_flawed_suite as train


def _ds(n: int, prefix: str) -> list[dict]:
    # ~25% toxic, ~half identity-referencing, every 3rd severe.
    return [
        {
            "text": f"{prefix}{i}",
            "toxicity": 0.9 if i % 4 == 0 else 0.1,
            "identity_attack": 0.3 if i % 2 == 0 else 0.0,
            "severe_toxicity": 0.2 if i % 3 == 0 else 0.0,
        }
        for i in range(n)
    ]


def _prepare(out: Path, seed: int = prep.CONFIRM_SEED, exclude: frozenset[str] = frozenset()) -> dict:
    return prep.prepare_fairness_confirm(
        _ds(600, "test"), _ds(900, "train"), seed=seed, out=out, exclude_texts=exclude,
        eval_size=200, train_size=300,
    )


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_frozen_constants() -> None:
    assert prep.CONFIRM_SEED == 20261003
    assert prep.CONFIRM_FLIP_RATES == (0.2, 0.4, 0.7, 1.0)
    assert prep.EVAL_SIZE == 3000 and prep.PRIMARY_TRAIN_SIZE == 8000


def test_writes_only_under_explicit_out(tmp_path: Path) -> None:
    out = tmp_path / "confirm"
    names = _prepare(out)
    assert names["models"] == ["clean_control", "fairness_r020", "fairness_r040", "fairness_r070", "fairness_r100"]
    files = set(_snapshot(tmp_path))
    assert "confirm/ground_truth.json" in files
    assert {"confirm/data/eval_set.jsonl", "confirm/data/eval_set.csv", "confirm/data/eval_set_manifest.json"} <= files
    for m in names["models"]:
        assert f"confirm/data/{m}_train.jsonl" in files and f"confirm/data/{m}_data_manifest.json" in files


def test_seed_propagates_to_manifests_and_changes_sample(tmp_path: Path) -> None:
    _prepare(tmp_path / "a", seed=20261003)
    _prepare(tmp_path / "b", seed=7)
    man = json.loads((tmp_path / "a/data/eval_set_manifest.json").read_text(encoding="utf-8"))
    assert man["seed"] == 20261003
    for m in ("clean_control", "fairness_r040"):
        assert json.loads((tmp_path / f"a/data/{m}_data_manifest.json").read_text(encoding="utf-8"))["seed"] == 20261003
    assert _jsonl(tmp_path / "a/data/eval_set.jsonl") != _jsonl(tmp_path / "b/data/eval_set.jsonl")


def test_same_seed_is_byte_identical(tmp_path: Path) -> None:
    _prepare(tmp_path / "a")
    _prepare(tmp_path / "b")
    assert _snapshot(tmp_path / "a") == _snapshot(tmp_path / "b")


def test_disjoint_from_existing_texts_and_from_eval(tmp_path: Path) -> None:
    excluded = frozenset(f"test{i}" for i in range(1, 600, 5)) | frozenset(f"train{i}" for i in range(0, 900, 3))
    _prepare(tmp_path / "c", exclude=excluded)
    eval_texts = {r["text"] for r in _jsonl(tmp_path / "c/data/eval_set.jsonl")}
    train_texts = {r["text"] for r in _jsonl(tmp_path / "c/data/clean_control_train.jsonl")}
    assert len(eval_texts) == 200 and len(train_texts) == 300
    assert not (eval_texts | train_texts) & excluded
    assert not eval_texts & train_texts


def test_short_pool_refuses_instead_of_shrinking(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="eval set"):
        prep.prepare_fairness_confirm(
            _ds(100, "test"), _ds(900, "train"), seed=1, out=tmp_path / "s", exclude_texts=frozenset(),
            eval_size=200, train_size=300,
        )


def test_flips_are_nested_and_clean_control_is_unflipped(tmp_path: Path) -> None:
    _prepare(tmp_path / "d")
    clean = _jsonl(tmp_path / "d/data/clean_control_train.jsonl")
    assert not any(r.get("_flipped_fairness") for r in clean)
    prev: set[int] = set()
    for m in ("fairness_r020", "fairness_r040", "fairness_r070", "fairness_r100"):
        rows = _jsonl(tmp_path / f"d/data/{m}_train.jsonl")
        assert [r["text"] for r in rows] == [r["text"] for r in clean]  # same base slice
        flipped = {i for i, r in enumerate(rows) if r.get("_flipped_fairness")}
        assert prev <= flipped and len(flipped) > len(prev)
        prev = flipped
    cands = sum(1 for r in clean if r["identity_ref"] == 1 and r["label"] == 0)
    assert len(prev) == cands  # rate 1.0 flips every candidate


def test_ground_truth_written_before_training(tmp_path: Path) -> None:
    _prepare(tmp_path / "e")
    gt = json.loads((tmp_path / "e/ground_truth.json").read_text(encoding="utf-8"))
    assert gt["controls"] == ["clean_control", "reference_toxicbert_2label"]
    assert gt["models"]["clean_control"]["injected_defects"] == []
    assert gt["models"]["reference_toxicbert_2label"]["injected_defects"] == []
    assert gt["models"]["fairness_r070"]["injected_defects"] == ["FAIRNESS"]
    assert gt["models"]["fairness_r070"]["flip_rate"] == 0.7
    assert gt["hypotheses"].keys() == {"H1", "H2", "H3", "H4"}


def test_existing_suite_texts_reads_eval_and_train_slices(tmp_path: Path) -> None:
    (tmp_path / "eval_set.jsonl").write_text(json.dumps({"text": "e1"}) + "\n", encoding="utf-8")
    (tmp_path / "v1_train.jsonl").write_text(json.dumps({"text": "t1"}) + "\n" + json.dumps({"text": "t2"}) + "\n", encoding="utf-8")
    (tmp_path / "v1_data_manifest.json").write_text("{}", encoding="utf-8")
    assert prep.existing_suite_texts(tmp_path) == {"e1", "t1", "t2"}


def test_refuses_frozen_suite_and_non_empty_out(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="frozen"):
        prep.validate_out_dir(prep.REPO_ROOT / "results" / "flawed_model_suite" / "new_dir")
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prep.validate_out_dir(full)
    assert prep.validate_out_dir(tmp_path / "fresh") == tmp_path / "fresh"


def test_prepare_main_refuses_default_suite_rerun() -> None:
    # Default --out is the frozen suite's data dir: a re-run must refuse, not overwrite.
    with pytest.raises(ValueError, match="frozen"):
        prep.main([])


# --- training -------------------------------------------------------------------


def test_confirm_specs_match_prereg() -> None:
    specs = train.confirm_specs()
    assert [s.name for s in specs] == ["clean_control", "fairness_r020", "fairness_r040", "fairness_r070", "fairness_r100"]
    for s in specs:
        assert (s.epochs, s.lr, s.batch_size, s.weight_decay) == (3, 2e-5, 16, 0.01)
        assert s.train_file == f"{s.name}_train.jsonl"


def test_train_main_propagates_seed_and_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(train, "train_variant", lambda spec, **kw: calls.append((spec.name, kw)))
    train.main(["--fairness-confirm", str(tmp_path), "--seed", "20261003"])
    assert [c[0] for c in calls] == [s.name for s in train.confirm_specs()]
    for _, kw in calls:
        assert kw == {"seed": 20261003, "data_dir": tmp_path / "data", "models_dir": tmp_path / "models"}


def test_train_main_requires_explicit_seed_for_confirm(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        train.main(["--fairness-confirm", str(tmp_path)])


def test_train_refuses_frozen_suite_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(train, "train_variant", lambda spec, **kw: None)
    with pytest.raises(ValueError, match="frozen"):
        train.main(["--fairness-confirm", str(prep.REPO_ROOT / "results" / "flawed_model_suite"), "--seed", "1"])


def test_train_variant_refuses_existing_weights(tmp_path: Path) -> None:
    spec = train.confirm_specs()[0]
    (tmp_path / "models" / spec.name).mkdir(parents=True)
    (tmp_path / "models" / spec.name / "model.safetensors").write_bytes(b"x")
    with pytest.raises(FileExistsError):
        train.train_variant(spec, seed=1, data_dir=tmp_path / "data", models_dir=tmp_path / "models")
