# FEATURE_ATTRIBUTION (SHAP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone SHAP-based feature-attribution feature (`POST /v1/attribution/runs`) that explains one text-classification prediction for one already-imported model, fully separate from the FRIES probe system.

**Architecture:** New backend package `app/attribution/` (schemas, errors, SHAP wrapper, orchestration service) + one new table `feature_attribution_results` + one new sync router `/v1/attribution/*`, reusing `LocalHFBackend`, `EvidenceStore`, `ModelRepository`, and the existing `AppError` machinery as-is. A new standalone frontend page is entered from `ModelDetailPage`, not from any evaluation/report screen.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, `shap`, `transformers`/`torch` (already-present `LocalHFBackend`), React + TypeScript (Vite), Pydantic v2.

**Spec:** `docs/superpowers/specs/2026-09-15-feature-attribution-shap-lime-design.md`

## Global Constraints

- Fully separate from the FRIES probe system — never touch `FriesDimension`, `ProbeRegistry`, `probe_results`, the confidence engine, or `dimension_scores`.
- v1 = text-classification models only, via the existing `LocalHFBackend`.
- v1 is **synchronous** (no Celery) — one short text, one forward pass, one SHAP call.
- v1 = SHAP only. `method: Literal["shap", "lime"]` stays open in the schema but `"lime"` is rejected at the API layer (422) — do not implement LIME.
- Every result always carries a fixed, non-conditional `limitations: list[str]` — no numeric "confidence" field on an attribution result.
- v1 constructs a fresh `LocalHFBackend()` per request, used and discarded within that request — no process-wide model cache, no cross-request reuse (`LocalHFBackend` is stateful and not thread-safe).
- Input text cap: 2000 characters, enforced server-side (422 `ValidationAppError` over the cap).
- New optional extra `trustlens-backend[attribution]` gates the `shap` dependency (and `torch`/`transformers`, self-contained) exactly like the existing `[robustness]` extra gates `LocalHFBackend`'s imports.
- New migration is `alembic/versions/014_add_feature_attribution_results.py`, `down_revision = "013_add_positive_label_index"` (current head).

---

### Task 1: `LocalHFBackend` read-only accessors

The SHAP wrapper (Task 3) needs the already-loaded raw `transformers` model/tokenizer/device to build a `transformers.pipeline` for `shap.Explainer`. `LocalHFBackend` currently only exposes `_model`/`_tokenizer`/`_device` as private attributes. Add three read-only properties — no change to `load`/`predict_batch`/`close` behavior.

**Files:**
- Modify: `backend/app/inference/local_hf.py:59-72` (add properties inside `LocalHFBackend`)
- Test: `backend/tests/test_inference_backend.py`

**Interfaces:**
- Produces: `LocalHFBackend.model -> Any` (the loaded `PreTrainedModel`, or `None` if not loaded), `LocalHFBackend.tokenizer -> Any`, `LocalHFBackend.device -> Any` (a `torch.device`, or `None` if not loaded).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_inference_backend.py — add at end of file
def test_local_hf_backend_exposes_model_tokenizer_device_after_load():
    from app.inference.local_hf import LocalHFBackend

    backend = LocalHFBackend()
    assert backend.model is None
    assert backend.tokenizer is None
    assert backend.device is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_inference_backend.py::test_local_hf_backend_exposes_model_tokenizer_device_after_load -v`
Expected: FAIL with `AttributeError: 'LocalHFBackend' object has no attribute 'model'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/inference/local_hf.py — inside class LocalHFBackend, after __init__ (line 71)
    @property
    def model(self) -> Any:
        return self._model

    @property
    def tokenizer(self) -> Any:
        return self._tokenizer

    @property
    def device(self) -> Any:
        return self._device
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_inference_backend.py::test_local_hf_backend_exposes_model_tokenizer_device_after_load -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/inference/local_hf.py backend/tests/test_inference_backend.py
git commit -m "feat(inference): expose read-only model/tokenizer/device on LocalHFBackend"
```

---

### Task 2: `app/attribution/` package — schemas + errors

**Files:**
- Create: `backend/app/attribution/__init__.py`
- Create: `backend/app/attribution/schemas.py`
- Create: `backend/app/attribution/errors.py`
- Test: `backend/tests/test_attribution_schemas.py`

**Interfaces:**
- Produces: `TokenAttribution(token: str, weight: float, position: int)`, `FeatureAttributionRequest(model_id: int, text: str, method: Literal["shap","lime"]="shap", modality: Literal["text"]="text", model_revision: str|None=None)`, `FeatureAttributionRead`, `FeatureAttributionList`, `UnsupportedModelTypeError`, `AttributionDependencyError`, `EvidenceStoreUnavailableError`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_attribution_schemas.py
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_request_rejects_empty_text():
    from app.attribution.schemas import FeatureAttributionRequest

    with pytest.raises(ValidationError):
        FeatureAttributionRequest(model_id=1, text="")


def test_request_rejects_text_over_2000_chars():
    from app.attribution.schemas import FeatureAttributionRequest

    with pytest.raises(ValidationError):
        FeatureAttributionRequest(model_id=1, text="a" * 2001)


def test_request_defaults_method_shap_modality_text():
    from app.attribution.schemas import FeatureAttributionRequest

    body = FeatureAttributionRequest(model_id=1, text="hello world")
    assert body.method == "shap"
    assert body.modality == "text"


def test_unsupported_model_type_error_is_422():
    from app.attribution.errors import UnsupportedModelTypeError

    exc = UnsupportedModelTypeError()
    assert exc.code == "UNSUPPORTED_MODEL_TYPE"
    assert exc.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_attribution_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.attribution'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/attribution/__init__.py
"""Standalone feature-attribution (SHAP/LIME) package.

Deliberately separate from the FRIES probe system (design doc
2026-09-15-feature-attribution-shap-lime-design.md) — never imports
ProbeContext/ProbeOutput/ProbeRegistry/run_all_probes/confidence.engine.
"""
```

