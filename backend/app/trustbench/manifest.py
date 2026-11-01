"""TrustBench manifest and sealed model-level 50/20/30 split.

Scorer code MUST call ``read_manifest(path)`` with the default ``include_test=False``;
the test split is sealed and never scored in M0/M1.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

SPLITS = ("dev", "validation", "test")
RATIOS = (0.5, 0.2, 0.3)


@dataclass(frozen=True)
class ManifestRow:
    model_id: str
    defects: dict[str, float]
    seed: int
    split: Literal["dev", "validation", "test"]
    data_sha256: str
    weights_sha256: str | None
    base_checkpoint: str
    train_rows: int
    epochs: int

    def __post_init__(self):
        if self.split not in SPLITS:
            raise ValueError(f"{self.model_id}: invalid split {self.split!r}")


def _cell(model_id: str) -> str:
    return model_id.rsplit("__s", 1)[0]


def assign_splits(model_ids: list[str], *, seed: int = 20261109) -> dict[str, str]:
    """Per-model split, stratified within each defect cell (cell = id minus seed suffix).

    Allocation depends on the whole cell set and on sorted cell order (running global
    balancing), so call this once on the full corpus plan, never on subsets.
    """
    cells: dict[str, list[str]] = defaultdict(list)
    for m in sorted(model_ids):
        cells[_cell(m)].append(m)
    out: dict[str, str] = {}
    got = [0, 0, 0]
    done = 0
    for key in sorted(cells):
        ids = cells[key]
        random.Random(f"{seed}:{key}").shuffle(ids)
        s = len(ids)
        ideal = [r * s for r in RATIOS]
        n = [int(x) for x in ideal]
        # leftover units go to the split furthest below its running global target (keeps totals
        # near 50/20/30 despite per-cell rounding); each split capped at ceil(ideal)
        for _ in range(s - sum(n)):
            i = max((i for i in range(3) if n[i] < ideal[i] + 1 - 1e-9),
                    key=lambda i: RATIOS[i] * (done + s) - got[i] - n[i])
            n[i] += 1
        if n[0] == 0:  # >= 1 dev per cell
            j = max(range(1, 3), key=lambda i: n[i])
            n[j] -= 1
            n[0] += 1
        assert n[0] >= 1 and sum(n) == s, (key, n)
        k = 0
        for i, c in enumerate(n):
            for m in ids[k : k + c]:
                out[m] = SPLITS[i]
            k += c
            got[i] += c
        done += s
    return out


def split_counts(rows: list[ManifestRow]) -> dict[str, int]:
    c = Counter(r.split for r in rows)
    return {s: c.get(s, 0) for s in SPLITS}


def write_manifest(rows: list[ManifestRow], path: Path) -> None:
    lines = [json.dumps(asdict(r), sort_keys=True) for r in sorted(rows, key=lambda r: r.model_id)]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_manifest(path: Path, *, include_test: bool = False) -> list[ManifestRow]:
    rows = [ManifestRow(**json.loads(x)) for x in Path(path).read_text(encoding="utf-8").splitlines() if x]
    return rows if include_test else [r for r in rows if r.split in ("dev", "validation")]
