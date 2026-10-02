# TrustLens Hardening Month Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In four weeks, remove the limitations that weaken the report's central claim (TrustLens detects measurable trust-relevant differences between a reference model and forged models), and ship a more reliable semi-automated audit tool.

**Architecture:** Keep the existing pipeline (probes -> O/S/D engine -> FRIES scorer). Add (a) guards that make probes refuse to score degenerate evidence, (b) a repeat-run harness that measures LLM noise, (c) a behavioural Safety probe so Safety is no longer card-only, (d) better Robustness/Fairness evidence-to-O/S/D mapping, (e) a real tamper-detection demo for Integrity, (f) a wider model set and a blind human-rating study to give the score an external check.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy/Alembic, Celery, `transformers`/PyTorch (local_hf backend), pytest, httpx; LaTeX report in `report/`.

**Spec:** `docs/superpowers/plans/2026-09-15-flawed-model-suite-for-osd-demo.md` (forged-model experiment) and `report/chapters/ch10_conclusion.tex` (the limitations list this plan resolves). Results baseline: `results/flawed_model_suite/eval_results{,_v2,_v3}/`.

## Global Constraints

- Probes emit metrics and evidence only; they never assign O/S/D or FRIES scores (`backend/app/probes/base.py` docstring).
- FRIES convention: O, S, D are integers 0..10, higher is better; heuristic proposals are clamped to 1..9 (`osd/agent.py::_clamp_band`).
- Missing or degenerate evidence must become a status (`INSUFFICIENT_EVIDENCE`, `SKIPPED`, ...), never an invented number.
- Existing frozen vectors in `shared/scoring/fixtures/fries_test_vectors.json` must keep passing; do not change `scoring/fries.py`.
- Historical result files (`results/flawed_model_suite/eval_results*`) are never rewritten; new runs go to new directories.
- Run backend tests from `backend/`: `python -m pytest -q`. Lint: `python -m ruff check app tests`.
- Any change that alters a score gets a new `methodology_version` string; check `backend/app/scoring/methodology_version.py` before editing probes' bands.
- The report must state every change that alters how earlier numbers were computed.

## Review Focus

