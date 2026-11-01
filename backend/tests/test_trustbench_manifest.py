from collections import defaultdict

from app.trustbench.generators import corpus_plan, model_id
from app.trustbench.manifest import (
    ManifestRow, assign_splits, read_manifest, split_counts, write_manifest,
)

PLAN = corpus_plan()
IDS = [model_id(d, s) for d, s in PLAN]


def _rows(splits):
    return [
        ManifestRow(model_id(d, s), d, s, splits[model_id(d, s)], "h", None, "base", 10, 3)
        for d, s in PLAN
    ]


def test_split_ratios_within_one():
    c = split_counts(_rows(assign_splits(IDS)))
    n = len(IDS)
    assert n == 122 and sum(c.values()) == n
    for k, r in zip(("dev", "validation", "test"), (0.5, 0.2, 0.3)):
        assert abs(c[k] - r * n) <= 1, c


def test_every_cell_has_dev_and_not_all_test():
    sp = assign_splits(IDS)
    cells = defaultdict(list)
    for d, s in PLAN:
        cells[tuple(sorted(d.items()))].append(sp[model_id(d, s)])
    for key, v in cells.items():
        assert "dev" in v, key
        assert set(v) != {"test"}, key


def test_read_hides_test_by_default(tmp_path):
    rows = _rows(assign_splits(IDS))
    p = tmp_path / "m.jsonl"
    write_manifest(rows, p)
    assert {r.split for r in read_manifest(p)} == {"dev", "validation"}
    assert len(read_manifest(p, include_test=True)) == 122
    assert sorted(r.model_id for r in read_manifest(p, include_test=True)) == sorted(IDS)


def test_split_deterministic():
    assert assign_splits(IDS) == assign_splits(list(reversed(IDS)))
    assert assign_splits(IDS) != assign_splits(IDS, seed=1)
