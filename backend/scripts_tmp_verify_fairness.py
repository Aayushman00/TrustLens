"""Compose verify: run evaluation and print FAIRNESS probe_results row."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_scope
from app.db.models import ProbeResult


def req(method: str, path: str, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:8000{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def main() -> None:
    login = req(
        "POST",
        "/v1/auth/login",
        {
            "email": "researcher@trustlens.local",
            "password": "trustlens-researcher-dev",
        },
    )
    token = login["access_token"]
    print("login_ok", bool(token))
    imp = req(
        "POST",
        "/v1/models/import-hf",
        {"repo_id": "distilbert-base-uncased"},
        token=token,
    )
    print("model_id", imp["id"])
    ev = req(
        "POST",
        "/v1/evaluations",
        {
            "model_id": imp["id"],
            "evaluation_mode": "AI_AUTONOMOUS",
            "probe_config": {
                "schema_version": "v1",
                "datasets": {"fairness": "adult_fairness"},
                "extra": {"max_samples": 64, "seed": 42, "min_group_n": 30},
            },
        },
        token=token,
    )
    eval_id = ev["id"]
    print("eval_id", eval_id, "status", ev.get("status"))
    final = None
    for i in range(90):
        time.sleep(5)
        row = req("GET", f"/v1/evaluations/{eval_id}", token=token)
        status = row.get("status")
        prog = row.get("probe_progress")
        print(f"poll {i}: status={status} progress={prog}")
        if status in {"FINALIZED", "FAILED", "AWAITING_REVIEW"}:
            final = row
            break
    print("final_status", None if final is None else final.get("status"))

    settings = get_settings()
    with session_scope(settings.database_url) as session:
        rows = list(
            session.scalars(
                select(ProbeResult)
                .where(ProbeResult.evaluation_id == UUID(str(eval_id)))
                .order_by(ProbeResult.id)
            )
        )
        for r in rows:
            mv = r.metric_values or {}
            print(
                r.dimension.value,
                "stub=",
                mv.get("stub"),
                "dp=",
                mv.get("demographic_parity_difference"),
                "eo=",
                mv.get("equalized_odds_difference"),
                "f1s=",
                mv.get("subgroup_f1_spread"),
                "nhr=",
                mv.get("needs_human_review"),
                "skip=",
                mv.get("skip_reason"),
                "dataset=",
                (mv.get("dataset") or {}).get("logical_key"),
            )


if __name__ == "__main__":
    main()