```python
# backend/app/attribution/schemas.py
"""Feature-attribution request/response schemas (design doc 2026-09-15)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CursorPage
from app.schemas.evidence import EvidenceRef

TEXT_MAX_LENGTH = 2000


class TokenAttribution(BaseModel):
    token: str
    weight: float
    position: int


class FeatureAttributionRequest(BaseModel):
    model_id: int
    text: str = Field(..., min_length=1, max_length=TEXT_MAX_LENGTH)
    method: Literal["shap", "lime"] = "shap"
    modality: Literal["text"] = "text"
    model_revision: str | None = None


class FeatureAttributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: int
    evaluation_id: uuid.UUID | None = None
    method: str
    modality: str
    input_text: str
    predicted_label: str | None = None
    predicted_index: int | None = None
    predicted_score: float | None = None
    label_space: dict[str, Any] | None = None
    token_attributions: list[TokenAttribution] | None = None
    model_ref: str
    model_revision: str | None = None
    inference_metadata: dict[str, Any] | None = None
    methodology_version: str
    status: str
    status_reason: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at: datetime


class FeatureAttributionList(CursorPage):
    items: list[FeatureAttributionRead]
```

```python
# backend/app/attribution/errors.py
"""Attribution-specific AppError subclasses (design doc 2026-09-15)."""

from __future__ import annotations

from typing import Any

from app.api.errors import AppError


class UnsupportedModelTypeError(AppError):
    """Model loads but has no text-classification head."""

    def __init__(
        self,
        message: str = "model does not have a supported text-classification head",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("UNSUPPORTED_MODEL_TYPE", message, status_code=422, details=details)


class AttributionDependencyError(AppError):
    """``shap`` (or torch/transformers) is not installed."""

    def __init__(
        self,
        message: str = "shap is required — install trustlens-backend[attribution]",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            "ATTRIBUTION_DEPENDENCY_MISSING", message, status_code=503, details=details
        )


class EvidenceStoreUnavailableError(AppError):
    """S3/MinIO is not configured — attribution runs cannot be persisted."""

    def __init__(
        self,
        message: str = "evidence store is not configured (S3/MinIO)",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            "EVIDENCE_STORE_UNAVAILABLE", message, status_code=503, details=details
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_attribution_schemas.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/attribution/__init__.py backend/app/attribution/schemas.py backend/app/attribution/errors.py backend/tests/test_attribution_schemas.py
git commit -m "feat(attribution): add schemas and error types for feature-attribution package"
```

---

### Task 3: SHAP explainer wrapper (`shap_text.py`)

**Files:**
- Create: `backend/app/attribution/shap_text.py`
- Modify: `backend/pyproject.toml` (add `attribution` optional extra)
- Test: `backend/tests/test_shap_text.py`

**Interfaces:**
- Consumes: `LocalHFBackend.model/tokenizer/device` (Task 1), `app.attribution.schemas.TokenAttribution` (Task 2), `app.attribution.errors.AttributionDependencyError` (Task 2).
- Produces: `ShapExplainResult(token_attributions: list[TokenAttribution], raw: dict[str, Any])`, `explain(backend: LocalHFBackend, text: str, predicted_index: int) -> ShapExplainResult`.

This wrapper needs a real loaded HF model to run — it is exercised by a real-model integration test marked `integration` (this repo's existing marker for tests that hit live external services / require heavier setup; opt in with `TRUSTLENS_LIVE_TESTS=1`, per `pyproject.toml`'s `[tool.pytest.ini_options]`), using a tiny public text-classification model. `AttributionService`'s own unit tests (Task 6) inject a fake `explain_fn` instead of importing `shap` at all, so the fast test suite never needs `shap`/`torch` installed.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_shap_text.py
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("TRUSTLENS_LIVE_TESTS") != "1",
    reason="hits the HF Hub and requires torch/transformers/shap — opt in with TRUSTLENS_LIVE_TESTS=1",
)
def test_explain_returns_one_token_attribution_per_token():
    from app.attribution.shap_text import explain
    from app.inference.base import InferenceConfig, TaskType
    from app.inference.local_hf import LocalHFBackend

    backend = LocalHFBackend()
    backend.load(
        "hf-internal-testing/tiny-random-DistilBertForSequenceClassification",
        config=InferenceConfig(task_type=TaskType.MULTICLASS_CLASSIFICATION),
    )
    try:
        prediction = backend.predict_batch(["this is a short test sentence"])
        predicted_index = int(prediction.predictions[0].y_hat)

        result = explain(backend, "this is a short test sentence", predicted_index)

        assert len(result.token_attributions) > 0
        assert all(isinstance(t.weight, float) for t in result.token_attributions)
        assert "values" in result.raw
        assert "tokens" in result.raw
    finally:
        backend.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_shap_text.py -v`
Expected: SKIPPED by default (no `TRUSTLENS_LIVE_TESTS`); with `TRUSTLENS_LIVE_TESTS=1 pytest tests/test_shap_text.py -v` (and `pip install -e ".[attribution]"` first): FAIL with `ModuleNotFoundError: No module named 'app.attribution.shap_text'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/attribution/shap_text.py
"""SHAP explainer wrapper for HF text-classification (design doc 2026-09-15).

Runs against an ALREADY-LOADED LocalHFBackend — this module never calls
backend.load()/close() itself, matching AttributionService's per-request
"construct, use, discard" backend lifecycle (design doc §7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.attribution.errors import AttributionDependencyError
from app.attribution.schemas import TokenAttribution
from app.inference.local_hf import LocalHFBackend


@dataclass
class ShapExplainResult:
    token_attributions: list[TokenAttribution]
    raw: dict[str, Any]


def explain(backend: LocalHFBackend, text: str, predicted_index: int) -> ShapExplainResult:
    """Run a SHAP explainer for ``text`` against ``predicted_index``'s class."""
    try:
        import shap
        from transformers import pipeline
    except ImportError as exc:
        raise AttributionDependencyError(details={"cause": str(exc)}) from exc

    pipe = pipeline(
        "text-classification",
        model=backend.model,
        tokenizer=backend.tokenizer,
        device=backend.device,
        top_k=None,
        truncation=True,
    )
    explainer = shap.Explainer(pipe)
    shap_values = explainer([text])

    tokens = [str(t) for t in shap_values[0].data]
    values = shap_values[0].values  # shape (n_tokens, n_classes)
    class_weights = [
        float(row[predicted_index]) if predicted_index < len(row) else 0.0 for row in values
    ]
    token_attributions = [
        TokenAttribution(token=tok, weight=weight, position=i)
        for i, (tok, weight) in enumerate(zip(tokens, class_weights, strict=True))
    ]

    base_values = shap_values[0].base_values
    raw = {
        "tokens": tokens,
        "values": [[float(v) for v in row] for row in values],
        "base_values": (
            [float(v) for v in base_values]
            if hasattr(base_values, "__iter__")
            else float(base_values)
        ),
        "predicted_index": predicted_index,
    }
    return ShapExplainResult(token_attributions=token_attributions, raw=raw)
