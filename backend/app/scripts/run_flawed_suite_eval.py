"""Runs the flawed-model-suite comparison against the real TrustLens API
(docker compose stack), per Task 7 of docs/superpowers/plans/
2026-09-15-flawed-model-suite-for-osd-demo.md.

For each of the 6 local variants + unitary/toxic-bert:
  1. Register the model (POST /v1/models for local checkpoints — card_text
     read from results/flawed_model_suite/cards/<variant>/README.md; POST
     /v1/models/import-hf for unitary/toxic-bert).
  2. Create an EvaluationDraft, configure + confirm FAIRNESS and ROBUSTNESS
     against the shared eval_set.csv (uploaded once, reused for all 7).
  3. Consume the draft into a real evaluation (AI_AUTONOMOUS, llm_v1).
  4. Poll until FINALIZED/FAILED, save the full response, and collect the
     FRIES/dimension score row.

Requires the compose stack up (`docker compose up -d`) and the worker
container to have `results/flawed_model_suite/models` bind-mounted at
`/models/flawed_model_suite` (see docker-compose.override.yml).

Usage (from backend/, against http://localhost:8000)::

    python -m app.scripts.run_flawed_suite_eval
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE_DIR = REPO_ROOT / "results" / "flawed_model_suite"
CARDS_DIR = SUITE_DIR / "cards"
OUT_DIR = SUITE_DIR / "eval_results"

API_BASE = "http://localhost:8000/v1"
WORKER_MODEL_ROOT = "/models/flawed_model_suite"  # bind-mount path inside the worker container

POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 900
TERMINAL_STATUSES = {"FINALIZED", "AWAITING_REVIEW", "FAILED"}

LOCAL_VARIANTS = [
    "variant1_fairness",
    "variant2_robustness",
    "variant3_explainability",
    "variant4_integrity",
    "variant5_safety",
    "variant6_compound",
]
TRUSTWORTHY_HF_REPO = "unitary/toxic-bert"


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=60.0)


def upload_eval_dataset(client: httpx.Client) -> str:
    csv_path = SUITE_DIR / "data" / "eval_set.csv"
    with csv_path.open("rb") as f:
        resp = client.post("/dataset-uploads", files={"file": ("eval_set.csv", f, "text/csv")})
    resp.raise_for_status()
    body = resp.json()
    print(f"  uploaded eval_set.csv -> dataset_content_id={body['id']} rows={body['row_count']}")
    return body["id"]


def register_local_model(client: httpx.Client, variant: str) -> int:
    card_text = (CARDS_DIR / variant / "README.md").read_text(encoding="utf-8")
    license_value = "apache-2.0" if variant not in ("variant3_explainability", "variant4_integrity", "variant6_compound") else None
    if variant in ("variant4_integrity", "variant6_compound"):
        license_value = "other"
    body: dict[str, Any] = {
        "hf_repo_id": f"{WORKER_MODEL_ROOT}/{variant}",
        "model_metadata": {"card_text": card_text, "card_data": ({"license": license_value} if license_value else {})},
        # Local checkpoints have no HF revision; the draft-creation gate
        # requires a non-null pinned value, so use a fixed sentinel — the
        # inference loader (transformers `from_pretrained`) ignores
        # `revision` for a local directory path anyway.
        "revision": "local",
    }
    resp = client.post("/models", json=body)
    if resp.status_code == 409:
        row = _find_existing_model(client, body["hf_repo_id"])
        print(f"  {variant} already registered -> model_id={row['id']}")
        return row["id"]
    resp.raise_for_status()
    row = resp.json()
    print(f"  registered {variant} -> model_id={row['id']}")
    return row["id"]


def _find_existing_model(client: httpx.Client, hf_repo_id: str) -> dict[str, Any]:
    cursor: str | None = None
    while True:
        params = {"limit": 200} | ({"cursor": cursor} if cursor else {})
        resp = client.get("/models", params=params)
        resp.raise_for_status()
        body = resp.json()
        for item in body["items"]:
            if item["hf_repo_id"] == hf_repo_id:
                return item
        cursor = body.get("next_cursor")
        if not cursor:
            raise RuntimeError(f"model {hf_repo_id!r} reported as conflicting but not found in list")


def register_hf_model(client: httpx.Client, repo_id: str) -> int:
    resp = client.post("/models/import-hf", json={"repo_id": repo_id})
    resp.raise_for_status()  # import-hf upserts on repo_id, no 409 case
    row = resp.json()
    print(f"  imported {repo_id} -> model_id={row['id']}")
    return row["id"]


def create_and_run_evaluation(client: httpx.Client, model_id: int, dataset_content_id: str) -> dict[str, Any]:
    draft = client.post("/evaluation-drafts", json={"model_id": model_id})
    draft.raise_for_status()
    draft_id = draft.json()["id"]

    label_mapping = [
        {"dataset_value": "0", "model_label_index": 0},
        {"dataset_value": "1", "model_label_index": 1},
    ]

    fairness_body = {
        "dataset_content_id": dataset_content_id,
        "text_column": "text",
        "target_column": "label",
        "sensitive_column": "identity_ref",
        "label_mapping": label_mapping,
        "min_group_n": 30,
        "positive_label_index": 1,
    }
    r = client.put(f"/evaluation-drafts/{draft_id}/FAIRNESS", json=fairness_body)
    r.raise_for_status()
    if not r.json().get("ok", True):
        raise RuntimeError(f"FAIRNESS config invalid: {r.json()}")
    r = client.post(f"/evaluation-drafts/{draft_id}/FAIRNESS/confirm")
    r.raise_for_status()

    robustness_body = {
        "dataset_content_id": dataset_content_id,
        "text_column": "text",
        "target_column": "label",
        "sensitive_column": None,
        "label_mapping": label_mapping,
    }
    r = client.put(f"/evaluation-drafts/{draft_id}/ROBUSTNESS", json=robustness_body)
    r.raise_for_status()
    if not r.json().get("ok", True):
        raise RuntimeError(f"ROBUSTNESS config invalid: {r.json()}")
    r = client.post(f"/evaluation-drafts/{draft_id}/ROBUSTNESS/confirm")
    r.raise_for_status()

    r = client.post(
        "/evaluations-v2",
        json={"draft_id": draft_id, "evaluation_mode": "AI_AUTONOMOUS", "assessment_engine": "llm_v1"},
    )
    r.raise_for_status()
    evaluation = r.json()
    evaluation_id = evaluation["id"]

    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        r = client.get(f"/evaluations/{evaluation_id}")
        r.raise_for_status()
        evaluation = r.json()
        status = evaluation["status"]
        if status in TERMINAL_STATUSES:
            print(f"    evaluation {evaluation_id} -> {status}")
            return evaluation
        time.sleep(POLL_INTERVAL_S)

    raise TimeoutError(f"evaluation {evaluation_id} did not reach a terminal status in {POLL_TIMEOUT_S}s (last: {evaluation.get('status')})")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []

    with _client() as client:
        print("Uploading shared eval dataset...")
        dataset_content_id = upload_eval_dataset(client)

        targets: list[tuple[str, int]] = []
        print("Registering models...")
        for variant in LOCAL_VARIANTS:
            model_id = register_local_model(client, variant)
            targets.append((variant, model_id))
        trustworthy_model_id = register_hf_model(client, TRUSTWORTHY_HF_REPO)
        targets.append(("trustworthy_" + TRUSTWORTHY_HF_REPO.replace("/", "_"), trustworthy_model_id))

        for name, model_id in targets:
            print(f"Running evaluation for {name} (model_id={model_id})...")
            evaluation = create_and_run_evaluation(client, model_id, dataset_content_id)
            (OUT_DIR / f"{name}.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")

            final_score = evaluation.get("final_score") or {}
            dims = final_score.get("dimension_scores") or {}
            summary.append(
                {
                    "name": name,
                    "model_id": model_id,
                    "status": evaluation["status"],
                    "fries_score": final_score.get("fries_score"),
                    "dimension_scores": dims,
                }
            )

    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n=== Summary ===")
    for row in summary:
        print(f"{row['name']:40s} status={row['status']:12s} FRIES={row['fries_score']}  dims={row['dimension_scores']}")


if __name__ == "__main__":
    main()
