"""Compose verify (Phase 22): opt-in publish/unpublish + published-only leaderboard."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid

API = "http://127.0.0.1:8000"

FAST_PROBE_CONFIG = {
    "schema_version": "v1",
    "datasets": {"fairness": "adult_fairness"},
    "extra": {"max_samples": 64, "seed": 42, "min_group_n": 30},
}


def req(method: str, path: str, data=None, token=None, expect_error: int | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(f"{API}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if expect_error is not None and exc.code == expect_error:
            return json.loads(detail)
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def login(email: str, password: str) -> str:
    return req("POST", "/v1/auth/login", {"email": email, "password": password})["access_token"]


def run_eval(token: str, model_id: int, mode: str, task: str, wait_for: set[str]) -> dict:
    ev = req(
        "POST",
        "/v1/evaluations",
        {
            "model_id": model_id,
            "evaluation_mode": mode,
            "task": task,
            "dataset": "adult_fairness",
            "probe_config": FAST_PROBE_CONFIG,
        },
        token=token,
    )
    eval_id = ev["id"]
    print(f"  created {mode} eval {eval_id} (task={task})")
    for i in range(120):
        time.sleep(5)
        row = req("GET", f"/v1/evaluations/{eval_id}", token=token)
        status = row["status"]
        if i % 6 == 0 or status in wait_for or status == "FAILED":
            print(f"  poll {i}: status={status}")
        if status in wait_for | {"FAILED"}:
            assert status in wait_for, f"evaluation failed: {row}"
            return row
    raise RuntimeError("timeout waiting for evaluation")


def listed_ids(token: str, query: str = "") -> list[str]:
    return [e["evaluation_id"] for e in req("GET", f"/v1/leaderboard{query}", token=token)["items"]]


def main() -> None:
    researcher = login("researcher@trustlens.local", "trustlens-researcher-dev")
    reviewer = login("reviewer@trustlens.local", "trustlens-reviewer-dev")
    print("login ok")

    err = req("GET", "/v1/leaderboard", expect_error=401)
    assert err["code"] in {"UNAUTHORIZED", "INVALID_TOKEN"}, err
    print("unauthenticated leaderboard -> 401 ok")

    model = req("POST", "/v1/models/import-hf", {"repo_id": "distilbert-base-uncased"},
                token=researcher)
    task = f"lb-verify-{uuid.uuid4().hex[:6]}"
    print(f"model_id={model['id']} task={task}")

    # --- Autonomous: FINALIZED, private by default ---
    print("AUTONOMOUS:")
    auto = run_eval(researcher, model["id"], "AI_AUTONOMOUS", task, {"FINALIZED"})
    auto_id = auto["id"]
    assert auto_id not in listed_ids(researcher, f"?task={task}"), "must be private by default"
    print("  finalized + unpublished -> not listed ok")

    # Non-owner/non-admin -> 403 (reviewer is neither)
    denied = req("POST", f"/v1/evaluations/{auto_id}/publish", token=reviewer, expect_error=403)
    assert denied["code"] == "FORBIDDEN", denied
    print("  non-owner publish -> 403 ok")

    # Attach a report so the entry carries a report ref
    report = req("GET", f"/v1/reports/{auto_id}", token=researcher)
    assert report["version"] == 1
    print("  report v1 generated")

    published = req("POST", f"/v1/evaluations/{auto_id}/publish", token=researcher)
    assert published["is_published"] is True and published["published_at"]
    again = req("POST", f"/v1/evaluations/{auto_id}/publish", token=researcher)
    assert again["published_at"] == published["published_at"], "idempotent republish"
    print("  publish ok (idempotent, published_at stable)")

    body = req("GET", f"/v1/leaderboard?task={task}", token=researcher)
    assert body["note"] is None, "task filter given -> no note"
    entry = next(e for e in body["items"] if e["evaluation_id"] == auto_id)
    assert entry["fries_score"] > 0 and entry["evaluation_mode"] == "AI_AUTONOMOUS"
    assert entry["human_reviewed"] is False and entry["task"] == task
    assert entry["report"] and entry["report"]["version"] >= 1 and entry["report"]["json_uri"]
    print(f"  listed ok: fries={entry['fries_score']} report={entry['report']['json_uri']}")

    no_filter = req("GET", "/v1/leaderboard", token=researcher)
    assert no_filter["note"] and "not directly comparable" in no_filter["note"]
    print("  no task filter -> non-comparability note ok")

    # --- Assisted: 409 before finalize; human_reviewed=true after ---
    print("ASSISTED:")
    assisted = run_eval(researcher, model["id"], "AI_ASSISTED", task, {"AWAITING_REVIEW"})
    assisted_id = assisted["id"]
    conflict = req("POST", f"/v1/evaluations/{assisted_id}/publish", token=researcher,
                   expect_error=409)
    assert conflict["code"] == "NOT_FINALIZED", conflict
    print("  non-finalized publish -> 409 NOT_FINALIZED ok")

    req("POST", f"/v1/evaluations/{assisted_id}/human-review", {"accept_all": True},
        token=reviewer)
    req("POST", f"/v1/evaluations/{assisted_id}/finalize", token=reviewer)
    req("POST", f"/v1/evaluations/{assisted_id}/publish", token=researcher)
    print("  reviewed + finalized + published")

    assisted_only = req(
        "GET", f"/v1/leaderboard?task={task}&evaluation_mode=AI_ASSISTED", token=researcher
    )
    entry = next(e for e in assisted_only["items"] if e["evaluation_id"] == assisted_id)
    assert entry["human_reviewed"] is True
    assert auto_id not in [e["evaluation_id"] for e in assisted_only["items"]]
    auto_only = listed_ids(researcher, f"?task={task}&evaluation_mode=AI_AUTONOMOUS")
    assert auto_id in auto_only and assisted_id not in auto_only
    print("  mode filter ok (assisted human_reviewed=true, autonomous excluded)")

    # --- Unpublish -> gone again ---
    gone = req("POST", f"/v1/evaluations/{auto_id}/unpublish", token=researcher)
    assert gone["is_published"] is False and gone["published_at"] is None
    req("POST", f"/v1/evaluations/{auto_id}/unpublish", token=researcher)  # idempotent
    assert auto_id not in listed_ids(researcher, f"?task={task}")
    req("POST", f"/v1/evaluations/{assisted_id}/unpublish", token=researcher)  # cleanup
    print("  unpublish ok (idempotent, delisted)")

    print("PHASE 22 LIVE VERIFY: ALL OK")


if __name__ == "__main__":
    main()