```

```toml
# backend/pyproject.toml — add alongside the existing [project.optional-dependencies] block
attribution = [
  # Self-contained: torch/transformers repeated here (not just relying on
  # [robustness]) so `pip install -e ".[attribution]"` alone is enough —
  # LocalHFBackend's own torch/transformers import happens lazily inside
  # app/inference/local_hf.py, same as the [robustness] extra.
  "shap>=0.46.0",
  "torch>=2.2.0",
  "transformers>=4.44.0",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pip install -e ".[attribution]" && TRUSTLENS_LIVE_TESTS=1 pytest tests/test_shap_text.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/attribution/shap_text.py backend/pyproject.toml backend/tests/test_shap_text.py
git commit -m "feat(attribution): add SHAP explainer wrapper for HF text-classification"
```

---

### Task 4: `feature_attribution_results` table + migration

**Files:**
- Modify: `backend/app/db/models.py` (append `FeatureAttributionResult` after `AttackFlag`, line 507)
- Create: `backend/alembic/versions/014_add_feature_attribution_results.py`
- Test: `backend/tests/test_models_fk.py`

**Interfaces:**
- Produces: `FeatureAttributionResult` ORM model — columns exactly as design doc §2 plus `modality` (design doc §8).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models_fk.py — add at end of file
def test_feature_attribution_result_requires_model_id(db_session, seeded_model):
    import uuid

    from app.db.models import FeatureAttributionResult

    row = FeatureAttributionResult(
        model_id=seeded_model.id,
        method="shap",
        modality="text",
        input_text="hello",
        input_hash="sha256:" + "a" * 64,
        model_ref=seeded_model.hf_repo_id,
        methodology_version="tl-attribution-v1.0",
        status="EVALUATED",
        evidence_refs=[],
    )
    db_session.add(row)
    db_session.flush()

    assert row.id is not None
    assert row.evaluation_id is None
    assert row.status == "EVALUATED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_models_fk.py::test_feature_attribution_result_requires_model_id -v`
Expected: FAIL with `ImportError: cannot import name 'FeatureAttributionResult'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/db/models.py — append after AttackFlag (after line 507)


class FeatureAttributionResult(Base):
    """Standalone SHAP/LIME feature-attribution result (design doc 2026-09-15).

    Deliberately separate from ProbeResult — never joined into
    dimension_scores, FriesDimension, or the confidence engine. One row =
    one (model, input_text, method) run; the full raw SHAP explanation goes
    to the evidence store, mirroring how every probe splits "metrics in DB"
    vs "full artifact in evidence store".
    """

    __tablename__ = "feature_attribution_results"
    __table_args__ = (Index("ix_feature_attribution_results_model_id", "model_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("models.id", ondelete="RESTRICT"), nullable=False
    )
    # No FK — see design doc §"Resolved: evaluation_id linkage". A report may
    # optionally surface attribution runs by evaluation_id in a later phase;
    # this table must never be joinable into FRIES scoring either way.
    evaluation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    modality: Mapped[str] = mapped_column(String(16), nullable=False, server_default="text")
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    predicted_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    predicted_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label_space: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    token_attributions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    model_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    inference_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    methodology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[Model] = relationship()
```

```python
# backend/alembic/versions/014_add_feature_attribution_results.py
"""Add feature_attribution_results table (SHAP/LIME feature attribution).

Revision ID: 014_add_feature_attribution_results
Revises: 013_add_positive_label_index
Create Date: 2026-09-15

Standalone table for the FEATURE_ATTRIBUTION (SHAP/LIME) feature — design
doc 2026-09-15-feature-attribution-shap-lime-design.md. Deliberately not
joined to probe_results/evaluations: evaluation_id is a nullable UUID with
NO foreign key, so this table can never be pulled into FRIES/O/S/D scoring.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_add_feature_attribution_results"
down_revision: str | None = "013_add_positive_label_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_attribution_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "model_id",
            sa.Integer(),
            sa.ForeignKey("models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=False, server_default="text"),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("predicted_label", sa.String(length=256), nullable=True),
        sa.Column("predicted_index", sa.Integer(), nullable=True),
        sa.Column("predicted_score", sa.Float(), nullable=True),
        sa.Column("label_space", postgresql.JSONB(), nullable=True),
        sa.Column("token_attributions", postgresql.JSONB(), nullable=True),
        sa.Column("model_ref", sa.String(length=256), nullable=False),
        sa.Column("model_revision", sa.String(length=128), nullable=True),
        sa.Column("inference_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column(
            "evidence_refs", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_feature_attribution_results_model_id",
        "feature_attribution_results",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feature_attribution_results_model_id", table_name="feature_attribution_results"
    )
    op.drop_table("feature_attribution_results")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && alembic upgrade head && pytest tests/test_models_fk.py::test_feature_attribution_result_requires_model_id -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/014_add_feature_attribution_results.py backend/tests/test_models_fk.py
git commit -m "feat(attribution): add feature_attribution_results table and migration"
```

---

### Task 5: `FeatureAttributionRepository`

**Files:**
- Create: `backend/app/db/repositories/feature_attribution.py`
- Test: `backend/tests/test_repositories.py`

**Interfaces:**
- Consumes: `FeatureAttributionResult` (Task 4).
- Produces: `FeatureAttributionRepository(session).create(**fields) -> FeatureAttributionResult`, `.get_by_id(id: uuid.UUID) -> FeatureAttributionResult | None`, `.list_by_model(model_id: int, *, limit=50, cursor=None) -> tuple[list[FeatureAttributionResult], str | None]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_repositories.py — add at end of file
def test_feature_attribution_repository_create_get_list(db_session, seeded_model):
    from app.db.repositories.feature_attribution import FeatureAttributionRepository

    repo = FeatureAttributionRepository(db_session)
    row = repo.create(
        model_id=seeded_model.id,
        method="shap",
        modality="text",
        input_text="hello",
        input_hash="sha256:" + "a" * 64,
        model_ref=seeded_model.hf_repo_id,
        methodology_version="tl-attribution-v1.0",
        status="EVALUATED",
        evidence_refs=[],
    )

    fetched = repo.get_by_id(row.id)
    assert fetched is not None
    assert fetched.input_text == "hello"

    rows, next_cursor = repo.list_by_model(seeded_model.id, limit=10)
    assert len(rows) == 1
    assert next_cursor is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_repositories.py::test_feature_attribution_repository_create_get_list -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.repositories.feature_attribution'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/db/repositories/feature_attribution.py
"""FeatureAttributionResult repository — create / get / list by model_id."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FeatureAttributionResult


class FeatureAttributionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, **fields: Any) -> FeatureAttributionResult:
        row = FeatureAttributionResult(**fields)
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, result_id: uuid.UUID) -> FeatureAttributionResult | None:
        return self._session.get(FeatureAttributionResult, result_id)

    def list_by_model(
        self, model_id: int, *, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[FeatureAttributionResult], str | None]:
        limit = max(1, min(limit, 200))
        stmt = (
            select(FeatureAttributionResult)
            .where(FeatureAttributionResult.model_id == model_id)
            .order_by(FeatureAttributionResult.id.asc())
        )
        if cursor:
            try:
                stmt = stmt.where(FeatureAttributionResult.id > uuid.UUID(cursor))
            except ValueError:
                pass
        stmt = stmt.limit(limit + 1)
        rows = list(self._session.scalars(stmt).all())
        next_cursor: str | None = None
        if len(rows) > limit:
            next_cursor = str(rows[limit - 1].id)
            rows = rows[:limit]
        return rows, next_cursor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_repositories.py::test_feature_attribution_repository_create_get_list -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories/feature_attribution.py backend/tests/test_repositories.py
git commit -m "feat(attribution): add FeatureAttributionRepository"
```

---

### Task 6: `AttributionService` orchestration

**Files:**
- Create: `backend/app/attribution/service.py`
- Test: `backend/tests/test_attribution_service.py`

**Interfaces:**
- Consumes: `FeatureAttributionRepository` (Task 5), `ModelRepository.get_by_id` (existing), `LocalHFBackend` (Task 1), `app.attribution.shap_text.explain`/`ShapExplainResult` (Task 3), `get_evidence_store`/`format_sha256` (existing), `FeatureAttributionRequest`/`FeatureAttributionRead`/`TokenAttribution` (Task 2), `UnsupportedModelTypeError`/`EvidenceStoreUnavailableError` (Task 2).
- Produces: `AttributionService(session, *, settings=None, backend_factory=LocalHFBackend, explain_fn=explain)`, `.create_run(body: FeatureAttributionRequest) -> FeatureAttributionRead`, `.get_run(id: uuid.UUID) -> FeatureAttributionRead`, `.list_runs(*, model_id: int, limit=50, cursor=None) -> FeatureAttributionList`.

Unit tests inject a fake `backend_factory` (returning a `FakeInferenceBackend`-shaped stub, extended with `model`/`tokenizer`/`device`/`close`) and a fake `explain_fn` — no `shap`/`torch` import happens in this test file.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_attribution_service.py
from __future__ import annotations

import uuid

import pytest

from app.attribution.errors import EvidenceStoreUnavailableError, UnsupportedModelTypeError
from app.attribution.schemas import FeatureAttributionRequest, TokenAttribution
from app.attribution.shap_text import ShapExplainResult
from app.inference.base import InferenceConfig, LoadedModelInfo, PredictionRecord
from app.inference.base import BatchPrediction, InferenceMetadata
from app.inference.errors import InferenceError


class _StubBackend:
    """Minimal stand-in for LocalHFBackend — no torch/transformers import."""

    def __init__(self, *, unsupported: bool = False) -> None:
        self._unsupported = unsupported
        self.model = object()
        self.tokenizer = object()
        self.device = "cpu"
        self.closed = False

    def load(self, model_ref, *, revision=None, config=None, hf_token=None):
        if self._unsupported:
            raise InferenceError("UNSUPPORTED_TASK", "model has no sequence-classification head")
        return LoadedModelInfo(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"})

    def predict_batch(self, inputs):
        return BatchPrediction(
            predictions=[PredictionRecord(y_hat=1, probabilities=[0.1, 0.9])],
            n_samples=1,
            metadata=InferenceMetadata(
                model_ref="org/model",
                revision=None,
                task_type="multiclass_classification",
                device="cpu",
                device_name=None,
                dtype="float32",
                batch_size=8,
                backend="local_hf",
            ),
        )

    def close(self):
        self.closed = True


def _fake_explain(backend, text, predicted_index):
    return ShapExplainResult(
        token_attributions=[
            TokenAttribution(token=tok, weight=float(i), position=i)
            for i, tok in enumerate(text.split())
        ],
        raw={"tokens": text.split(), "values": [], "base_values": 0.0},
    )


@pytest.fixture
def fake_evidence_store(fake_s3_client):
    from app.storage.evidence_store import EvidenceStore

    return EvidenceStore(fake_s3_client, "test-bucket")


def test_create_run_persists_row_and_evidence(db_session, seeded_model, fake_evidence_store, monkeypatch):
    from app.attribution.service import AttributionService
    import app.attribution.service as service_module

    monkeypatch.setattr(service_module, "get_evidence_store", lambda settings: fake_evidence_store)

    service = AttributionService(
        db_session,
        backend_factory=lambda: _StubBackend(),
        explain_fn=_fake_explain,
    )
    body = FeatureAttributionRequest(model_id=seeded_model.id, text="hello world")

    result = service.create_run(body)

    assert result.status == "EVALUATED"
    assert result.predicted_index == 1
    assert result.predicted_label == "POSITIVE"
    assert len(result.token_attributions) == 2
    assert len(result.evidence_refs) == 1
    assert len(result.limitations) == 3


def test_create_run_unknown_model_raises_not_found(db_session, fake_evidence_store, monkeypatch):
    from app.api.errors import NotFoundError
    from app.attribution.service import AttributionService
    import app.attribution.service as service_module

    monkeypatch.setattr(service_module, "get_evidence_store", lambda settings: fake_evidence_store)
    service = AttributionService(
        db_session, backend_factory=lambda: _StubBackend(), explain_fn=_fake_explain
    )
    body = FeatureAttributionRequest(model_id=999999, text="hello")

    with pytest.raises(NotFoundError):
        service.create_run(body)


def test_create_run_lime_rejected(db_session, seeded_model, fake_evidence_store, monkeypatch):
    from app.api.errors import ValidationAppError
    from app.attribution.service import AttributionService
    import app.attribution.service as service_module

    monkeypatch.setattr(service_module, "get_evidence_store", lambda settings: fake_evidence_store)
    service = AttributionService(
        db_session, backend_factory=lambda: _StubBackend(), explain_fn=_fake_explain
    )
    body = FeatureAttributionRequest(model_id=seeded_model.id, text="hello", method="lime")

    with pytest.raises(ValidationAppError):
        service.create_run(body)


def test_create_run_unsupported_model_type(db_session, seeded_model, fake_evidence_store, monkeypatch):
    from app.attribution.service import AttributionService
    import app.attribution.service as service_module

    monkeypatch.setattr(service_module, "get_evidence_store", lambda settings: fake_evidence_store)
    service = AttributionService(
        db_session,
        backend_factory=lambda: _StubBackend(unsupported=True),
        explain_fn=_fake_explain,
    )
    body = FeatureAttributionRequest(model_id=seeded_model.id, text="hello")

    with pytest.raises(UnsupportedModelTypeError):
        service.create_run(body)


def test_create_run_no_evidence_store_configured(db_session, seeded_model, monkeypatch):
    from app.attribution.service import AttributionService
    import app.attribution.service as service_module

    monkeypatch.setattr(service_module, "get_evidence_store", lambda settings: None)
    service = AttributionService(
        db_session, backend_factory=lambda: _StubBackend(), explain_fn=_fake_explain
    )
    body = FeatureAttributionRequest(model_id=seeded_model.id, text="hello")

    with pytest.raises(EvidenceStoreUnavailableError):
        service.create_run(body)


def test_get_run_not_found(db_session, fake_evidence_store, monkeypatch):
    from app.api.errors import NotFoundError
    from app.attribution.service import AttributionService
    import app.attribution.service as service_module

    monkeypatch.setattr(service_module, "get_evidence_store", lambda settings: fake_evidence_store)
    service = AttributionService(db_session)

    with pytest.raises(NotFoundError):
        service.get_run(uuid.uuid4())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_attribution_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.attribution.service'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/attribution/service.py
"""AttributionService — orchestration for SHAP feature-attribution runs
(design doc 2026-09-15). Deliberately does not import ProbeContext,
ProbeOutput, ProbeRegistry, run_all_probes, confidence.engine.refine, or
ProbeResultRepository — this is a model-centric, ad hoc diagnostic, not an
evaluation-lifecycle-bound probe run.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.api.errors import NotFoundError, ValidationAppError
from app.attribution.errors import EvidenceStoreUnavailableError, UnsupportedModelTypeError
from app.attribution.schemas import (
    FeatureAttributionList,
    FeatureAttributionRead,
    FeatureAttributionRequest,
)
from app.attribution.shap_text import ShapExplainResult, explain
from app.core.config import Settings, get_settings
from app.db.models import FeatureAttributionResult
from app.db.repositories.feature_attribution import FeatureAttributionRepository
from app.db.repositories.model import ModelRepository
from app.inference.base import InferenceConfig, TaskType
from app.inference.errors import InferenceError
from app.inference.local_hf import LocalHFBackend
from app.storage.evidence_store import format_sha256, get_evidence_store

METHODOLOGY_VERSION = "tl-attribution-v1.0"

LIMITATIONS: list[str] = [
    "single-instance explanation, not global model behavior",
    "approximate — Shapley values are estimated by sampling, not exact for non-linear models",
    "sensitive to explainer configuration (background distribution / masker choice)",
]

ExplainFn = Callable[[Any, str, int], ShapExplainResult]
BackendFactory = Callable[[], Any]


class AttributionService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        backend_factory: BackendFactory = LocalHFBackend,
        explain_fn: ExplainFn = explain,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._models = ModelRepository(session)
        self._results = FeatureAttributionRepository(session)
        self._backend_factory = backend_factory
        self._explain_fn = explain_fn

    def create_run(self, body: FeatureAttributionRequest) -> FeatureAttributionRead:
        model = self._models.get_by_id(body.model_id)
        if model is None:
            raise NotFoundError(
                f"Model {body.model_id} not found", details={"model_id": body.model_id}
            )
        if body.method != "shap":
            raise ValidationAppError(
                f"method {body.method!r} is not supported yet — only 'shap' is implemented",
                details={"method": body.method},
            )

        store = get_evidence_store(self._settings)
        if store is None:
            raise EvidenceStoreUnavailableError()

        backend = self._backend_factory()
        revision = body.model_revision or model.revision
        try:
            loaded_info = backend.load(
                model.hf_repo_id,
                revision=revision,
                config=InferenceConfig(task_type=TaskType.MULTICLASS_CLASSIFICATION),
            )
        except InferenceError as exc:
            if exc.code == "UNSUPPORTED_TASK":
                raise UnsupportedModelTypeError(details={"cause": exc.message}) from exc
            raise

        try:
            prediction = backend.predict_batch([body.text])
            record = prediction.predictions[0]
            predicted_index = int(record.y_hat)
            probs = record.probabilities or []
            predicted_score = probs[predicted_index] if predicted_index < len(probs) else None
            id2label = loaded_info.id2label or {}
            label_space = {str(k): v for k, v in id2label.items()}
            predicted_label = label_space.get(str(predicted_index))

            explanation = self._explain_fn(backend, body.text, predicted_index)
        finally:
            backend.close()

        row_id = uuid.uuid4()
        artifact = {
            "method": "shap",
            "model_id": body.model_id,
            "model_ref": model.hf_repo_id,
            "model_revision": revision,
            "input_text": body.text,
            "predicted_index": predicted_index,
            "predicted_label": predicted_label,
            "predicted_score": predicted_score,
            "token_attributions": [t.model_dump() for t in explanation.token_attributions],
            "raw_shap": explanation.raw,
            "limitations": LIMITATIONS,
        }
        ref = store.put_artifact(
            data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
            content_type="application/json",
            probe_name="feature_attribution",
            evaluation_id=row_id,
        )

        row = self._results.create(
            id=row_id,
            model_id=body.model_id,
            evaluation_id=None,
            method="shap",
            modality="text",
            input_text=body.text,
            input_hash=format_sha256(body.text.encode("utf-8")),
            predicted_label=predicted_label,
            predicted_index=predicted_index,
            predicted_score=predicted_score,
            label_space=label_space,
            token_attributions=[t.model_dump() for t in explanation.token_attributions],
            model_ref=model.hf_repo_id,
            model_revision=revision,
            inference_metadata=None,
            methodology_version=METHODOLOGY_VERSION,
            status="EVALUATED",
            status_reason=None,
            evidence_refs=[ref.model_dump(mode="json")],
        )
        return self.to_read(row)

    def get_run(self, result_id: uuid.UUID) -> FeatureAttributionRead:
        row = self._results.get_by_id(result_id)
        if row is None:
            raise NotFoundError(
                f"Attribution run {result_id} not found", details={"id": str(result_id)}
            )
        return self.to_read(row)

    def list_runs(
        self, *, model_id: int, limit: int = 50, cursor: str | None = None
    ) -> FeatureAttributionList:
        rows, next_cursor = self._results.list_by_model(model_id, limit=limit, cursor=cursor)
        return FeatureAttributionList(items=[self.to_read(r) for r in rows], next_cursor=next_cursor)

    def to_read(self, row: FeatureAttributionResult) -> FeatureAttributionRead:
        read = FeatureAttributionRead.model_validate(row)
        return read.model_copy(update={"limitations": LIMITATIONS})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_attribution_service.py -v`
Expected: PASS (6 tests) — requires `TEST_DATABASE_URL` set and migrated (`db_session` fixture); skips cleanly otherwise, same as every other DB-backed test in this suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/attribution/service.py backend/tests/test_attribution_service.py
git commit -m "feat(attribution): add AttributionService orchestration"
```

---

### Task 7: `/v1/attribution/*` router

**Files:**
- Create: `backend/app/routers/v1/attribution.py`
- Modify: `backend/app/routers/v1/__init__.py:7-28` (register the new router)
- Test: `backend/tests/test_attribution_router.py`

**Interfaces:**
- Consumes: `AttributionService` (Task 6), `get_db` (existing), `FeatureAttributionRequest`/`FeatureAttributionRead`/`FeatureAttributionList` (Task 2), `ErrorResponse` (existing).
- Produces: `POST /v1/attribution/runs`, `GET /v1/attribution/runs/{id}`, `GET /v1/attribution/runs`.

Router tests monkeypatch `AttributionService` itself (same style as testing any other thin FastAPI router in this repo — the service is already unit-tested in Task 6) so no real SHAP/torch call happens here either.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_attribution_router.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest


def _fake_read(model_id: int) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "model_id": model_id,
        "evaluation_id": None,
        "method": "shap",
        "modality": "text",
        "input_text": "hello world",
        "predicted_label": "POSITIVE",
        "predicted_index": 1,
        "predicted_score": 0.9,
        "label_space": {"0": "NEGATIVE", "1": "POSITIVE"},
        "token_attributions": [{"token": "hello", "weight": 0.1, "position": 0}],
        "model_ref": "org/model",
        "model_revision": None,
        "inference_metadata": None,
        "methodology_version": "tl-attribution-v1.0",
        "status": "EVALUATED",
        "status_reason": None,
        "evidence_refs": [],
        "limitations": ["single-instance explanation, not global model behavior"],
        "created_at": datetime.now(UTC).isoformat(),
    }


def test_post_attribution_runs_returns_created_row(api_client, seeded_model, monkeypatch):
    from app.attribution.schemas import FeatureAttributionRead
    import app.routers.v1.attribution as attribution_router

    class _FakeService:
        def __init__(self, session):
            pass

        def create_run(self, body):
            return FeatureAttributionRead.model_validate(_fake_read(body.model_id))

    monkeypatch.setattr(attribution_router, "AttributionService", _FakeService)

    response = api_client.post(
        "/v1/attribution/runs",
        json={"model_id": seeded_model.id, "text": "hello world"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "shap"
    assert body["predicted_label"] == "POSITIVE"


def test_post_attribution_runs_rejects_lime(api_client, seeded_model):
    response = api_client.post(
        "/v1/attribution/runs",
        json={"model_id": seeded_model.id, "text": "hello world", "method": "lime"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_get_attribution_run_not_found(api_client, monkeypatch):
    from app.api.errors import NotFoundError
    import app.routers.v1.attribution as attribution_router

    class _FakeService:
        def __init__(self, session):
            pass

        def get_run(self, result_id):
            raise NotFoundError(f"Attribution run {result_id} not found")

    monkeypatch.setattr(attribution_router, "AttributionService", _FakeService)

    response = api_client.get(f"/v1/attribution/runs/{uuid.uuid4()}")

    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_attribution_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.v1.attribution'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/routers/v1/attribution.py
"""Feature-attribution routes (SHAP) — design doc 2026-09-15.

Synchronous, model-centric, ad hoc — not evaluation-lifecycle-bound. No
auth dependency, matching every other /v1/* router in this instance.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.attribution.schemas import (
    FeatureAttributionList,
    FeatureAttributionRead,
    FeatureAttributionRequest,
)
from app.attribution.service import AttributionService
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/attribution", tags=["attribution"])


@router.post(
    "/runs",
    response_model=FeatureAttributionRead,
    summary="Run SHAP feature attribution for one text input",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def create_attribution_run(
    body: FeatureAttributionRequest,
    db: Session = Depends(get_db),
) -> FeatureAttributionRead:
    return AttributionService(db).create_run(body)


@router.get(
    "/runs/{result_id}",
    response_model=FeatureAttributionRead,
    responses={404: {"model": ErrorResponse}},
)
def get_attribution_run(
    result_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FeatureAttributionRead:
    return AttributionService(db).get_run(result_id)


@router.get(
    "/runs",
    response_model=FeatureAttributionList,
)
def list_attribution_runs(
    model_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor (last run id)"),
    db: Session = Depends(get_db),
) -> FeatureAttributionList:
    return AttributionService(db).list_runs(model_id=model_id, limit=limit, cursor=cursor)
```

```python
# backend/app/routers/v1/__init__.py — full replacement
"""/v1 API router aggregate."""

from __future__ import annotations

from fastapi import APIRouter

from app.routers.v1 import (
    attribution,
    dataset_content,
    documentation,
    evaluation_actions,
    evaluation_drafts,
    evaluations,
    import_hf,
    models,
    reports,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(models.router)
api_router.include_router(import_hf.router)
api_router.include_router(documentation.router)
api_router.include_router(dataset_content.router)
api_router.include_router(dataset_content.content_router)
api_router.include_router(dataset_content.upload_router)
api_router.include_router(evaluations.router)
api_router.include_router(evaluation_actions.router)
api_router.include_router(evaluation_drafts.router)
api_router.include_router(reports.router)
api_router.include_router(attribution.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_attribution_router.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/v1/attribution.py backend/app/routers/v1/__init__.py backend/tests/test_attribution_router.py
git commit -m "feat(attribution): add /v1/attribution/* router"
```

---

### Task 8: Frontend — `FeatureAttributionPage` + `ModelDetailPage` entry point

**Files:**
- Modify: `frontend/src/api/types.ts` (append attribution types near `ModelRead`, after line 47)
- Create: `frontend/src/pages/FeatureAttributionPage.tsx`
- Create: `frontend/src/pages/FeatureAttributionPage.test.tsx`
- Modify: `frontend/src/pages/ModelDetailPage.tsx:63-69` (add entry-point button)
- Modify: `frontend/src/App.tsx:9,24` (register route)

**Interfaces:**
- Consumes: `apiFetch` (existing `frontend/src/api/client.ts`), `ErrorNotice`, `Spinner` (existing components).
- Produces: route `/models/:id/attribution`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/FeatureAttributionPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { apiFetch } from "../api/client";
import FeatureAttributionPage from "./FeatureAttributionPage";

vi.mock("../api/client", () => ({ apiFetch: vi.fn() }));

const mockedApiFetch = vi.mocked(apiFetch);

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/models/1/attribution"]}>
      <Routes>
        <Route path="/models/:id/attribution" element={<FeatureAttributionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("FeatureAttributionPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("shows the fixed limitations block after a successful run", async () => {
    mockedApiFetch.mockResolvedValueOnce({
      id: "r1",
      model_id: 1,
      method: "shap",
      modality: "text",
      input_text: "hello world",
      predicted_label: "POSITIVE",
      predicted_index: 1,
      predicted_score: 0.9,
      label_space: { "0": "NEGATIVE", "1": "POSITIVE" },
      token_attributions: [
        { token: "hello", weight: 0.2, position: 0 },
        { token: "world", weight: -0.1, position: 1 },
      ],
      model_ref: "org/model",
      model_revision: null,
      methodology_version: "tl-attribution-v1.0",
      status: "EVALUATED",
      evidence_refs: [],
      limitations: [
        "single-instance explanation, not global model behavior",
        "approximate — Shapley values are estimated by sampling, not exact for non-linear models",
        "sensitive to explainer configuration (background distribution / masker choice)",
      ],
      created_at: "2026-09-15T00:00:00Z",
    });

    renderPage();
    await userEvent.type(screen.getByLabelText(/input text/i), "hello world");
    await userEvent.click(screen.getByRole("button", { name: /explain prediction/i }));

    await waitFor(() => expect(screen.getByText(/POSITIVE/)).toBeInTheDocument());
    expect(
      screen.getByText(/single-instance explanation, not global model behavior/),
    ).toBeInTheDocument();
  });

  it("shows a distinct message for UNSUPPORTED_MODEL_TYPE", async () => {
    const { ApiError } = await import("../api/client");
    mockedApiFetch.mockRejectedValueOnce(
      new ApiError(422, {
        code: "UNSUPPORTED_MODEL_TYPE",
        message: "model does not have a supported text-classification head",
        details: {},
      }),
    );

    renderPage();
    await userEvent.type(screen.getByLabelText(/input text/i), "hello world");
    await userEvent.click(screen.getByRole("button", { name: /explain prediction/i }));

    await waitFor(() =>
      expect(screen.getByText(/not a supported text-classification model/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/FeatureAttributionPage.test.tsx`
Expected: FAIL with `Cannot find module './FeatureAttributionPage'`

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/src/api/types.ts — insert after ModelList (after line 51, before the next section)
export interface TokenAttribution {
  token: string;
  weight: number;
  position: number;
}

export interface FeatureAttributionRead {
  id: string;
  model_id: number;
  evaluation_id: string | null;
  method: string;
  modality: string;
  input_text: string;
  predicted_label: string | null;
  predicted_index: number | null;
  predicted_score: number | null;
  label_space: Record<string, string> | null;
  token_attributions: TokenAttribution[] | null;
  model_ref: string;
  model_revision: string | null;
  inference_metadata: Record<string, unknown> | null;
  methodology_version: string;
  status: string;
  status_reason: string | null;
  evidence_refs: unknown[];
  limitations: string[];
  created_at: string;
}

export interface FeatureAttributionRequest {
  model_id: number;
  text: string;
  method?: "shap";
  model_revision?: string | null;
}
```

```tsx
// frontend/src/pages/FeatureAttributionPage.tsx
import { useState } from "react";
import { useParams } from "react-router-dom";

import { apiFetch, ApiError } from "../api/client";
import type { FeatureAttributionRead, FeatureAttributionRequest } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";

function weightColor(weight: number): string {
  const intensity = Math.min(1, Math.abs(weight));
  return weight >= 0
    ? `rgba(34, 197, 94, ${0.15 + intensity * 0.6})`
    : `rgba(239, 68, 68, ${0.15 + intensity * 0.6})`;
}

export default function FeatureAttributionPage() {
  const { id } = useParams();
  const modelId = Number(id);
  const [text, setText] = useState("");
  const [result, setResult] = useState<FeatureAttributionRead | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const isUnsupportedModel = error instanceof ApiError && error.code === "UNSUPPORTED_MODEL_TYPE";

  async function handleSubmit() {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const body: FeatureAttributionRequest = { model_id: modelId, text, method: "shap" };
      const row = await apiFetch<FeatureAttributionRead>("/v1/attribution/runs", {
        method: "POST",
        body,
      });
      setResult(row);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="identity-header">
        <div className="identity-title">
          <h1>Explain a prediction</h1>
        </div>
      </div>

      <div className="card">
        <label htmlFor="attribution-input">Input text</label>
        <textarea
          id="attribution-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={2000}
          rows={4}
          style={{ width: "100%", marginTop: "0.5rem" }}
        />
        <button
          type="button"
          className="btn"
          disabled={loading || text.trim().length === 0}
          onClick={() => void handleSubmit()}
          style={{ marginTop: "0.75rem" }}
        >
          {loading ? "Working…" : "Explain prediction"}
        </button>
      </div>

      {loading ? <Spinner label="Loading model — first request can take longer…" /> : null}

      {isUnsupportedModel ? (
        <div className="notice notice-error">
          This model does not have a supported text-classification head — feature attribution
          (v1) only supports text-classification models.
        </div>
      ) : (
        <ErrorNotice error={error} />
      )}

      {result ? (
        <div className="card">
          <h2>Result</h2>
          <p>
            Predicted: <strong>{result.predicted_label ?? "—"}</strong>{" "}
            {result.predicted_score != null ? `(${result.predicted_score.toFixed(3)})` : null}
          </p>
          <p className="field-hint">
            Method: {result.method.toUpperCase()} · Model: <span className="mono">{result.model_ref}</span>
            {result.model_revision ? ` @ ${result.model_revision.slice(0, 8)}` : ""}
          </p>
          <div style={{ marginTop: "0.75rem", lineHeight: 2 }}>
            {(result.token_attributions ?? []).map((t) => (
              <span
                key={t.position}
                style={{ backgroundColor: weightColor(t.weight), padding: "0.1rem 0.2rem", marginRight: "0.15rem" }}
                title={`weight: ${t.weight.toFixed(4)}`}
              >
                {t.token}
              </span>
            ))}
          </div>
          <div className="notice notice-warning" style={{ marginTop: "1rem" }}>
            <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
              {result.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </>
  );
}
```

```tsx
// frontend/src/pages/ModelDetailPage.tsx — inside the identity-header, add alongside the "Evaluate model" link (near line 63-69)
        {isPinned ? (
          <div className="btn-row">
            <Link to={`/evaluations/new?modelId=${model.id}`} className="btn">
              Evaluate model
            </Link>
            <Link to={`/models/${model.id}/attribution`} className="btn btn-secondary">
              Explain a prediction
            </Link>
          </div>
        ) : (
          <span className="field-hint">Re-import with a revision to evaluate this model.</span>
        )}
```

```tsx
// frontend/src/App.tsx — add import (after line 9) and route (after line 24)
import FeatureAttributionPage from "./pages/FeatureAttributionPage";
// ...
          <Route path="/models/:id/attribution" element={<FeatureAttributionPage />} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/FeatureAttributionPage.test.tsx`
Expected: PASS (2 tests)

Also run the full frontend typecheck to confirm `ModelDetailPage.tsx`/`App.tsx` edits compile: `cd frontend && npx tsc --noEmit -p .`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/FeatureAttributionPage.tsx frontend/src/pages/FeatureAttributionPage.test.tsx frontend/src/pages/ModelDetailPage.tsx frontend/src/App.tsx
git commit -m "feat(attribution): add FeatureAttributionPage and ModelDetailPage entry point"
```

---

## Deferred (not in this plan, per spec §"Implementation phases" item 4)

- LIME as a second `method`.
- Queuing (Celery) if usage shows concurrent/repeated-model traffic.
- Image/tabular `modality` support.
