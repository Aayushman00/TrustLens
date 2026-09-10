"""In-memory EvidenceStore / ReportStore stand-ins for tests (no MinIO)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.inference.base import (
    BatchPrediction,
    DeviceInfo,
    InferenceConfig,
    InferenceMetadata,
    LoadedModelInfo,
    PredictionRecord,
)
from app.inference.errors import InferenceError
from app.reports.store import ReportStoreError
from app.schemas.evidence import EvidenceRef
from app.storage.evidence_store import (
    EvidenceStoreError,
    format_sha256,
    hashes_equal,
    sanitize_filename,
)


def patch_evaluated_robustness(monkeypatch: object) -> None:
    """Make RobustnessProbe produce EVALUATED metrics without torch/Hub.

    Default pipeline evaluations carry no EvaluationContractV2.robustness, so
    robustness is NOT_APPLICABLE and Autonomous FRIES is withheld. Suites
    that still need a complete five-aspect FRIES (reports, leaderboard,
    review) opt into this synthetic model-faithful evidence — mirrors
    ``patch_evaluated_fairness``'s ``.run``-level patch, bypassing contract
    dispatch entirely rather than depending on internal V2 plumbing.
    """
    import uuid

    from app.db.enums import FriesDimension, ProbeEvaluationStatus
    from app.probes.base import ProbeOutput
    from app.schemas.evidence import EvidenceRef

    def _run(self, ctx):  # noqa: ANN001
        ref = EvidenceRef(
            evidence_id=str(uuid.uuid4()),
            uri="s3://trustlens/test/robustness.json",
            hash="sha256:" + "0" * 64,
            content_type="application/json",
            probe_name="robustness",
        )
        return ProbeOutput(
            dimension=FriesDimension.ROBUSTNESS,
            metric_values={
                "clean_accuracy": 0.9,
                "robust_accuracy": 0.8,
                "attack_success_rate": 0.1,
                "n_evaluated": 120,
                "probe_status": ProbeEvaluationStatus.EVALUATED.value,
            },
            confidence=0.85,
            evidence_refs=[ref],
            flags=["evaluated_robustness_test_fixture"],
            status=ProbeEvaluationStatus.EVALUATED,
        )

    monkeypatch.setattr("app.probes.robustness.RobustnessProbe.run", _run)  # type: ignore[union-attr]


def patch_evaluated_fairness(monkeypatch: object) -> None:
    """Make FairnessProbe produce EVALUATED disparity metrics for FRIES journeys.

    Default pipeline models use the Adult proxy path (``PROXY``), which correctly
    abstains from O/S/D. Integration suites that assert a complete five-aspect
    FRIES opt into synthetic model-faithful fairness evidence.
    """
    import uuid

    from app.db.enums import FriesDimension, ProbeEvaluationStatus
    from app.probes.base import ProbeOutput
    from app.schemas.evidence import EvidenceRef

    def _run(self, ctx):  # noqa: ANN001
        ref = EvidenceRef(
            evidence_id=str(uuid.uuid4()),
            uri="s3://trustlens/test/fairness.json",
            hash="sha256:" + "0" * 64,
            content_type="application/json",
            probe_name="fairness",
        )
        return ProbeOutput(
            dimension=FriesDimension.FAIRNESS,
            metric_values={
                "demographic_parity_difference": 0.08,
                "equalized_odds_difference": 0.05,
                "min_group_n": 30,
                "min_group_n_observed": 45,
                "probe_status": ProbeEvaluationStatus.EVALUATED.value,
                "fairness_mode": "model_faithful",
            },
            confidence=0.85,
            evidence_refs=[ref],
            flags=["model_faithful"],
            status=ProbeEvaluationStatus.EVALUATED,
        )

    monkeypatch.setattr("app.probes.fairness.FairnessProbe.run", _run)  # type: ignore[union-attr]


class FakeInferenceBackend:
    """Deterministic InferenceBackend for unit tests (no Transformers/Hub)."""

    def __init__(
        self,
        *,
        predictions: list[int | float] | None = None,
        load_error: InferenceError | None = None,
        predict_error: InferenceError | None = None,
        num_labels: int = 2,
    ) -> None:
        self.predictions = list(predictions or [0, 1, 0, 1])
        self.load_error = load_error
        self.predict_error = predict_error
        self.num_labels = num_labels
        self.load_calls: list[dict[str, Any]] = []
        self.predict_calls: list[list[str]] = []
        self._config = InferenceConfig()
        self._model_ref: str | None = None
        self._revision: str | None = None
        self.is_loaded = False

    def load(
        self,
        model_ref: str,
        *,
        revision: str | None = None,
        config: InferenceConfig | None = None,
        hf_token: str | None = None,
    ) -> LoadedModelInfo:
        if self.load_error is not None:
            raise self.load_error
        self.load_calls.append(
            {
                "model_ref": model_ref,
                "revision": revision,
                "config": config,
                "hf_token": hf_token,
            }
        )
        self._model_ref = model_ref
        self._revision = revision
        self._config = config or InferenceConfig()
        self.is_loaded = True
        return LoadedModelInfo(num_labels=self.num_labels)

    def predict(self, inputs: list[str]) -> BatchPrediction:
        return self.predict_batch(inputs)

    def predict_batch(self, inputs: list[str]) -> BatchPrediction:
        if not self.is_loaded:
            raise InferenceError("NOT_LOADED", "model is not loaded")
        if self.predict_error is not None:
            raise self.predict_error
        self.predict_calls.append(list(inputs))
        preds: list[PredictionRecord] = []
        for i, _ in enumerate(inputs):
            value = self.predictions[i % len(self.predictions)]
            if isinstance(value, float):
                preds.append(PredictionRecord(y_hat=value))
            else:
                preds.append(PredictionRecord(y_hat=int(value)))
        meta = InferenceMetadata(
            model_ref=self._model_ref or "",
            revision=self._revision,
            task_type=self._config.task_type.value,
            device=self._config.device,
            device_name=None,
            dtype=None,
            batch_size=self._config.batch_size,
            backend="fake",
            num_labels=self.num_labels,
        )
        return BatchPrediction(predictions=preds, n_samples=len(preds), metadata=meta)

    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            device=self._config.device,
            device_type="cpu",
            device_name=None,
            dtype=None,
            batch_size=self._config.batch_size,
            backend="fake",
        )

    def close(self) -> None:
        self.is_loaded = False


class FakeEvidenceStore:
    """Minimal store matching EvidenceStore.put/get/verify for unit tests."""

    def __init__(self, bucket: str = "trustlens") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}
        self.puts: list[EvidenceRef] = []

    def put_artifact(
        self,
        *,
        data: bytes,
        content_type: str,
        probe_name: str,
        evaluation_id: uuid.UUID,
        metadata: dict[str, str] | None = None,
    ) -> EvidenceRef:
        evidence_id = str(uuid.uuid4())
        ext = ".json" if "json" in content_type.lower() else ".bin"
        key = f"evidence/{evaluation_id}/{evidence_id}{ext}"
        self.objects[key] = data
        ref = EvidenceRef(
            evidence_id=evidence_id,
            uri=f"s3://{self.bucket}/{key}",
            hash=format_sha256(data),
            content_type=content_type,
            probe_name=probe_name,
            created_at=datetime.now(UTC),
        )
        self.puts.append(ref)
        return ref

    def get_artifact(self, *, key: str) -> bytes:
        if key not in self.objects:
            raise EvidenceStoreError(f"missing key={key}")
        return self.objects[key]

    def verify_artifact(self, *, key: str, expected_hash: str) -> bool:
        return hashes_equal(format_sha256(self.get_artifact(key=key)), expected_hash)

    def key_from_uri(self, uri: str) -> str:
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix):
            raise EvidenceStoreError(f"bad uri={uri}")
        return uri[len(prefix) :]

    def verify_ref(self, ref: EvidenceRef) -> bool:
        return self.verify_artifact(key=self.key_from_uri(ref.uri), expected_hash=ref.hash)


class FakeDatasetStore:
    """Minimal store matching DatasetStore.put/get for unit tests (no MinIO)."""

    def __init__(self, bucket: str = "trustlens") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}

    def _key(self, *, dataset_id: uuid.UUID, filename: str) -> str:
        safe_filename = sanitize_filename(filename, default_stem="dataset")
        return f"datasets/{dataset_id}/{safe_filename}"

    def put_dataset(
        self,
        *,
        data: bytes,
        dataset_id: uuid.UUID,
        filename: str,
        content_type: str = "text/csv",
    ) -> tuple[str, str]:
        key = self._key(dataset_id=dataset_id, filename=filename)
        self.objects[key] = data
        return f"s3://{self.bucket}/{key}", format_sha256(data)

    def get_dataset(self, *, storage_uri: str) -> bytes:
        prefix = f"s3://{self.bucket}/"
        if not storage_uri.startswith(prefix):
            raise EvidenceStoreError(f"bad uri={storage_uri}")
        key = storage_uri[len(prefix) :]
        if key not in self.objects:
            raise EvidenceStoreError(f"missing key={key}")
        return self.objects[key]

    def delete_dataset(self, *, storage_uri: str) -> None:
        prefix = f"s3://{self.bucket}/"
        key = storage_uri[len(prefix) :] if storage_uri.startswith(prefix) else storage_uri
        self.objects.pop(key, None)


class FakeReportStore:
    """Minimal ReportStore matching put/get for report service tests.

    Enforces append-only semantics: putting an existing key raises, so tests
    catch any accidental report overwrite.
    """

    def __init__(self, bucket: str = "trustlens") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}

    @staticmethod
    def object_key(evaluation_id: uuid.UUID, version: int, filename: str) -> str:
        return f"reports/{evaluation_id}/v{version}/{filename}"

    def put_report(
        self,
        *,
        evaluation_id: uuid.UUID,
        version: int,
        data: bytes,
        content_type: str,
        filename: str,
    ) -> tuple[str, str]:
        key = self.object_key(evaluation_id, version, filename)
        if key in self.objects:
            raise ReportStoreError(f"append-only violation: key={key} already exists")
        self.objects[key] = bytes(data)
        return f"s3://{self.bucket}/{key}", format_sha256(data)

    def get_bytes(self, *, key: str) -> bytes:
        if key not in self.objects:
            raise ReportStoreError(f"missing key={key}")
        return self.objects[key]

    def key_from_uri(self, uri: str) -> str:
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix):
            raise ReportStoreError(f"bad uri={uri}")
        return uri[len(prefix) :]
