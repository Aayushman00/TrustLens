"""Behavioural safety run: dataset -> imported model -> evaluate_behavior.

Kept out of safety.py so the card-disclosure probe stays metadata-only and
this inference path reads like fairness.py's v2 path it mirrors (fetch,
hash-verify, map labels, load the pinned model, verify the label snapshot,
predict, refuse a constant predictor).
"""
from __future__ import annotations

import csv
from dataclasses import asdict
from typing import Any

from app.datasets.user_dataset import UserDatasetError, _decode, _is_missing
from app.db.enums import ProbeEvaluationStatus
from app.db.repositories.dataset_content import DatasetContentRepository
from app.inference.base import InferenceBackend, InferenceConfig, TaskType
from app.inference.errors import InferenceError
from app.inference.model_snapshot_check import verify_loaded_model_matches_snapshot
from app.probes.base import ProbeContext
from app.probes.prediction_gate import FLAG_CONSTANT_PREDICTOR, prediction_collapse
from app.probes.safety_behavior import evaluate_behavior
from app.schemas.evaluation_contract_v2 import EvaluationContractV2, SafetyContractV2
from app.storage.evidence_store import EvidenceStoreError, format_sha256, hashes_equal


def _not_run(status: ProbeEvaluationStatus, reason: str, flags: list[str]) -> dict[str, Any]:
    return {"status": status.value, "status_reason": reason, "flags": flags}


def _load_rows(data: bytes, sc: SafetyContractV2) -> list[dict[str, Any]]:
    encoding = {e.dataset_value: e.model_label_index for e in sc.label_mapping}
    reader = csv.DictReader(_decode(data))
    for col in (sc.text_column, sc.target_column, sc.severe_column):
        if col not in (reader.fieldnames or []):
            raise UserDatasetError(f"column {col!r} not found in dataset")
    rows = []
    for row in reader:
        target, text, severe = row.get(sc.target_column), row.get(sc.text_column), row.get(sc.severe_column)
        if _is_missing(target) or _is_missing(severe) or not (text or "").strip():
            continue
        if target.strip() not in encoding or severe.strip() not in ("0", "1"):
            continue
        rows.append({"text": text, "label": encoding[target.strip()], "severe": int(severe.strip())})
    return rows


def run_behavioral_safety(
    ctx: ProbeContext, contract: EvaluationContractV2 | None, backend: InferenceBackend
) -> dict[str, Any]:
    """Return the ``behavior`` evidence dict; never raises for data/model problems."""
    sc = contract.safety if contract is not None else None
    if sc is None:
        return _not_run(
            ProbeEvaluationStatus.NOT_APPLICABLE,
            "behavioural safety not configured — only card disclosure was assessed",
            ["behavioral_safety_not_tested"],
        )
    if ctx.dataset_content_store is None or ctx.session is None:
        return _not_run(ProbeEvaluationStatus.FAILED, "dataset content storage unavailable", ["dataset_store_unavailable"])
    content = DatasetContentRepository(ctx.session).get_by_id(sc.dataset_content_id)
    if content is None:
        return _not_run(ProbeEvaluationStatus.FAILED, f"dataset content {sc.dataset_content_id} not found", ["dataset_fetch_failed"])
    try:
        data = ctx.dataset_content_store.get(content.storage_uri)
    except EvidenceStoreError as exc:
        return _not_run(ProbeEvaluationStatus.FAILED, str(exc), ["dataset_fetch_failed"])
    if not hashes_equal(format_sha256(data), content.content_hash):
        return _not_run(ProbeEvaluationStatus.FAILED, "dataset content hash mismatch", ["dataset_hash_mismatch"])
    try:
        rows = _load_rows(data, sc)
    except UserDatasetError as exc:
        return _not_run(ProbeEvaluationStatus.FAILED, str(exc), ["dataset_load_failed"])

    provenance = {
        "dataset_content_id": str(sc.dataset_content_id),
        "dataset_content_hash": content.content_hash,
        "severe_column": sc.severe_column,
        "positive_label_index": sc.positive_label_index,
        "min_severe_n": sc.min_severe_n,
        "n_evaluated": len(rows),
        "model_ref": contract.model_ref,
        "model_revision": contract.model_revision,
    }
    try:
        loaded = backend.load(
            contract.model_ref,
            revision=contract.model_revision,
            config=InferenceConfig(
                task_type=TaskType.BINARY_CLASSIFICATION,
                multilabel_positive_index=sc.multilabel_target_index,
            ),
        )
        verify_loaded_model_matches_snapshot(loaded, contract.model_label_snapshot)
        y_pred = [int(p.y_hat) for p in backend.predict_batch([r["text"] for r in rows]).predictions]
    except InferenceError as exc:
        return {**provenance, **_not_run(ProbeEvaluationStatus.FAILED, exc.message, ["predictor_failed"])}
    finally:
        backend.close()
    if len(y_pred) != len(rows):
        return {**provenance, **_not_run(ProbeEvaluationStatus.FAILED, "prediction count mismatch", ["predictor_failed"])}

    collapsed, majority, share = prediction_collapse(y_pred)
    if collapsed:
        return {
            **provenance,
            "majority_class_share": round(share, 6),
            **_not_run(
                ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
                f"model predicts class {majority} for {share:.1%} of rows",
                [FLAG_CONSTANT_PREDICTOR],
            ),
        }
    result = evaluate_behavior(
        [r["label"] for r in rows],
        y_pred,
        [r["severe"] for r in rows],
        positive=sc.positive_label_index,
        min_severe_n=sc.min_severe_n,
    )
    out = asdict(result)
    out["status"] = result.status.value
    return {**provenance, **out}
