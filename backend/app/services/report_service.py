"""Report orchestration (Phase 19, ADR 0009): guards → build → render → store.

- JSON is canonical; the PDF is a projection of the same document.
- Versioning is append-only: every generation inserts a new ``reports`` row and
  writes new MinIO keys ``reports/{evaluation_id}/v{n}/report.json`` (+ ``.pdf``);
  existing artifacts are never rewritten.
- GET returns the latest stored JSON read back from MinIO (not rebuilt), so the
  served report is exactly the persisted artifact.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import AppError, ConflictError, NotFoundError
from app.core.config import get_settings
from app.db.enums import EvaluationStatus
from app.db.models import Evaluation, Report
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_event import EVENT_REPORT_GENERATED, EvaluationEventRepository
from app.db.repositories.report import ReportRepository
from app.reports.builder import build_report_json
from app.reports.render import render_html, render_pdf
from app.reports.store import ReportStore, ReportStoreError, get_report_store
from app.schemas.modes import ModeDisclosure
from app.schemas.reports import ReportRead
from app.storage.evidence_store import format_sha256

JSON_FILENAME = "report.json"
PDF_FILENAME = "report.pdf"


class ReportService:
    def __init__(self, session: Session, store: ReportStore | None = None) -> None:
        self._session = session
        self._store = store if store is not None else get_report_store(get_settings())
        self._evals = EvaluationRepository(session)
        self._reports = ReportRepository(session)

    # -- guards --------------------------------------------------------------

    def _get_finalized_evaluation(self, evaluation_id: uuid.UUID) -> Evaluation:
        evaluation = self._evals.get_by_id(evaluation_id)
        if evaluation is None:
            raise NotFoundError(
                "Evaluation not found",
                details={"evaluation_id": str(evaluation_id)},
            )
        if evaluation.status != EvaluationStatus.FINALIZED:
            raise AppError(
                "NOT_FINALIZED",
                "Reports are available only after the evaluation reaches FINALIZED.",
                status_code=409,
                details={
                    "evaluation_id": str(evaluation.id),
                    "status": evaluation.status.value,
                    "evaluation_mode": evaluation.evaluation_mode.value,
                },
            )
        # Phase 5: a FINALIZED evaluation with no final_scores row (FRIES
        # withheld — required O/S/D incomplete) still gets a full
        # evidentiary report; build_report_json produces an explicit
        # withheld score section rather than fabricating one. No 409 here
        # anymore for that case — only "not finalized yet" blocks.
        return evaluation

    def _require_store(self) -> ReportStore:
        if self._store is None:
            raise AppError(
                "STORAGE_UNAVAILABLE",
                "Report storage (S3/MinIO) is not configured",
                status_code=503,
            )
        return self._store

    # -- public API ------------------------------------------------------------

    def get_report(self, evaluation_id: uuid.UUID) -> ReportRead:
        """Latest report for a finalized evaluation; auto-generates v1 if none."""
        evaluation = self._get_finalized_evaluation(evaluation_id)
        # Serializes with any concurrent get_report/generate for the SAME
        # evaluation so "read latest -> compute next version -> insert" is
        # never interleaved with another transaction doing the same thing
        # (audit P1-6). Held for the rest of this request's transaction.
        self._evals.lock_for_report_generation(evaluation.id)
        latest = self._reports.latest_for_evaluation(evaluation.id)
        if latest is None:
            return self._generate(evaluation, version=1)
        return self._read_existing(latest)

    def generate(self, evaluation_id: uuid.UUID) -> ReportRead:
        """Force a new report version (append-only: latest+1, new MinIO keys)."""
        evaluation = self._get_finalized_evaluation(evaluation_id)
        self._evals.lock_for_report_generation(evaluation.id)
        latest = self._reports.latest_for_evaluation(evaluation.id)
        next_version = 1 if latest is None else latest.version + 1
        return self._generate(evaluation, version=next_version)

    # -- internals ---------------------------------------------------------------

    def _generate(self, evaluation: Evaluation, *, version: int) -> ReportRead:
        store = self._require_store()
        report_json = build_report_json(self._session, evaluation, report_version=version)
        json_bytes = json.dumps(
            report_json, ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8")

        pdf_uri: str | None = None
        pdf_hash: str | None = None
        try:
            json_uri, json_hash = store.put_report(
                evaluation_id=evaluation.id,
                version=version,
                data=json_bytes,
                content_type="application/json",
                filename=JSON_FILENAME,
            )
            # PDF is a projection of the stored JSON; None (disabled/unavailable)
            # degrades the report to JSON-only with pdf_uri=null.
            pdf_bytes = render_pdf(render_html(report_json))
            if pdf_bytes is not None:
                pdf_uri, pdf_hash = store.put_report(
                    evaluation_id=evaluation.id,
                    version=version,
                    data=pdf_bytes,
                    content_type="application/pdf",
                    filename=PDF_FILENAME,
                )
        except ReportStoreError as exc:
            raise AppError(
                "STORAGE_UNAVAILABLE",
                "Failed to store report artifacts",
                status_code=503,
                details={"evaluation_id": str(evaluation.id), "error": str(exc)},
            ) from exc

        try:
            # SAVEPOINT-scoped: on a unique-constraint violation only this
            # nested transaction rolls back, leaving the outer request
            # transaction (and this session) usable for the ConflictError
            # response — never a raw 500, and never a fabricated
            # report_generated event for this failed attempt.
            with self._session.begin_nested():
                row = self._reports.create(
                    evaluation_id=evaluation.id,
                    json_uri=json_uri,
                    pdf_uri=pdf_uri,
                    version=version,
                )
        except IntegrityError as exc:
            # Final invariant (uq_reports_evaluation_id_version) — should
            # never actually trigger given the lock in get_report/generate,
            # but the constraint must win over application logic no matter
            # what.
            raise ConflictError(
                "A report with this version already exists for this evaluation "
                "— retry the request.",
                details={"evaluation_id": str(evaluation.id), "version": version},
            ) from exc
        # A real, legitimate fact each time — explicit regenerate endpoint
        # supports unlimited versions by design (report_service.py docstring).
        EvaluationEventRepository(self._session).create(
            evaluation_id=evaluation.id,
            event_type=EVENT_REPORT_GENERATED,
            detail={"version": version},
        )
        return self._to_read(row, report_json, json_hash=json_hash, pdf_hash=pdf_hash)

    def _read_existing(self, row: Report) -> ReportRead:
        store = self._require_store()
        try:
            data = store.get_bytes(key=store.key_from_uri(row.json_uri or ""))
        except ReportStoreError as exc:
            raise AppError(
                "STORAGE_UNAVAILABLE",
                "Failed to read the stored report artifact",
                status_code=503,
                details={"json_uri": row.json_uri, "error": str(exc)},
            ) from exc
        report_json = json.loads(data)
        # pdf_hash is not persisted in the DB (it lives in S3 object metadata);
        # re-reads return it as null while fresh generations include it.
        return self._to_read(
            row, report_json, json_hash=format_sha256(data), pdf_hash=None
        )

    @staticmethod
    def _to_read(
        row: Report,
        report_json: dict[str, Any],
        *,
        json_hash: str,
        pdf_hash: str | None,
    ) -> ReportRead:
        return ReportRead(
            evaluation_id=row.evaluation_id,
            version=row.version,
            json_uri=row.json_uri or "",
            pdf_uri=row.pdf_uri,
            json_hash=json_hash,
            pdf_hash=pdf_hash,
            fries_score=report_json["score"]["fries_score"],
            mode_disclosure=ModeDisclosure.model_validate(report_json["mode_disclosure"]),
            generated_at=report_json["generated_at"],
            report_json=report_json,
            methodology_version=report_json.get("methodology_version"),
        )