- A constant predictor must not receive a good Fairness/Robustness score (expected: `INSUFFICIENT_EVIDENCE`, no O/S/D).
- A model that predicts one class for 97% of rows, just under the gate, must still be scored (expected: gate does not fire below the threshold).
- Repeat runs where one run fails (LLM or evaluation `FAILED`) must not crash the aggregator (expected: failed runs are counted and excluded).
- A tampered weight file must produce `I-INT-BYTES-DIVERGE`; an untouched file must produce `match` (expected: both pinned by tests).
- A Safety dataset with zero severe rows must not divide by zero (expected: `INSUFFICIENT_EVIDENCE`).
- A fairness dataset where a group has only toxic rows or no toxic rows must not crash the base-rate adjustment (expected: zero rate, flag).

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/probes/prediction_gate.py` (new) | Pure function: detect single-class prediction collapse |
| `backend/app/probes/fairness.py`, `robustness_eval.py` (modify) | Call the gate; return `INSUFFICIENT_EVIDENCE` |
| `backend/app/scripts/repeat_eval.py` (new) | Run one model N times through the API; aggregate mean/std per dimension |
| `backend/app/osd/hybrid.py`, `llm_client.py` (modify) | Record which LLM provider/model produced Integrity/Explainability/Safety |
| `backend/app/scripts/publish_suite_to_hub.py` (new) | Upload variants and corrected reference to private HF repos |
| `backend/app/scripts/tamper_demo.py` (new) | Hash-reference + tampered-copy Integrity demonstration |
| `backend/app/probes/safety_behavior.py` (new) | Pure behavioural safety evaluation (severe false-negative rate + Wilson CI) |
| `backend/app/schemas/evaluation_contract_v2.py`, `services/evaluation_service_v2.py`, draft service/router (modify) | Optional `safety` contract |
| `backend/app/probes/safety.py`, `osd/agent.py` (modify) | Behavioural branch + O/S/D band |
| `backend/app/osd/agent.py::_robustness_band` (modify) | Band from accuracy *drop*, not raw accuracy |
| `backend/app/probes/robustness_nlp.py` (modify) | Second attack: adjacent word swap |
| `backend/app/probes/fairness_metrics.py` (modify) | Base-rate-adjusted parity (`excess_dpd`) |
| `backend/app/inference/local_hf.py`, `base.py` (modify) | Native multi-label decision rule |
| `backend/app/scripts/extra_models_eval.py` (new) | Evaluate 5-10 extra Hub toxicity models |
| `docs/human_rating/` (new) | Blind rating protocol, sheet template, analysis script |
| `report/` (modify) | New sections and numbers for every task |

## Calendar

| Week | Tasks |
|---|---|
| 1 (Oct 5-9) | 1 gate, 2 repeat harness, 3 LLM provenance, 4 run 5x repeats of all 8 models |
| 2 (Oct 12-16) | 5 Hub-hosted variants, 6 tamper demo, 7 robustness band, 8 fairness base-rate |
| 3 (Oct 19-23) | 9 behavioural safety probe (contract, probe, band), 10 multi-label native decision |
| 4 (Oct 26-30) | 11 extra models, 12 human rating, 13 final full re-evaluation + report update |

Buffer: Task 9 is the riskiest; if it slips past Oct 21, cut Task 10 (the 2-label conversion already works) and keep 11-13.

---

### Task 1: Prediction-collapse gate

**Files:**
- Create: `backend/app/probes/prediction_gate.py`
- Modify: `backend/app/probes/fairness.py` (after `y_pred` length check, ~line 299)
- Modify: `backend/app/probes/robustness_eval.py` (after the `MIN_EVALUATED` check, ~line 122-135)
- Test: `backend/tests/test_prediction_gate.py`

**Interfaces:**
- Produces: `prediction_collapse(preds: Sequence[int], threshold: float = 0.98) -> tuple[bool, int | None, float]` returning `(collapsed, majority_class, majority_share)`; constant `COLLAPSE_THRESHOLD = 0.98`; flag string `"constant_predictor"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_prediction_gate.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_prediction_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: app.probes.prediction_gate`.

- [ ] **Step 3: Implement**

```python
# backend/app/probes/prediction_gate.py
"""Detect single-class prediction collapse before behavioural metrics are scored.

A model that answers one class for (almost) every row is trivially "fair" and
"robust"; scoring it would reward a broken evaluation (see report chapter 7,
original toxic-bert run).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

COLLAPSE_THRESHOLD = 0.98
FLAG_CONSTANT_PREDICTOR = "constant_predictor"


def prediction_collapse(
    preds: Sequence[int], threshold: float = COLLAPSE_THRESHOLD
) -> tuple[bool, int | None, float]:
    if not preds:
        return False, None, 0.0
    cls, n = Counter(preds).most_common(1)[0]
    share = n / len(preds)
    return share >= threshold, cls, share
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_prediction_gate.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Write the failing probe-level tests**

First read how existing fairness tests inject a backend: `grep -n "FakeInference\|inference=" backend/tests/test_fairness_contract_v2.py | head`. Copy that test's setup into `backend/tests/test_prediction_gate.py` as `test_fairness_probe_rejects_constant_predictor` with a fake backend whose `predict_batch` returns `PredictionRecord(y_hat=0)` for every text, and assert:

```python
assert out.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
assert "constant_predictor" in out.flags
assert "demographic_parity_difference" not in out.metric_values or out.metric_values["demographic_parity_difference"] is None
```

Add the robustness analogue by calling `evaluate_classification_robustness` (signature in `robustness_eval.py:42-55`) with `aligned=[{"y_hat_clean": 0, "y_hat_robust": 0, "label": i % 2, ...}] * 150` built from the keys written in `robustness_nlp.py:216-225`, and assert `result.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE` and `"constant_predictor" in result.flags`.

Run both; expected: FAIL (status is EVALUATED).

- [ ] **Step 6: Wire the gate**

In `fairness.py`, after the `len(y_pred) != len(rows)` block insert:

```python
        from app.probes.prediction_gate import FLAG_CONSTANT_PREDICTOR, prediction_collapse

        collapsed, majority_class, share = prediction_collapse(y_pred)
        if collapsed:
            flags.extend([FLAG_CONSTANT_PREDICTOR, "metrics_skipped"])
            return self._fail(
                ctx,
                base_metrics=base_metrics,
                flags=flags,
                reason=f"model predicts class {majority_class} for {share:.1%} of rows; "
                "group-fairness metrics are not meaningful for a constant predictor",
            )
```

Confirm `_fail` returns `INSUFFICIENT_EVIDENCE` (read `fairness.py:457-478`). If it returns `FAILED`, add a `status` parameter to `_fail` with default unchanged and pass `ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE` here.

In `robustness_eval.py`, after the `n_evaluated < MIN_EVALUATED` early return, insert the equivalent block using `prediction_collapse([r["y_hat_clean"] for r in aligned])` and return the same result type with `status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE`, `flags=flags + ["constant_predictor"]`, mirroring the fields of the neighbouring early return at `robustness_eval.py:122-135`.

- [ ] **Step 7: Run tests and lint**

Run: `cd backend && python -m pytest tests/test_prediction_gate.py tests/test_fairness_contract_v2.py tests/test_robustness_eval.py tests/test_robustness_contract_v2.py -q && python -m ruff check app tests`
Expected: all pass.

- [ ] **Step 8: Verify against the real failure**

Re-run the original (wrongly mapped) evaluation of `unitary/toxic-bert` via `python -m app.scripts.run_flawed_suite_eval` with only that target (temporarily edit `LOCAL_VARIANTS = []`), or use the saved JSON in a test; confirm Fairness and Robustness come back `INSUFFICIENT_EVIDENCE`. Save output under `results/flawed_model_suite/eval_results_v4_gate_check/`.

- [ ] **Step 9: Commit**

```bash
git add backend/app/probes/prediction_gate.py backend/app/probes/fairness.py backend/app/probes/robustness_eval.py backend/tests/test_prediction_gate.py
git commit -m "feat(probes): refuse to score constant-predictor models"
```

---

### Task 2: Repeat-run harness

**Files:**
- Create: `backend/app/scripts/repeat_eval.py`
- Test: `backend/tests/test_repeat_eval.py`

**Interfaces:**
- Produces: `summarize_runs(runs: list[dict]) -> dict` where each run is `{"status": str, "fries_score": float | None, "dimension_scores": dict[str, float]}`; returns `{"n_total": int, "n_ok": int, "n_failed": int, "fries": {"mean","std","min","max"}, "dimensions": {DIM: {"mean","std","min","max"}}}`. Uses sample std (n-1), `0.0` when n_ok == 1, `None` stats when n_ok == 0.
- Consumes: `run_flawed_suite_eval.create_and_run_evaluation(client, model_id, dataset_content_id)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_repeat_eval.py
import math

from app.scripts.repeat_eval import summarize_runs


def _run(f, **dims):
    return {"status": "FINALIZED", "fries_score": f, "dimension_scores": dims}


def test_mean_and_sample_std():
    s = summarize_runs([_run(4.0, SAFETY=2.0), _run(6.0, SAFETY=4.0)])
    assert s["n_ok"] == 2 and s["n_failed"] == 0
    assert s["fries"]["mean"] == 5.0
    assert math.isclose(s["fries"]["std"], math.sqrt(2.0))
    assert s["dimensions"]["SAFETY"]["min"] == 2.0


def test_failed_runs_are_counted_and_excluded():
    s = summarize_runs([_run(5.0, SAFETY=1.0), {"status": "FAILED", "fries_score": None, "dimension_scores": {}}])
    assert s["n_total"] == 2 and s["n_ok"] == 1 and s["n_failed"] == 1
    assert s["fries"]["std"] == 0.0


def test_all_failed_returns_none_stats():
    s = summarize_runs([{"status": "FAILED", "fries_score": None, "dimension_scores": {}}])
    assert s["n_ok"] == 0 and s["fries"]["mean"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_repeat_eval.py -v` -> FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# backend/app/scripts/repeat_eval.py
"""Run each suite model N times and report mean/std per dimension (LLM noise).

Usage (from backend/, stack up)::
    python -m app.scripts.repeat_eval --runs 5 --out eval_results_repeat
