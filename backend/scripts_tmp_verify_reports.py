"""Compose verify (Phase 19): reports for Autonomous + Assisted, versioning, MinIO PDF."""
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


def run_eval(token: str, model_id: int, mode: str, wait_for: set[str]) -> dict:
    ev = req(
        "POST",
        "/v1/evaluations",
        {"model_id": model_id, "evaluation_mode": mode, "probe_config": FAST_PROBE_CONFIG},
        token=token,
    )
    eval_id = ev["id"]
    print(f"  created {mode} eval {eval_id}")
    for i in range(120):
        time.sleep(5)
        row = req("GET", f"/v1/evaluations/{eval_id}", token=token)
        status = row["status"]
        if i % 6 == 0 or status in wait_for or status == "FAILED":
            print(f"  poll {i}: status={status} progress={row.get('probe_progress')}")
        if status in wait_for | {"FAILED"}:
            assert status in wait_for, f"evaluation failed: {row}"
            return row
    raise RuntimeError("timeout waiting for evaluation")


def check_report_body(body: dict, *, eval_id: str, version: int, mode: str, reviewed: bool):
    assert body["evaluation_id"] == eval_id
    assert body["version"] == version, body["version"]
    assert body["json_uri"] == f"s3://trustlens/reports/{eval_id}/v{version}/report.json"
    assert body["pdf_uri"] == f"s3://trustlens/reports/{eval_id}/v{version}/report.pdf", body[
        "pdf_uri"
    ]
    assert body["json_hash"].startswith("sha256:")
    report = body["report_json"]
    assert report["schema_version"] == "report_v1"
    assert report["report_version"] == version
    assert report["mode_disclosure"]["evaluation_mode"] == mode
    assert report["mode_disclosure"]["human_reviewed"] is reviewed
    assert report["score"]["score_type"] == "original_FRIES"
    assert "not ground truth" in report["score"]["note"].lower()
    assert len(report["probes"]) == 5
    assert all(probe["evidence_refs"] for probe in report["probes"])
    disclaimer = report["mode_disclosure"]["disclaimer"]
    if mode == "AI_AUTONOMOUS":
        assert "not human-reviewed" in disclaimer
    elif reviewed:
        assert "human-reviewed (accept/edit" in disclaimer
    print(
        f"  report ok: v{version} fries={body['fries_score']} "
        f"human_reviewed={reviewed} disclaimer={disclaimer!r}"
    )


def check_minio_artifacts(eval_id: str, versions: list[int]) -> None:
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:9000",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        region_name="us-east-1",
    )
    listed = s3.list_objects_v2(Bucket="trustlens", Prefix=f"reports/{eval_id}/")
    keys = sorted(obj["Key"] for obj in listed.get("Contents", []))
    print(f"  minio keys: {keys}")
    for v in versions:
        assert f"reports/{eval_id}/v{v}/report.json" in keys
        assert f"reports/{eval_id}/v{v}/report.pdf" in keys
    pdf = s3.get_object(Bucket="trustlens", Key=f"reports/{eval_id}/v1/report.pdf")["Body"].read()
    assert pdf.startswith(b"%PDF"), pdf[:16]
    js = s3.get_object(Bucket="trustlens", Key=f"reports/{eval_id}/v1/report.json")["Body"].read()
    assert json.loads(js)["schema_version"] == "report_v1"
    print(f"  minio ok: v1 pdf magic %PDF ({len(pdf)} bytes), v1 json parses")


def main() -> None:
    researcher = login("researcher@trustlens.local", "trustlens-researcher-dev")
    reviewer = login("reviewer@trustlens.local", "trustlens-reviewer-dev")
    print("login ok")

    # Unauthenticated -> 401
    err = req("GET", f"/v1/reports/{uuid.uuid4()}", expect_error=401)
    assert err["code"] in {"UNAUTHORIZED", "INVALID_TOKEN"}, err
    print("unauthenticated GET -> 401 ok")

    model = req("POST", "/v1/models/import-hf", {"repo_id": "distilbert-base-uncased"},
                token=researcher)
    print("model_id", model["id"])

    # --- Autonomous: FINALIZED -> auto-generate v1 -> POST generate v2 ---
    print("AUTONOMOUS:")
    auto = run_eval(researcher, model["id"], "AI_AUTONOMOUS", {"FINALIZED"})
    auto_id = auto["id"]
    body = req("GET", f"/v1/reports/{auto_id}", token=researcher)
    check_report_body(body, eval_id=auto_id, version=1, mode="AI_AUTONOMOUS", reviewed=False)
    again = req("GET", f"/v1/reports/{auto_id}", token=researcher)
    assert again["version"] == 1, "repeat GET must not regenerate"
    print("  repeat GET stays v1 ok")
    regen = req("POST", f"/v1/reports/{auto_id}/generate", token=researcher)
    check_report_body(regen, eval_id=auto_id, version=2, mode="AI_AUTONOMOUS", reviewed=False)
    check_minio_artifacts(auto_id, versions=[1, 2])

    # --- Assisted: 409 before finalize -> review -> finalize -> report ---
    print("ASSISTED:")
    assisted = run_eval(researcher, model["id"], "AI_ASSISTED", {"AWAITING_REVIEW"})
    assisted_id = assisted["id"]
    conflict = req("GET", f"/v1/reports/{assisted_id}", token=researcher, expect_error=409)
    assert conflict["code"] == "NOT_FINALIZED", conflict
    assert conflict["details"]["status"] == "AWAITING_REVIEW"
    print("  non-finalized GET -> 409 NOT_FINALIZED ok")
    req("POST", f"/v1/evaluations/{assisted_id}/human-review", {"accept_all": True},
        token=reviewer)
    req("POST", f"/v1/evaluations/{assisted_id}/finalize", token=reviewer)
    print("  reviewed + finalized")
    body = req("GET", f"/v1/reports/{assisted_id}", token=researcher)
    check_report_body(body, eval_id=assisted_id, version=1, mode="AI_ASSISTED", reviewed=True)
    check_minio_artifacts(assisted_id, versions=[1])

    print("PHASE 19 LIVE VERIFY: ALL OK")


if __name__ == "__main__":
    main()
