"""In-memory EvidenceStore / ReportStore stand-ins for tests (no MinIO)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.reports.store import ReportStoreError
from app.schemas.evidence import EvidenceRef
from app.storage.evidence_store import EvidenceStoreError, format_sha256, hashes_equal


def patch_evaluated_robustness(monkeypatch: object) -> None:
    """Make RobustnessProbe produce EVALUATED metrics without torch/Hub.

    Default pipeline models have no text-classification metadata, so robustness
    is NOT_APPLICABLE and Autonomous FRIES is withheld. Suites that still need
    a complete five-aspect FRIES (reports, leaderboard, review) opt into this.
    """
    from app.probes.robustness_nlp import RobustnessRunResult

    monkeypatch.setattr(  # type: ignore[union-attr]
        "app.probes.robustness._is_text_classification",
        lambda _meta: True,
    )
    monkeypatch.setattr(  # type: ignore[union-attr]
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello", "label": 0}] * 16,
    )

    def _run(self, **kwargs):  # noqa: ANN001, ANN003
        return RobustnessRunResult(
            clean_accuracy=0.9,
            robust_accuracy=0.8,
            attack_success_rate=0.1,
            n_samples=16,
            n_evaluated=16,
        )

    monkeypatch.setattr(  # type: ignore[union-attr]
        "app.probes.robustness.TransformersCharSwapRunner.run",
        _run,
    )


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
