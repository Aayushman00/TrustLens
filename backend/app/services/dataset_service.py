"""Dataset service — upload/list/read/group-discovery for user-defined local
Fairness datasets. Single-user local instance: no ownership concept."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.api.errors import NotFoundError, ValidationAppError
from app.datasets.user_dataset import (
    UserDatasetError,
    count_rows,
    discover_group_values,
    sniff_columns,
)
from app.db.models import UserDataset
from app.db.repositories.user_dataset import UserDatasetRepository
from app.schemas.datasets import GroupDiscoveryRead, ObservedGroup, UserDatasetColumn
from app.storage.evidence_store import DatasetStore

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_UPLOAD_ROWS = 50_000


class DatasetService:
    def __init__(self, session: Session, *, dataset_store: DatasetStore | None) -> None:
        self._session = session
        self._repo = UserDatasetRepository(session)
        self._store = dataset_store

    def upload(self, *, filename: str, data: bytes) -> UserDataset:
        if self._store is None:
            raise ValidationAppError(
                "local dataset storage is not configured on this TrustLens instance"
            )
        if not filename.lower().endswith(".csv"):
            raise ValidationAppError(
                "only .csv files are supported in this release",
                details={"filename": filename},
            )
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValidationAppError(
                f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
                details={"size_bytes": len(data), "limit_bytes": MAX_UPLOAD_BYTES},
            )
        try:
            columns = sniff_columns(data)
            row_count = count_rows(data)
        except UserDatasetError as exc:
            raise ValidationAppError(str(exc), details={"filename": filename}) from exc
        if row_count > MAX_UPLOAD_ROWS:
            raise ValidationAppError(
                f"file exceeds the {MAX_UPLOAD_ROWS} row limit",
                details={"row_count": row_count, "limit_rows": MAX_UPLOAD_ROWS},
            )

        dataset_id = uuid.uuid4()
        storage_uri, content_hash = self._store.put_dataset(
            data=data,
            dataset_id=dataset_id,
            filename=filename,
        )
        row = self._repo.create(
            id=dataset_id,
            filename=filename,
            format="csv",
            content_hash=content_hash,
            row_count=row_count,
            size_bytes=len(data),
            columns=columns,
            storage_uri=storage_uri,
        )
        return row

    def list_all(self) -> list[UserDataset]:
        return self._repo.list_all()

    def get_by_id(self, dataset_id: uuid.UUID) -> UserDataset:
        row = self._repo.get_by_id(dataset_id)
        if row is None:
            raise NotFoundError(
                f"Dataset {dataset_id} not found",
                details={"dataset_id": str(dataset_id)},
            )
        return row

    def discover_groups(
        self,
        dataset_id: uuid.UUID,
        *,
        group_column: str,
    ) -> GroupDiscoveryRead:
        row = self.get_by_id(dataset_id)
        if self._store is None:
            raise ValidationAppError(
                "local dataset storage is not configured on this TrustLens instance"
            )
        data = self._store.get_dataset(storage_uri=row.storage_uri)
        try:
            observed, missing_summary = discover_group_values(data, group_column=group_column)
        except UserDatasetError as exc:
            raise ValidationAppError(str(exc), details={"group_column": group_column}) from exc
        return GroupDiscoveryRead(
            group_column=group_column,
            total_rows=row.row_count,
            observed_groups=[ObservedGroup(**g) for g in observed],
            missing_count=missing_summary["missing_count"],
            missing_reasons=missing_summary["missing_reasons"],
        )

    def delete(self, dataset_id: uuid.UUID) -> None:
        row = self.get_by_id(dataset_id)
        if self._store is not None:
            try:
                self._store.delete_dataset(storage_uri=row.storage_uri)
            except Exception:  # noqa: BLE001 - best-effort; DB row removal still proceeds
                pass
        self._repo.delete(row)


__all__ = ["DatasetService", "MAX_UPLOAD_BYTES", "MAX_UPLOAD_ROWS", "UserDatasetColumn"]
