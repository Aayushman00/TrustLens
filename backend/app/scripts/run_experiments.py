"""Phase 25 experiment runner — creates and polls benchmark evaluations via the API.

Reads ``configs/experiments_v1.yaml`` (see ``docs/experiments_runbook.md``),
drives the real product path (import-hf → create evaluation → poll to the
terminal status), measures client-side wall time, and appends one JSON line
per run to ``results/manifest_v1.jsonl``. Resumable: (model, mode, repeat)
tuples already in the manifest are skipped — delete a line to redo a run.

Usage (host, against the Compose stack)::

    cd backend
    python -m app.scripts.run_experiments --mode c            # Mode C batch + det-check
    python -m app.scripts.run_experiments --mode b            # Mode B assisted creates
    python -m app.scripts.run_experiments --mode b-review \
        --plan ../results/mode_b_review_plan.json             # review pass + finalize

    # Pilot helpers: --only <repo substring>  --seeds 42  --dry-run

Single-user local instance — no login/credentials required.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "experiments_v1.yaml"
MANIFEST_PATH = REPO_ROOT / "results" / "manifest_v1.jsonl"

TERMINAL_BY_MODE = {
    "C": {"FINALIZED", "FAILED"},
    "B": {"AWAITING_REVIEW", "FAILED"},
}


@dataclass(frozen=True)
class RunKey:
    hf_repo_id: str
    mode: str  # "C" | "B"
    repeat: str  # "seed-42" | "det-check"


def _load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return []
    rows = []
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _manifest_keys(rows: list[dict[str, Any]]) -> set[RunKey]:
    return {RunKey(r["hf_repo_id"], r["mode"], r["repeat"]) for r in rows}


def _append_manifest(row: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _login(client: httpx.Client, role: str) -> dict[str, str]:
    """No-op — TrustLens is single-user local; the API takes no auth headers."""
    del client, role
    return {}


def _import_model(client: httpx.Client, headers: dict[str, str], repo_id: str) -> dict[str, Any]:
    response = client.post(
        "/v1/models/import-hf", json={"repo_id": repo_id}, headers=headers
    )
    if response.status_code != 201:
        raise RuntimeError(
            f"import-hf failed for {repo_id}: {response.status_code} {response.text}"
        )
    return response.json()


def _build_probe_config(cfg: dict[str, Any], model_entry: dict[str, Any], seed: int) -> dict[str, Any]:
    probe_config = copy.deepcopy(cfg["probe_config_template"])
    override = model_entry.get("robustness_dataset")
    if override:
        probe_config.setdefault("datasets", {})["robustness"] = override
    probe_config.setdefault("extra", {})["seed"] = seed
    return probe_config


def _poll_terminal(
    client: httpx.Client,
    headers: dict[str, str],
    evaluation_id: str,
    *,
    terminal: set[str],
    poll_interval_s: float,
    timeout_s: float,
) -> tuple[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    while True:
        response = client.get(f"/v1/evaluations/{evaluation_id}", headers=headers)
        response.raise_for_status()
        body = response.json()
        status = body["status"]
        if status in terminal:
            return status, body
        if time.monotonic() > deadline:
            return f"TIMEOUT({status})", body
        time.sleep(poll_interval_s)


def _run_one(
    client: httpx.Client,
    headers: dict[str, str],
    cfg: dict[str, Any],
    model_entry: dict[str, Any],
    model_row: dict[str, Any],
    *,
    mode: str,
    repeat: str,
    seed: int,
) -> None:
    repo_id = model_entry["hf_repo_id"]
    probe_config = _build_probe_config(cfg, model_entry, seed)
    payload = {
        "model_id": model_row["id"],
        "evaluation_mode": "AI_AUTONOMOUS" if mode == "C" else "AI_ASSISTED",
        "probe_config": probe_config,
        "task": model_entry.get("task"),
        "dataset": model_entry.get("dataset"),
        "trustlens_version": str(cfg.get("trustlens_version", "")) or None,
    }
    runner_cfg = cfg.get("runner", {})
    started = time.perf_counter()
    created = client.post("/v1/evaluations", json=payload, headers=headers)
    if created.status_code != 201:
        raise RuntimeError(
            f"create failed for {repo_id}: {created.status_code} {created.text}"
        )
    evaluation_id = created.json()["id"]
    print(f"  created {mode}/{repeat} -> {evaluation_id} (polling...)", flush=True)
    status, detail = _poll_terminal(
        client,
        headers,
        evaluation_id,
        terminal=TERMINAL_BY_MODE[mode],
        poll_interval_s=float(runner_cfg.get("poll_interval_s", 5)),
        timeout_s=float(runner_cfg.get("timeout_s", 1800)),
    )
    wall_s = round(time.perf_counter() - started, 2)
    final_score = detail.get("final_score") or {}
    _append_manifest(
        {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "evaluation_id": evaluation_id,
            "hf_repo_id": repo_id,
            "model_id": model_row["id"],
            "model_revision": model_row.get("revision"),
            "mode": mode,
            "repeat": repeat,
            "seed": seed,
            "wall_s": wall_s,
            "status": status,
            "fries_score": final_score.get("fries_score"),
        }
    )
    print(f"  {status} in {wall_s}s fries={final_score.get('fries_score')}", flush=True)


def _iter_mode_c_runs(cfg: dict[str, Any], seeds: list[int]) -> list[tuple[dict[str, Any], str, int]]:
    """(model_entry, repeat_key, seed) for the batch + determinism check."""
    runs = [
        (entry, f"seed-{seed}", seed)
        for entry in cfg["models"]
        for seed in seeds
    ]
    det = cfg.get("determinism_check")
    if det:
        entry = next(
            (m for m in cfg["models"] if m["hf_repo_id"] == det["hf_repo_id"]), None
        )
        if entry and det["seed"] in seeds:
            runs.append((entry, "det-check", det["seed"]))
    return runs


def _cmd_batch(args: argparse.Namespace, cfg: dict[str, Any], mode: str) -> int:
    seeds = [int(s) for s in (args.seeds or cfg["seeds"])]
    if mode == "C":
        planned = _iter_mode_c_runs(cfg, seeds)
    else:
        b_cfg = cfg["mode_b"]
        by_id = {m["hf_repo_id"]: m for m in cfg["models"]}
        planned = [
            (by_id[m["hf_repo_id"]], f"seed-{b_cfg['seed']}", int(b_cfg["seed"]))
            for m in b_cfg["models"]
        ]
    if args.only:
        planned = [p for p in planned if args.only in p[0]["hf_repo_id"]]

    done = _manifest_keys(_load_manifest())
    todo = [
        p for p in planned if RunKey(p[0]["hf_repo_id"], mode, p[1]) not in done
    ]
    print(f"mode {mode}: {len(planned)} planned, {len(todo)} to run "
          f"({len(planned) - len(todo)} already in manifest)")
    if args.dry_run:
        for entry, repeat, seed in todo:
            print(f"  would run {entry['hf_repo_id']} {repeat} seed={seed}")
        return 0
    if not todo:
        return 0

    with httpx.Client(base_url=cfg["api_base_url"], timeout=120.0) as client:
        headers = _login(client, "researcher")
        model_rows: dict[str, dict[str, Any]] = {}
        for entry, repeat, seed in todo:
            repo_id = entry["hf_repo_id"]
            if repo_id not in model_rows:
                print(f"import-hf {repo_id}", flush=True)
                model_rows[repo_id] = _import_model(client, headers, repo_id)
            print(f"run {repo_id} {repeat} seed={seed}", flush=True)
            _run_one(
                client, headers, cfg, entry, model_rows[repo_id],
                mode=mode, repeat=repeat, seed=seed,
            )
    return 0


def _cmd_b_review(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Apply the committed review plan to AWAITING_REVIEW Mode B runs, then finalize."""
    plan_path = Path(args.plan) if args.plan else REPO_ROOT / "results" / "mode_b_review_plan.json"
    plan: dict[str, dict[str, Any]] = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = _load_manifest()
    b_rows = [r for r in manifest if r["mode"] == "B" and r["status"] == "AWAITING_REVIEW"]
    if not b_rows:
        print("no AWAITING_REVIEW Mode B rows in manifest")
        return 1

    with httpx.Client(base_url=cfg["api_base_url"], timeout=120.0) as client:
        headers = _login(client, "reviewer")
        for row in b_rows:
            repo_id = row["hf_repo_id"]
            review = plan.get(repo_id)
            if review is None:
                print(f"skip {repo_id}: no entry in {plan_path.name}")
                continue
            evaluation_id = row["evaluation_id"]
            detail = client.get(f"/v1/evaluations/{evaluation_id}", headers=headers)
            detail.raise_for_status()
            if detail.json()["status"] != "AWAITING_REVIEW":
                print(f"skip {repo_id}: status={detail.json()['status']} (already reviewed?)")
                continue
            submitted = client.post(
                f"/v1/evaluations/{evaluation_id}/human-review",
                json=review,
                headers=headers,
            )
            if submitted.status_code != 201:
                raise RuntimeError(
                    f"review failed for {repo_id}: {submitted.status_code} {submitted.text}"
                )
            finalized = client.post(
                f"/v1/evaluations/{evaluation_id}/finalize", headers=headers
            )
            if finalized.status_code != 200:
                raise RuntimeError(
                    f"finalize failed for {repo_id}: {finalized.status_code} {finalized.text}"
                )
            fin = finalized.json()
            print(
                f"reviewed+finalized {repo_id}: human_changed="
                f"{submitted.json()['human_changed']} "
                f"fries={fin['final_score']['fries_score']}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["c", "b", "b-review"])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--only", help="substring filter on hf_repo_id (pilot)")
    parser.add_argument("--seeds", nargs="*", help="override seed list (pilot)")
    parser.add_argument("--plan", help="review plan JSON for --mode b-review")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    if args.mode == "c":
        return _cmd_batch(args, cfg, "C")
    if args.mode == "b":
        return _cmd_batch(args, cfg, "B")
    return _cmd_b_review(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
