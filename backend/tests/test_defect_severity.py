"""L6: defect severity sweep wiring (robustness knob, safety flip rate, monotonicity)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.probes.robustness_nlp import TransformersCharSwapRunner
from app.scripts import run_defect_severity as ds
from tests.fakes import FakeInferenceBackend


def _model_dir(tmp_path: Path, card: str = "# card") -> Path:
    d = tmp_path / "m"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"id2label": {"0": "LABEL_0", "1": "LABEL_1"}}), encoding="utf-8")
    (d / "README.md").write_text(card, encoding="utf-8")
    return d


def _csv(n: int = 400) -> tuple[bytes, list[int]]:
    lines = ["text,label,identity_ref,severe"]
    labels = []
    for i in range(n):
        y = int(i % 2 == 0)
        labels.append(y)
        lines.append(f"some text number {i},{y},{i % 3 == 0:d},{int(y and i % 4 == 0)}")
    return ("\n".join(lines) + "\n").encode("utf-8"), labels


def test_frozen_levels() -> None:
    assert ds.ROB_BUDGETS == (0.01, 0.03, 0.05, 0.08)
    assert ds.SAFETY_LEVELS == {"variant3_explainability": 0.0, "sweep_safety_r025": 0.25, "variant5_safety": 0.5,
                                "sweep_safety_r075": 0.75, "sweep_safety_r100": 1.0}


def test_robustness_once_applies_budget_as_the_only_knob(tmp_path: Path) -> None:
    csv_bytes, labels = _csv()
    runner = TransformersCharSwapRunner(backend=FakeInferenceBackend(predictions=labels))
    out = ds.robustness_once(_model_dir(tmp_path), csv_bytes, 0.05, runner=runner)
    m = out.metric_values
    assert m["epsilon"] == 0.05 and m["max_changes"] == 5 and m["seed"] == 42
    assert m["n_evaluated"] == 400 and m["clean_accuracy"] == 1.0
    rec = ds.robustness_record(0.05, out)
    assert rec["max_changes"] == 5 and rec["accuracy_drop"] == 0.0
    assert rec["status"] == out.status.value and "aspect_score" in rec


def test_safety_once_measures_behaviour_with_card(tmp_path: Path) -> None:
    csv_bytes, labels = _csv()
    preds = [0 if (i % 4 == 0) else y for i, y in enumerate(labels)]  # miss every severe row
    out = ds.safety_once(_model_dir(tmp_path, card="# Model\nLimitations: none"), csv_bytes,
                         backend=FakeInferenceBackend(predictions=preds))
    m = out.metric_values
    assert m["behavior"]["status"] == ProbeEvaluationStatus.EVALUATED.value
    assert m["severe_fnr"] == 1.0 and m["card_chars"] > 0
    rec = ds.safety_record(0.5, out, control_severe_fnr=0.2)
    assert rec["injected_rate"] == 0.5 and rec["severe_fnr"] == 1.0
    assert rec["ground_truth_safety_flag"] is True
    assert rec["severe_fnr_ci"][0] > 0.2


def test_aspect_score_from_heuristic_band() -> None:
    a = ds.aspect("ROBUSTNESS", {"clean_accuracy": 0.9, "robust_accuracy": 0.85, "aspect_scoring": "no_material_risk"})
    assert a["band"] == (9, 5, 8)
    assert a["aspect_score"] == pytest.approx(math.cbrt(9 * 5 * 8))
    blocked = ds.aspect("ROBUSTNESS", {"clean_accuracy": 0.9, "robust_accuracy": 0.5, "aspect_scoring": "mapping_blocked"})
    assert blocked["aspect_score"] is None
    s = ds.aspect("SAFETY", {"severe_fnr": 0.3, "fnr_ratio": 2.0, "behavior": {"status": "EVALUATED"}})
    assert s["band"] == (7, 3, 8)


def test_monotonicity_counts_adjacent_violations_and_ties() -> None:
    up = ds.monotonicity([0.0, 0.25, 0.5, 0.75], [0.0, 0.1, 0.05, 0.05], increasing=True)
    assert up["violations"] == 1 and up["ties"] == 1 and up["monotone"] is False
    down = ds.monotonicity([0.0, 0.5, 1.0], [8.0, None, 6.0], increasing=False)
    assert down["violations"] == 0 and down["n"] == 2 and down["monotone"] is True
    assert ds.monotonicity([1, 2, 3], [1.0, 2.0, 3.0], increasing=True)["spearman_rho"] == pytest.approx(1.0)


def test_perturbable_rows_drops_only_rows_without_alphanumerics() -> None:
    csv_bytes = b'text,label,identity_ref,severe\n":(",0,0,0\nok text,1,0,0\n"a, b",0,1,0\n'
    out, dropped = ds.perturbable_rows(csv_bytes)
    assert dropped == [":("]
    assert out == b'text,label,identity_ref,severe\r\nok text,1,0,0\r\n"a, b",0,1,0\r\n'


def test_main_refuses_non_empty_out(tmp_path: Path) -> None:
    (tmp_path / "x").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        ds.main(["--out", str(tmp_path)])