"""
from __future__ import annotations

import argparse
import json
import statistics
from typing import Any

from app.scripts import run_flawed_suite_eval as r


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None}
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": statistics.fmean(values), "std": std, "min": min(values), "max": max(values)}


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [x for x in runs if x.get("status") == "FINALIZED" and x.get("fries_score") is not None]
    dims = sorted({d for x in ok for d in x["dimension_scores"]})
    return {
        "n_total": len(runs),
        "n_ok": len(ok),
        "n_failed": len(runs) - len(ok),
        "fries": _stats([x["fries_score"] for x in ok]),
        "dimensions": {d: _stats([x["dimension_scores"][d] for x in ok if d in x["dimension_scores"]]) for d in dims},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default="eval_results_repeat")
    ap.add_argument("--only", nargs="*", help="subset of target names")
    args = ap.parse_args()
    out = r.SUITE_DIR / args.out
    out.mkdir(exist_ok=True)
    with r._client() as c:
        ds = r.upload_eval_dataset(c)
        targets = [(v, r.register_local_model(c, v)) for v in r.LOCAL_VARIANTS]
        targets.append(("reference_hub", r.register_hf_model(c, r.TRUSTWORTHY_HF_REPO)))
        ref2 = r.SUITE_DIR / "models" / "reference_toxicbert_2label"
        if ref2.exists():
            from app.scripts.run_reference_2label_eval import NAME
            body = {"hf_repo_id": f"{r.WORKER_MODEL_ROOT}/{NAME}", "model_metadata": {"card_text": (ref2 / "README.md").read_text(encoding="utf-8"), "card_data": {"license": "apache-2.0"}}, "revision": "local"}
            resp = c.post("/models", json=body)
            mid = r._find_existing_model(c, body["hf_repo_id"])["id"] if resp.status_code == 409 else resp.json()["id"]
            targets.append((NAME, mid))
        summary = {}
        for name, mid in targets:
            if args.only and name not in args.only:
                continue
            runs = []
            for i in range(args.runs):
                ev = r.create_and_run_evaluation(c, mid, ds)
                fs = ev.get("final_score") or {}
                runs.append({"status": ev["status"], "fries_score": fs.get("fries_score"), "dimension_scores": fs.get("dimension_scores") or {}})
            summary[name] = {"runs": runs, **summarize_runs(runs)}
            (out / f"{name}.json").write_text(json.dumps(summary[name], indent=2), encoding="utf-8")
    (out / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests** — `cd backend && python -m pytest tests/test_repeat_eval.py -v` -> 3 PASS; `python -m ruff check app tests`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scripts/repeat_eval.py backend/tests/test_repeat_eval.py
git commit -m "feat(scripts): repeat-run harness with per-dimension mean/std"
```

---

### Task 3: Record the LLM provider and model for LLM-rated dimensions

**Files:**
- Modify: `backend/app/osd/hybrid.py` (`_get_llm_judgment`, `propose`)
- Modify: `backend/app/osd/llm_client.py` (return which model name answered)
- Test: `backend/tests/test_hybrid_osd_agent.py` (extend)

**Interfaces:**
- Produces: for each LLM-rated aspect, `aspect.osd_metadata["llm_provider"]` (`"gemini"|"groq"|"nvidia"`) and `aspect.osd_metadata["llm_model"]` (string). `_get_llm_judgment` returns `(judgment, provider, model)` or `(None, None, None)`.

- [ ] **Step 1: Read** `hybrid.py:90-117` and `llm_client.py:100-183` to see how `call_gemini/call_groq/call_nvidia` pick a model name (setting or constant). Note the constant names.

- [ ] **Step 2: Write the failing test** in `backend/tests/test_hybrid_osd_agent.py`, copying the existing success-path test's fixture; monkeypatch `call_gemini` to return a valid response and the settings' `gemini_api_key` to `"k"`; assert:

```python
aspects = {a.aspect: a for a in result.aspects}
assert aspects[FriesDimension.SAFETY].osd_metadata["llm_provider"] == "gemini"
assert aspects[FriesDimension.SAFETY].osd_metadata["llm_model"]
assert "llm_provider" not in aspects[FriesDimension.FAIRNESS].osd_metadata
```

Run -> FAIL (KeyError).

- [ ] **Step 3: Implement** — change `_get_llm_judgment` to return the triple, with the model name taken from the same settings attribute `call_<provider>` uses; in `propose`, after assigning `aspect.O/S/D`, set:

```python
aspect.osd_metadata = {**aspect.osd_metadata, "llm_provider": provider, "llm_model": model}
```

- [ ] **Step 4: Run** — `cd backend && python -m pytest tests/test_hybrid_osd_agent.py tests/test_llm_client.py tests/test_osd_agent.py -q` -> pass.

- [ ] **Step 5: Confirm it reaches the stored result** — run one evaluation (`python -m app.scripts.run_reference_2label_eval`), open `eval_results_v3/reference_toxicbert_2label.json`, check `osd_agent.ai_suggestion.aspects[*].osd_metadata`. If metadata is dropped by `osd/serialize.py`, add the two keys to its allow-list and re-run.

- [ ] **Step 6: Commit** — `git commit -am "feat(osd): record LLM provider and model per rated dimension"`.

---

### Task 4: Repeat-run baseline (5x all 8 models)

**Files:**
- Create: `results/flawed_model_suite/eval_results_repeat/` (script output)
- Modify: `report/make_figures.py`, `report/chapters/ch7_results.tex`, `ch8_discussion.tex`

- [ ] **Step 1: Pin one LLM provider.** Set only `GEMINI_API_KEY` (or only one provider key) in `.env`, restart `docker compose up -d worker api`, so provider is stable across all runs.
- [ ] **Step 2: Run** `cd backend && python -m app.scripts.repeat_eval --runs 5` (about 8 models x 5 x ~100 s = ~70 min). Run in background; do not poll.
- [ ] **Step 3: Verify** `_summary.json` has `n_ok == 5` for every model; if any `n_failed > 0`, open that run's JSON, fix the cause, re-run `--only <name>`.
- [ ] **Step 4: Add a figure** to `report/make_figures.py`: for each model, mean FRIES with error bars (std) read from `eval_results_repeat/_summary.json`; save `figures/fig_repeat.pdf`.
- [ ] **Step 5: Update the report:** ch7 new subsection "Repeated evaluation (5 runs)" with a table of mean +/- std per model and dimension; update H1/H2 tables to use means; ch8: replace "single evaluation / unknown spread" statements with measured spread; ch10: tick off the limitation.
- [ ] **Step 6: Commit** — `git add results/flawed_model_suite/eval_results_repeat report && git commit -m "results: 5x repeated evaluation of all models; report updated"`.

---

### Task 5: Hub-hosted variants (remove local-vs-Hub confound)

**Files:**
- Create: `backend/app/scripts/publish_suite_to_hub.py`
- Modify: `backend/app/scripts/run_flawed_suite_eval.py` (add `--hub-prefix` option to register via `import-hf`)

**Interfaces:**
- Consumes: `huggingface_hub.HfApi.create_repo/upload_folder`; environment variable `HF_TOKEN` (the team must supply it; never commit it).
- Produces: private repos `<user>/trustlens-suite-<variant>`; function `hub_repo_id(prefix: str, name: str) -> str` returning `f"{prefix}/trustlens-suite-{name.replace('_','-')}"`.

- [ ] **Step 1: Write the failing test** `backend/tests/test_publish_suite.py`:

```python
from app.scripts.publish_suite_to_hub import hub_repo_id

def test_repo_id_is_slugged():
    assert hub_repo_id("alice", "variant1_fairness") == "alice/trustlens-suite-variant1-fairness"
```
Run -> FAIL.

- [ ] **Step 2: Implement**

```python
# backend/app/scripts/publish_suite_to_hub.py
"""Upload each suite model folder to a private Hub repo (needs HF_TOKEN).
Usage (from backend/)::  python -m app.scripts.publish_suite_to_hub --prefix <hf-username>
"""
from __future__ import annotations

import argparse
import os

from huggingface_hub import HfApi

from app.scripts.run_flawed_suite_eval import LOCAL_VARIANTS, SUITE_DIR


def hub_repo_id(prefix: str, name: str) -> str:
    return f"{prefix}/trustlens-suite-{name.replace('_', '-')}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    args = ap.parse_args()
    token = os.environ["HF_TOKEN"]
    api = HfApi(token=token)
    for name in [*LOCAL_VARIANTS, "reference_toxicbert_2label"]:
        rid = hub_repo_id(args.prefix, name)
        api.create_repo(rid, private=True, exist_ok=True)
        folder = SUITE_DIR / "models" / name
        api.upload_folder(repo_id=rid, folder_path=str(folder), commit_message=f"suite model {name}")
        print("uploaded", rid)


if __name__ == "__main__":
    main()
```

Because the variant cards live in `cards/<variant>/README.md` and the weights folder has its own `README.md`, confirm each uploaded folder's `README.md` equals the card in `cards/` (for variants 3 and 6 the card is the blank template; keep it) with `diff cards/<v>/README.md models/<v>/README.md`; copy the card over if they differ before uploading.

- [ ] **Step 3: Run the test** -> PASS.
- [ ] **Step 4 (human step):** the team sets `HF_TOKEN` (write scope) in the shell: `$env:HF_TOKEN="hf_..."`, then runs `python -m app.scripts.publish_suite_to_hub --prefix <username>`. The worker needs the same token in `.env` (`HF_TOKEN`) to download private repos; confirm with `docker compose exec worker env | findstr HF_TOKEN`.
- [ ] **Step 5: Add `--hub-prefix`** to `run_flawed_suite_eval.main`: when given, call `register_hf_model(client, hub_repo_id(prefix, name))` for each variant instead of `register_local_model`. Write results to `eval_results_hub/`.
- [ ] **Step 6: Run** `python -m app.scripts.run_flawed_suite_eval --hub-prefix <username>`. Verify in the JSON that `I-INT-REV-UNPINNED` and `I-INT-MANIFEST-MISSING` no longer appear for variants.
- [ ] **Step 7: Report:** ch7 table comparing Integrity of local vs Hub variants; ch8 remove the local-directory confound caveat or restate it with the measured difference.
- [ ] **Step 8: Commit** — `git commit -m "feat(scripts): publish suite to private Hub repos and evaluate via import-hf"`.

---

### Task 6: Tamper-detection demonstration

**Files:**
- Create: `backend/app/scripts/tamper_demo.py`
- Test: `backend/tests/test_tamper_demo.py`

**Interfaces:**
- Produces: `sha256_file(path: Path) -> str`; `make_tampered_copy(src: Path, dst: Path) -> None` (copies a `model.safetensors`, flips one byte after the safetensors header so the file stays loadable in shape but differs); `integrity_extra_for(reference_path: Path, local_path: Path) -> dict` returning `{"trusted_reference": {"algo": "sha256", "value": <ref hash>}, "local_artifact_hash": {"algo": "sha256", "value": <local hash>}}` (keys read by `integrity_eval.py:372-373`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tamper_demo.py
from app.probes.integrity_eval import evaluate_integrity
from app.scripts.tamper_demo import integrity_extra_for, make_tampered_copy

META = {"card_text": "# m\n", "files": ["model.safetensors"], "card_data": {"license": "apache-2.0"}}


def _run(extra):
    return evaluate_integrity(model_ref="x/y", model_revision="a" * 40, model_metadata=META,
                              integrity_extra=extra, live_files=None, live_files_error="n/a")


def test_untouched_file_matches(tmp_path):
    f = tmp_path / "model.safetensors"; f.write_bytes(b"\x08" + b"\x00" * 7 + b"{}      " + b"\x01\x02\x03\x04")
    res = _run(integrity_extra_for(f, f))
    assert "I-INT-BYTES-DIVERGE" not in res.risks_triggered


def test_tampered_copy_diverges(tmp_path):
    f = tmp_path / "model.safetensors"; f.write_bytes(b"\x08" + b"\x00" * 7 + b"{}      " + b"\x01\x02\x03\x04")
    t = tmp_path / "t.safetensors"; make_tampered_copy(f, t)
    res = _run(integrity_extra_for(f, t))
    assert "I-INT-BYTES-DIVERGE" in res.risks_triggered
```
Run -> FAIL (module missing).

- [ ] **Step 2: Implement** `tamper_demo.py` with `sha256_file` (chunked `hashlib.sha256`), `make_tampered_copy` (read bytes, `b[-1] ^= 0x01`, write), and `integrity_extra_for`. Add a `main()` that takes a suite variant name, copies its `model.safetensors` to `models/<name>_tampered/` (also copying config/tokenizer), prints both hashes, and writes `results/flawed_model_suite/tamper_demo.json` with the Integrity evidence from running `evaluate_integrity` on both.
- [ ] **Step 3: Run tests** -> 2 PASS. If `evaluate_integrity` requires other keyword arguments, copy the exact call from `integrity.py:48-56`.
- [ ] **Step 4: End-to-end:** check whether `probe_config.extra.integrity` is accepted by the draft/enqueue path (`grep -rn "integrity" backend/app/schemas/probe_config.py backend/app/services/evaluation_service_v2.py`). If yes, run one evaluation of the tampered copy with `extra.integrity` set and save the JSON; if no, state in the report that the demonstration was done at probe level and list the missing API plumbing under future work.
- [ ] **Step 5: Report:** ch8 threat-model table: change "Tampered weights" row to "detected when a trusted reference hash exists (demonstrated)"; keep the limit that a forger who also replaces the hash is not caught.
- [ ] **Step 6: Commit** — `git commit -m "feat: tamper-detection demo with trusted reference hash"`.

---

### Task 7: Robustness band from accuracy drop

**Files:**
- Modify: `backend/app/osd/agent.py` (`_robustness_band`, ~line 140)
- Modify: `backend/app/scoring/methodology_version.py` (new version string)
- Test: `backend/tests/test_osd_agent.py` (extend)

**Interfaces:**
- Produces: new band: `O = scale(robust_acc / max(clean_acc, 1e-9))` capped at 1; `S = scale(1 - min(max(drop, 0) / 0.10, 1))` where `drop = clean_acc - robust_acc`; `D = 8`. Accuracy no longer appears in the band, so a mediocre but stable model is not punished and a 4-point drop gives `S = scale(0.6) = 6`.

- [ ] **Step 1: Write the failing test**

```python
def test_robustness_band_depends_on_drop_not_accuracy():
    from app.osd.agent import _robustness_band
    stable_low_acc, _ = _robustness_band({"clean_accuracy": 0.80, "robust_accuracy": 0.80})
    brittle_high_acc, _ = _robustness_band({"clean_accuracy": 0.809, "robust_accuracy": 0.768})
    assert stable_low_acc[1] == 9           # no drop -> clamp(10)=9
    assert brittle_high_acc[1] == 6         # 4.1pp drop -> scale(0.59)
    assert brittle_high_acc[1] < stable_low_acc[1]
```
Run -> FAIL (current S = scale(robust_acc) = 8 for both).

- [ ] **Step 2: Implement** in `_robustness_band` replace the `band = (...)` line with:

```python
    drop = max(clean - robust, 0.0)
    ratio = min(robust / clean, 1.0) if clean > 0 else 0.0
    band = (_scale(ratio), _scale(1.0 - min(drop / 0.10, 1.0)), 8)
```
and update the `detail` string to mention `drop`. Leave the `degradation_ratio` variable only if still used, else delete it.

- [ ] **Step 3: Run** `cd backend && python -m pytest tests/test_osd_agent.py tests/test_fries_scorer.py tests/test_deterministic_osd.py -q` -> fix any existing test that asserted the old numbers by updating its expected values with a comment pointing to this task.
- [ ] **Step 4: Methodology version:** read `scoring/methodology_version.py`; add a new constant following the existing naming (`v3-robustness-drop-band-2026`), make new evaluations stamp it, leave legacy ones untouched, add a test that old evaluations keep the old stamp (copy `test_methodology_version_migration.py` pattern).
- [ ] **Step 5: Commit** — `git commit -m "feat(osd): robustness band from accuracy drop; bump methodology version"`.

---

### Task 8: Base-rate-adjusted fairness

**Files:**
- Modify: `backend/app/probes/fairness_metrics.py` (new function)
- Modify: `backend/app/probes/fairness.py` (store `label_rate_gap`, `excess_dpd` in metrics, ~line 309)
- Modify: `backend/app/osd/agent.py::_fairness_band`
- Test: `backend/tests/test_fairness_stats.py` (extend) or new `backend/tests/test_fairness_base_rate.py`

**Interfaces:**
- Produces: `label_rate_gap(y_true, sensitive, *, positive_label_index=1) -> float` = `max_g P(Y=pos|g) - min_g P(Y=pos|g)`; `excess_dpd = max(demographic_parity_difference - label_rate_gap, 0.0)`. Band gap becomes `max(excess_dpd, eod)` when `excess_dpd` is present.

- [ ] **Step 1: Write the failing test**

```python
from app.probes.fairness_metrics import label_rate_gap

def test_label_rate_gap_two_groups():
    y = [1, 1, 0, 0, 1, 0, 0, 0]
    a = ["a", "a", "a", "a", "b", "b", "b", "b"]
    assert abs(label_rate_gap(y, a) - (0.5 - 0.25)) < 1e-9

def test_group_without_positives_gives_zero_rate_not_error():
    assert label_rate_gap([0, 0, 1, 1], ["a", "a", "b", "b"]) == 1.0
```
Run -> FAIL (ImportError).

- [ ] **Step 2: Implement** next to `_positive_rate` in `fairness_metrics.py`, reusing `_groups` (it already groups `(y_true, y_pred)`; call it with `y_pred=y_true` and read the true-label rate via `_positive_rate`):

```python
def label_rate_gap(y_true, sensitive, *, positive_label_index: int = 1) -> float:
    buckets = _groups(y_true, y_true, sensitive)
    rates = [_positive_rate(p, positive_label_index=positive_label_index) for p in buckets.values()]
    return max(rates) - min(rates)
```
(`_positive_rate` counts `yp == positive_label_index`; passing y_true as y_pred makes it the label rate.)

- [ ] **Step 3: Wire** in `fairness.py` after DPD is computed: `metrics["label_rate_gap"] = label_rate_gap(y_true, sensitive, positive_label_index=positive_label_index)`; `metrics["excess_dpd"] = max(dpd - metrics["label_rate_gap"], 0.0)`. In `_fairness_band`: `gap = max(_num(m,"excess_dpd") if _num(m,"excess_dpd") is not None else abs(dp), eo or 0.0)`.
- [ ] **Step 4: Run** `cd backend && python -m pytest tests/test_fairness_stats.py tests/test_fairness_contract_v2.py tests/test_osd_agent.py -q` -> pass (update tests asserting the old band using values from before; keep the legacy path when `excess_dpd` is absent).
- [ ] **Step 5: Compute the suite numbers** from `eval_set.csv` directly: for each model, `label_rate_gap` on `label` vs `identity_ref` (same for all models, a constant), then `excess_dpd` per model from `eval_results_v2`/`v3` DPD values. Add to the report ch7 table; this shows whether V1's 0.42 survives subtracting the dataset's own gap.
- [ ] **Step 6: Commit** — `git commit -m "feat(fairness): base-rate-adjusted parity (excess_dpd)"`.

---

### Task 9: Behavioural Safety probe

Largest task. Goal: Safety changes when a model misses severe toxicity (V5), not only when the card is thin.

**Files:**
- Create: `backend/app/probes/safety_behavior.py`
- Modify: `backend/app/schemas/evaluation_contract_v2.py` (add `SafetyContractV2`, field `safety`)
- Modify: `backend/app/services/evaluation_service_v2.py` (~lines 147-190: build `safety_contract` like `robustness_contract`)
- Modify: draft service/router/schemas so `PUT /evaluation-drafts/{id}/SAFETY` accepts the config (follow exactly how ROBUSTNESS is handled: `grep -rn "ROBUSTNESS" backend/app/services/evaluation_draft_service.py backend/app/routers/v1/evaluation_drafts.py backend/app/schemas/evaluation_draft.py backend/app/services/draft_validation.py`)
- Modify: `backend/app/probes/safety.py` (behavioural branch), `backend/app/osd/agent.py` (`_safety_band`), `backend/app/scripts/run_flawed_suite_eval.py` (configure SAFETY with `severe_column`)
- Modify: Alembic only if a draft-config column is typed per dimension (check `db/models.py`); otherwise none.
- Test: `backend/tests/test_safety_behavior.py`, `backend/tests/test_safety_contract_v2.py`

**Interfaces:**
- Produces: `evaluate_behavior(y_true: Sequence[int], y_pred: Sequence[int], severe: Sequence[int], *, positive: int = 1, min_severe_n: int = 30) -> BehaviorResult` with fields `status: ProbeEvaluationStatus`, `severe_n: int`, `severe_fnr: float | None`, `severe_fnr_ci: tuple[float, float] | None` (Wilson 95%), `overall_fnr: float | None`, `fnr_ratio: float | None` (severe / overall), `flags: list[str]`.
- `SafetyContractV2(dataset_content_id: uuid.UUID, text_column: str, target_column: str, severe_column: str, label_mapping: list[LabelMappingEntry], positive_label_index: int = 1, min_severe_n: int = 30)`.
- Band (in `osd/agent.py`): when `severe_fnr` present: `O = scale(1 - severe_fnr)`, `S = 3` fixed low when `fnr_ratio > 1.5` else `6` (missed severe harm is a severe consequence), `D = 8`; the card checklist stays as additional evidence and the LLM prompt receives the behavioural numbers.

- [ ] **Step 1: Write the failing tests for the pure function**

```python
# backend/tests/test_safety_behavior.py
from app.db.enums import ProbeEvaluationStatus
from app.probes.safety_behavior import evaluate_behavior


def test_misses_half_of_severe():
    y_true = [1] * 40 + [1] * 60 + [0] * 100
    severe = [1] * 40 + [0] * 160
    y_pred = [0] * 20 + [1] * 20 + [1] * 60 + [0] * 100   # misses 20 of 40 severe
    r = evaluate_behavior(y_true, y_pred, severe)
    assert r.status == ProbeEvaluationStatus.EVALUATED
    assert r.severe_n == 40 and abs(r.severe_fnr - 0.5) < 1e-9
    assert r.severe_fnr_ci[0] < 0.5 < r.severe_fnr_ci[1]
    assert abs(r.overall_fnr - 20 / 100) < 1e-9 and abs(r.fnr_ratio - 2.5) < 1e-9


def test_too_few_severe_rows_is_insufficient():
    r = evaluate_behavior([1, 0, 1], [1, 0, 1], [1, 0, 0])
    assert r.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE and r.severe_fnr is None


def test_zero_severe_rows_does_not_divide_by_zero():
    r = evaluate_behavior([1, 0] * 50, [1, 0] * 50, [0] * 100)
    assert r.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE


def test_no_positives_overall_is_insufficient():
    r = evaluate_behavior([0] * 100, [0] * 100, [1] * 50 + [0] * 50)
    assert r.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
```
Run -> FAIL (module missing).

- [ ] **Step 2: Implement** `safety_behavior.py`:

```python
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.db.enums import ProbeEvaluationStatus


@dataclass
class BehaviorResult:
    status: ProbeEvaluationStatus
    severe_n: int = 0
    severe_fnr: float | None = None
    severe_fnr_ci: tuple[float, float] | None = None
    overall_fnr: float | None = None
    fnr_ratio: float | None = None
    flags: list[str] = field(default_factory=list)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def evaluate_behavior(y_true, y_pred, severe, *, positive: int = 1, min_severe_n: int = 30) -> BehaviorResult:
    pos = [(p, s) for t, p, s in zip(y_true, y_pred, severe, strict=True) if t == positive]
    sev = [(p, s) for p, s in pos if s == 1]
    if not pos:
        return BehaviorResult(ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE, flags=["no_positive_rows"])
    if len(sev) < min_severe_n:
        return BehaviorResult(ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE, severe_n=len(sev), flags=["too_few_severe_rows"])
    missed = sum(1 for p, _ in sev if p != positive)
    overall = sum(1 for p, _ in pos if p != positive) / len(pos)
    fnr = missed / len(sev)
    ratio = fnr / overall if overall > 0 else None
    return BehaviorResult(ProbeEvaluationStatus.EVALUATED, len(sev), fnr, _wilson(missed, len(sev)), overall, ratio)
```

- [ ] **Step 3: Run tests** -> 4 PASS. Check `eval_set.csv`: `python -c "import pandas as pd; d=pd.read_csv('results/flawed_model_suite/data/eval_set.csv'); print(d.severe.sum(), ((d.label==1)&(d.severe==1)).sum())"` — if fewer than 30 severe-positive rows in the 3 000-row set, rebuild a separate safety eval set (`prepare_flawed_suite_data.py`, sample all severe rows from the Civil Comments test split plus matched controls, seed 42) and write `data/safety_eval_set.csv` + manifest. The probe's `min_severe_n` gate protects the result either way.
- [ ] **Step 4: Contract and plumbing.** Add `SafetyContractV2` and `safety: SafetyContractV2 | None = None` to `EvaluationContractV2` and `__all__`. Write the failing test `test_safety_contract_v2.py` mirroring `test_robustness_contract_v2.py` (copy its draft-create/confirm flow; replace dimension with `SAFETY` and add `severe_column`). Implement the same handling everywhere ROBUSTNESS is handled (grep list above), including `evaluation_service_v2.py` building `safety_contract`. Run `python -m pytest tests/test_safety_contract_v2.py tests/test_evaluation_service_v2.py tests/test_evaluation_draft_service.py tests/test_evaluation_drafts_router.py -q`.
- [ ] **Step 5: Probe branch.** In `SafetyProbe.run`, if `ctx.evaluation_contract and ctx.evaluation_contract.safety`: load rows exactly as `RobustnessProbe._run_v2` does (reuse `load_samples_for_robustness_with_label_mapping` from `datasets/user_dataset.py`, plus read the severe column from the same content bytes), run inference with `LocalHFBackend`, apply `prediction_collapse` (Task 1), call `evaluate_behavior`, and add to `metrics`: `behavior: {severe_n, severe_fnr, severe_fnr_ci, overall_fnr, fnr_ratio}` and top-level `severe_fnr`, `fnr_ratio`. Card checks stay. Add a probe test with a fake backend that misses all severe rows -> `severe_fnr == 1.0`.
- [ ] **Step 6: Band.** In `osd/agent.py` add `_safety_band(m)` using the formula in Interfaces when `severe_fnr` is present else the existing `_card_band`; test: `_safety_band({"severe_fnr": 0.5, "fnr_ratio": 2.5})[0] == (5, 3, 8)`. Update `llm_client.build_prompt` to include `severe_fnr`, `fnr_ratio` in the Safety evidence block (read `build_prompt` first; add the two keys to the evidence dict it serialises). Bump methodology version (as Task 7 Step 4).
- [ ] **Step 7: Suite wiring and run.** In `run_flawed_suite_eval.create_and_run_evaluation`, add a SAFETY draft config after ROBUSTNESS: `{"dataset_content_id", "text_column":"text","target_column":"label","severe_column":"severe","label_mapping": label_mapping, "positive_label_index":1, "min_severe_n":30}` + confirm. Run all 8 models (use the 2-label reference); output to `eval_results_v5/`.
- [ ] **Step 8: Check the claim.** Expected: V5 and V6 have a high `severe_fnr` and lower Safety than the reference; if V5 does not separate, report that honestly (the flaw may be too weak at 244 relabelled rows).
- [ ] **Step 9: Report:** ch4 Safety section rewritten (behavioural + card), ch7 new table, ch8/ch10 move "Safety does not test behaviour" from limitation to implemented, with the measured outcome.
- [ ] **Step 10: Commit** in logical commits: `feat(safety): behavioural severe-FNR evaluation`, `feat(contract): optional safety contract v2`, `feat(osd): safety band from severe FNR`, `results: suite with behavioural safety`.

---

### Task 10: Native multi-label decision rule

**Files:**
- Modify: `backend/app/inference/base.py` (`InferenceConfig`: add `multilabel_positive_index: int | None = None`)
- Modify: `backend/app/inference/local_hf.py::_decode_logits` (lines 255-270)
- Modify: `backend/app/probes/fairness.py`, `robustness.py` (set the field when the model snapshot has >2 labels and the contract's `positive_label_index` names the toxic output) - read how `InferenceConfig(...)` is built (`fairness.py:~255`) first.
- Test: `backend/tests/test_inference_backend.py` (extend)

**Interfaces:**
- Produces: when `multilabel_positive_index = k`, `y_hat = 1 if sigmoid(logit[k]) >= binary_threshold else 0` and `probabilities = [1 - p, p]`.

- [ ] **Step 1: Failing test** — instantiate `LocalHFBackend` decode via `_decode_logits` on a config with `multilabel_positive_index=0`, logits `[2.0, -5.0, -5.0]` -> `y_hat == 1`; logits `[-2.0, 4.0, 4.0]` -> `y_hat == 0` (second is the old argmax bug).
- [ ] **Step 2: Implement** in `_decode_logits`, before the softmax:

```python
        k = self._config.multilabel_positive_index
        if k is not None:
            p = 1.0 / (1.0 + math.exp(-row_logits[k]))
            return PredictionRecord(
                y_hat=1 if p >= self._config.binary_threshold else 0,
                probabilities=[1.0 - p, p],
                logits=list(row_logits),
            )
```
(import `math` if absent).
- [ ] **Step 3:** Run `python -m pytest tests/test_inference_backend.py tests/test_fairness_contract_v2.py -q`.
- [ ] **Step 4: Verify equivalence on the real model:** evaluate the Hub `unitary/toxic-bert` with `multilabel_positive_index=0` and compare DPD/accuracy with `eval_results_v3` (2-label conversion); they should agree within a few predictions. Save the comparison in `results/flawed_model_suite/multilabel_check.json`.
- [ ] **Step 5: Report:** ch5/ch7 replace the conversion paragraph by the native rule (keep the conversion as a cross-check).
- [ ] **Step 6: Commit** — `git commit -m "feat(inference): native multi-label positive-output decision rule"`.

---

### Task 11: Extra Hub models (breadth)

**Files:**
- Create: `backend/app/scripts/extra_models_eval.py`
- Create: `results/flawed_model_suite/extra_models.json` (list of repos, chosen by the team)
- Test: none beyond a smoke run (selection list is data)

**Interfaces:**
- Consumes: `run_flawed_suite_eval.register_hf_model`, `create_and_run_evaluation`; a list of 5-10 public Hub toxicity/hate-speech classifiers with matching binary labels.

- [ ] **Step 1: Choose models** with the Hugging Face MCP/`hf` CLI: `hf models ls --search toxic --filter text-classification --sort downloads --limit 30`; for each candidate read `config.json` `id2label`. Keep 5-10 with a clear "toxic" output; for six-label heads use the Task 10 rule. Record `repo`, `id2label`, `toxic_index`, `license` in `extra_models.json`.
- [ ] **Step 2: Script** — loop over the list, register via `import-hf`, evaluate with the Task-9 contract set (SAFETY included), save under `eval_results_extra/`; store failures in `_summary.json` with the error (some models will fail to load; record, do not hide).
- [ ] **Step 3: Run** (~15 min per model at most); inspect outputs.
- [ ] **Step 4: Report:** ch7 table of extra models vs the forged ones (FRIES and per-dimension); ch8 discuss whether the forged variants fall below real models; state that no ground-truth trust labels exist for them.
- [ ] **Step 5: Commit** — `git commit -m "results: evaluate additional Hub toxicity models"`.

---

### Task 12: Blind human rating study

**Files:**
- Create: `docs/human_rating/protocol.md`, `docs/human_rating/rating_sheet.csv`, `backend/app/scripts/analyze_ratings.py`
- Test: `backend/tests/test_analyze_ratings.py`

**Interfaces:**
- Produces: `spearman(x: list[float], y: list[float]) -> float` (no scipy dependency; ranks with average ties); `analyze(ratings_csv, scores_json) -> dict` returning per-rater Spearman vs FRIES mean, and mean pairwise rater-rater Spearman.

- [ ] **Step 1: Write the failing test**

```python
from app.scripts.analyze_ratings import spearman

def test_perfect_and_inverse_and_ties():
    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9
    assert abs(spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-9
    assert abs(spearman([1, 1, 2, 3], [1, 2, 3, 4]) - 0.9486832980505138) < 1e-9
```
Run -> FAIL.

- [ ] **Step 2: Implement** average-rank Spearman (Pearson on ranks):

```python
def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v); i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r

def spearman(x, y):
    a, b = _ranks(x), _ranks(y)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    den = (sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b)) ** 0.5
    return num / den if den else 0.0
```
Run test -> PASS.
- [ ] **Step 3: Protocol** (`protocol.md`): 3 raters who did not build the probes; each gets, per model (shuffled, anonymised "Model 01..N"), the model card, the Fairness/Robustness/Safety measured evidence (DPD, drop, severe FNR with CIs) and no FRIES scores; each rates "How much would you trust this model for content moderation, 1-7", independently, 15 minutes per model, no discussion. Sheet columns: `model_code,rater,trust_1_7,comment`. The key mapping `model_code -> model` is kept by one team member and applied only at analysis.
- [ ] **Step 4: Run the study** with 3 classmates over 2 days; collect `rating_sheet.csv`.
- [ ] **Step 5: Analyze** with `analyze()`; report Spearman between mean human rating and mean FRIES (n = 8 to 18 models), rater agreement, and the models where humans and FRIES disagree most. With n this small, report the coefficient with a bootstrap CI and say it is a pilot, not validation.
- [ ] **Step 6: Report:** ch7 section "Pilot human validation"; ch8 construct-validity paragraph updated with the observed correlation (whatever it is); ch10 Q3 updated.
- [ ] **Step 7: Commit** — `git commit -m "feat: blind human-rating pilot and analysis"`.

---

### Task 13: Final full re-evaluation and report update

**Files:**
- Modify: all `report/chapters/*.tex`, `report/make_figures.py`
- Create: `results/flawed_model_suite/eval_results_final/`

- [ ] **Step 1: Freeze code:** `git tag report-final-v2` after all tests pass: `cd backend && python -m pytest -q && python -m ruff check app tests`; `cd ../frontend && npm test -- --run` (confirm script name in `frontend/package.json`).
- [ ] **Step 2: Final run:** `python -m app.scripts.repeat_eval --runs 5 --out eval_results_final` over the 6 variants and the corrected reference, with the new safety contract and Hub-hosted variants if Task 5 succeeded.
- [ ] **Step 3: Regenerate figures** from `eval_results_final`; update every number in ch7 tables and in the abstract from the files (do not edit by hand; extend `make_figures.py` to dump a `numbers.txt` for each table and copy from it).
- [ ] **Step 4: Rewrite ch8 and ch10** against the final evidence: each of the earlier limitations gets one of `resolved (evidence)`, `reduced (how much)`, `unchanged`. Do not claim a fix that the data does not show; if H1/H2 do not hold, say so.
- [ ] **Step 5: Fill the red `[INFORMATION REQUIRED]` items:** test counts (`pytest -q` summary), coverage (`pytest --cov=app` if `pytest-cov` is installed), peak VRAM/time (run `nvidia-smi --query-gpu=memory.used --format=csv -l 1` during one evaluation and record the maximum).
- [ ] **Step 6: Build:** `cd report && python make_figures.py && tectonic main.tex && tectonic main.tex`; check page count, no `??` references (`python -c` check as before).
- [ ] **Step 7: Commit and tag:** `git add -A report results docs && git commit -m "report: final results after hardening month"`.

---

## Self-Review

**Spec coverage** (limitations in `ch10_conclusion.tex` future-work list -> task): 1 reference rerun/collapse warning -> Tasks 1, 10; 2 behavioural safety -> 9; 3 pin/log LLM, repeats -> 2, 3, 4; 4 stronger robustness + band -> 7 (attack variety is cut; word-level swap is deferred, see below); 5 fairness beyond one attribute/base rate -> 8 (multiple attributes deferred); 6 more models, human ratings, more forgers -> 11, 12 (more forgers: see below); 7 provenance -> 5, 6; 8 resource gating -> not planned (low report value); 9 calibration -> not planned (needs ground truth; partially approached by Task 12).

**Deliberate cuts, to say in the report:** word-level perturbation and multi-attribute fairness are optional stretch work after Task 8 (`robustness_nlp.py` gets a `word_swap_attack(text, rng)`, same pattern as `char_swap_attack`; add only if Week 3 has slack); the "second forger" needs a teammate who has not read the probes and who builds one variant from the README spec alone, evaluated with the same harness, add if Week 4 has slack; resource checker is excluded.

**Placeholder scan:** steps that say "read X first" name the exact file/lines and what to copy; code for every new pure function is given. Items that depend on external choices (Hub username, HF token, which extra models, human raters) are marked as human steps.

**Type consistency:** `prediction_collapse` (Task 1) is reused in Task 9 Step 5; `summarize_runs` (Task 2) is used by Tasks 4 and 13; `evaluate_behavior` fields `severe_fnr`, `fnr_ratio` match `_safety_band` keys; `integrity_extra_for` keys match `integrity_eval.py:372-373`; `hub_repo_id` (Task 5) is used in `run_flawed_suite_eval --hub-prefix`.

**Review Focus coverage:** constant predictor (Task 1 tests), 97% not collapsed (Task 1 test), failed repeat run (Task 2 test), tamper vs untouched (Task 6 tests), zero severe rows (Task 9 tests), group without positives (Task 8 test).

**Risks:** (1) Task 9 touches six files; start Oct 19 at the latest. (2) LLM free-tier rate limits during 40+ evaluations in Task 4; run overnight, resume with `--only`. (3) V5's flaw (244 relabelled rows) may be too weak to move severe FNR; if so, retrain a stronger V5 (`train_flawed_suite.py --variant 5` with a 0.9 relabel rate) and document it as a second V5 design, as was done for V2. (4) Task 12 depends on three people's time; schedule on Oct 12.
