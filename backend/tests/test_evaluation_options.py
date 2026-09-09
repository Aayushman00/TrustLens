"""GET /v1/models/{id}/evaluation-options — read-only registry reflection (UI)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

_HATEXPLAIN_MODEL = "Hate-speech-CNERG/bert-base-uncased-hatexplain"
_HATEXPLAIN_REV = "e487c81b768c7532bf474bd5e486dedea4cf3848"
_AG_NEWS_MODEL = "textattack/bert-base-uncased-ag-news"
_AG_NEWS_REV = "fe417ad660b1657142f66353a184dc0c7e6d2e48"


def _create_model(api_client: TestClient, headers: dict[str, str], *, hf_repo_id: str, revision: str | None) -> int:
    body = {"hf_repo_id": hf_repo_id}
    if revision is not None:
        body["revision"] = revision
    resp = api_client.post("/v1/models", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_hatexplain_pin_exposes_fairness_only_never_robustness(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    model_id = _create_model(
        api_client,
        auth_headers,
        hf_repo_id=_HATEXPLAIN_MODEL,
        revision=_HATEXPLAIN_REV,
    )
    resp = api_client.get(f"/v1/models/{model_id}/evaluation-options", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["fairness"]) == 1
    assert body["fairness"][0]["pairing_id"] == "hatexplain_bert_v1"
    # Critical: HateXplain must never appear as a Robustness contract.
    assert body["robustness"] == []
    assert body["documentation_only_available"] is True
    assert body["proxy_lr_available"] is True


def test_ag_news_pin_exposes_robustness(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    model_id = _create_model(
        api_client,
        auth_headers,
        hf_repo_id=_AG_NEWS_MODEL,
        revision=_AG_NEWS_REV,
    )
    resp = api_client.get(f"/v1/models/{model_id}/evaluation-options", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fairness"] == []
    assert len(body["robustness"]) == 1
    assert body["robustness"][0]["dataset_key"] == "ag_news_robustness"


def test_unmatched_model_has_empty_contract_lists_no_fabrication(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    model_id = _create_model(
        api_client,
        auth_headers,
        hf_repo_id=f"org/unmatched-{uuid.uuid4().hex[:8]}",
        revision="0" * 40,
    )
    resp = api_client.get(f"/v1/models/{model_id}/evaluation-options", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fairness"] == []
    assert body["robustness"] == []
    assert body["documentation_only_available"] is True


def test_proxy_lr_option_always_visible(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Single-user local instance — no admin-only visibility gate."""
    model_id = _create_model(
        api_client,
        auth_headers,
        hf_repo_id=f"org/proxy-visibility-{uuid.uuid4().hex[:8]}",
        revision=None,
    )
    resp = api_client.get(f"/v1/models/{model_id}/evaluation-options", headers=auth_headers)
    assert resp.json()["proxy_lr_available"] is True
