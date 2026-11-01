# Feature Attribution (SHAP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone, model-centric "explain a prediction" capability using SHAP over `LocalHFBackend`-loaded text-classification models — fully separate from the FRIES probe system.

**Architecture:** New `backend/app/attribution/` package (service + SHAP wrapper + schemas + errors), a new `feature_attribution_results` table/repository, a synchronous `/v1/attribution/*` router, and a standalone `FeatureAttributionPage` reached from `ModelDetailPage`. Reuses `LocalHFBackend`, `EvidenceStore`, `ModelRepository`, and the existing `AppError` machinery as-is.

**Tech Stack:** FastAPI, SQLAlchemy (sync), Alembic, Pydantic v2, `shap`, `transformers`/`torch` (already-optional `robustness` extra), React + TypeScript (Vite).

**Spec:** `docs/superpowers/specs/2026-09-15-feature-attribution-shap-lime-design.md`

## Global Constraints

- Never touches `FriesDimension`, `ProbeRegistry`, `probe_results`, `run_all_probes`, or `confidence.engine.refine` (locked, spec §1).
- v1 supports **text-classification models only**, via `LocalHFBackend` (spec: locked constraint).
- v1 method is **`"shap"` only** — `"lime"` is a valid schema value but rejected at the API layer with `422 UNSUPPORTED_METHOD` (spec §4).
- Synchronous execution, no Celery, in v1 (spec §3, §7).
- No auth on the new router — this codebase has none anywhere (spec §1, `alembic/versions/008_remove_auth_and_ownership.py`).
- `feature_attribution_results.evaluation_id` is nullable, **no FK constraint** (spec, resolved).
- No numeric "confidence" field on a result — always a fixed, non-conditional `limitations: list[str]` instead (spec §5).
- No `AttributionService` model caching across requests — a fresh `LocalHFBackend()` per call, discarded after (spec §7).

---

### Task 1: `FeatureAttributionResult` ORM model + migration

**Files:**
- Modify: `backend/app/db/models.py` (add `FeatureAttributionResult` class, after `ProbeResult`)
- Create: `backend/alembic/versions/014_add_feature_attribution_results.py`
- Test: `backend/tests/test_feature_attribution_model.py`

**Interfaces:**
- Produces: `FeatureAttributionResult` ORM class with columns `id, model_id, evaluation_id, method, input_text, input_hash, predicted_label, predicted_index, predicted_score, label_space, token_attributions, model_ref, model_revision, inference_metadata, methodology_version, status, status_reason, evidence_refs, created_at`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_feature_attribution_model.py
"""FeatureAttributionResult ORM model — column shape and FK-to-models.id only."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models import FeatureAttributionResult, Model


def test_create_and_read_feature_attribution_result(db_session) -> None:
    model = Model(hf_repo_id=f"org/attr-model-{uuid.uuid4().hex[:8]}", model_metadata={}, revision="a" * 40)
    db_session.add(model)
    db_session.flush()

    row = FeatureAttributionResult(
        model_id=model.id,
        evaluation_id=None,
        method="shap",
        input_text="This movie was great.",
        input_hash="sha256:" + "a" * 64,
        predicted_label="POSITIVE",
        predicted_index=1,
        predicted_score=0.97,
        label_space={"0": "NEGATIVE", "1": "POSITIVE"},
        token_attributions=[{"token": "great", "weight": 0.8, "position": 4}],
        model_ref=model.hf_repo_id,
        model_revision="a" * 40,
        inference_metadata={"device": "cpu"},
        methodology_version="tl-attribution-v1.0",
        status="EVALUATED",
        status_reason=None,
        evidence_refs=[{"evidence_id": "e1", "uri": "s3://x/y", "hash": "sha256:b", "content_type": "application/json", "probe_name": "feature_attribution"}],
    )
    db_session.add(row)
    db_session.flush()

    fetched = db_session.scalars(select(FeatureAttributionResult).where(FeatureAttributionResult.id == row.id)).one()
    assert fetched.model_id == model.id
    assert fetched.evaluation_id is None
    assert fetched.method == "shap"
    assert fetched.predicted_label == "POSITIVE"
    assert fetched.token_attributions[0]["token"] == "great"
    assert fetched.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_feature_attribution_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'FeatureAttributionResult' from 'app.db.models'`

- [ ] **Step 3: Add the ORM model**

In `backend/app/db/models.py`, add after the `ProbeResult` class (which ends around line 375, right before `OsdAgentOutput`):

```python
class FeatureAttributionResult(Base, TimestampMixin):
    """SHAP/LIME feature-attribution run — model-centric, NOT a FRIES probe.

    Never joined into dimension_scores/FRIES scoring. evaluation_id is a
    nullable, unconstrained pointer only (a report may cite that attribution
    ran for this evaluation's model); it carries no FK and no cascade.
    """

    __tablename__ = "feature_attribution_results"
    __table_args__ = (Index("ix_feature_attribution_results_model_id", "model_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[int] = mapped_column(Integer, ForeignKey("models.id", ondelete="RESTRICT"), nullable=False)
    evaluation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    predicted_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    predicted_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_score: Mapped[float | None] = mapped_column(nullable=True)
    label_space: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    token_attributions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    model_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    inference_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    methodology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")

    model: Mapped[Model] = relationship()
```

`Index` must already be imported at the top of `models.py` (it is — used by `Report`/`ProbeResult`); `Mapped`, `mapped_column`, `relationship`, `Integer`, `String`, `Text`, `ForeignKey`, `JSONB`, `UUID`, `Any`, `uuid` are all already imported for the existing models in this file — no new imports needed beyond what's already at the top of `models.py`.

- [ ] **Step 4: Create the migration**

```python
# backend/alembic/versions/014_add_feature_attribution_results.py
"""Add feature_attribution_results table (SHAP/LIME, non-FRIES).

Revision ID: 014_add_feature_attribution_results
Revises: 013_add_positive_label_index
Create Date: 2026-09-15

Standalone table, deliberately not FK'd to evaluations — feature attribution
is model-centric and never counts toward FRIES/O/S/D (see
docs/superpowers/specs/2026-09-15-feature-attribution-shap-lime-design.md).
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
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("predicted_label", sa.String(length=256), nullable=True),
        sa.Column("predicted_index", sa.Integer(), nullable=True),
        sa.Column("predicted_score", sa.Float(), nullable=True),
        sa.Column("label_space", postgresql.JSONB(), nullable=True),
        sa.Column("token_attributions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("model_ref", sa.String(length=256), nullable=False),
        sa.Column("model_revision", sa.String(length=128), nullable=True),
        sa.Column("inference_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_feature_attribution_results_model_id",
        "feature_attribution_results",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_feature_attribution_results_model_id", table_name="feature_attribution_results")
    op.drop_table("feature_attribution_results")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_feature_attribution_model.py -v`
Expected: PASS (the test fixture `db_session` runs migrations via `ensure_migrated`/`alembic upgrade head`, per `tests/conftest.py` — this migration must apply cleanly against the current head).

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/014_add_feature_attribution_results.py backend/tests/test_feature_attribution_model.py
git commit -m "feat: add feature_attribution_results table (SHAP/LIME, non-FRIES)"
```

---

### Task 2: `EvidenceRef` docstring correction

**Files:**
- Modify: `backend/app/schemas/evidence.py:11`

**Interfaces:** none (docs-only; schema shape unchanged).

- [ ] **Step 1: Edit the docstring**

Change:
```python
class EvidenceRef(BaseModel):
    """Immutable reference stored in ``probe_results.evidence_refs`` JSONB."""
```
to:
```python
class EvidenceRef(BaseModel):
    """Immutable evidence-artifact reference (MinIO/S3 pointer + hash).

    Stored today in both ``probe_results.evidence_refs`` and
    ``feature_attribution_results.evidence_refs`` JSONB columns — this schema
    itself carries no FK or probe-specific coupling.
    """
```

- [ ] **Step 2: Run the existing schema test to confirm nothing broke**

Run: `cd backend && python -m pytest tests/test_probe_output_contract.py -v`
Expected: PASS (docstring-only change, no behavior change).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/evidence.py
git commit -m "docs: correct EvidenceRef docstring for its second caller"
```

---

### Task 3: `LocalHFBackend` — expose loaded model/tokenizer

SHAP needs the raw HF `model`/`tokenizer` objects to build a `transformers.pipeline`; `InferenceBackend`'s protocol (`predict`/`predict_batch`/`device_info`/`close`) doesn't expose them. This is a small, additive property addition — not a duplication of load logic, and not a change to the load/predict contract other probes rely on.

**Files:**
- Modify: `backend/app/inference/local_hf.py` (add two properties after `predict_batch`)
- Test: `backend/tests/test_inference_backend.py` (add one test)

**Interfaces:**
- Produces: `LocalHFBackend.model -> Any | None`, `LocalHFBackend.tokenizer -> Any | None` (the loaded transformers objects, or `None` before `load()`/after `close()`).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_inference_backend.py`:

```python
def test_model_and_tokenizer_exposed_after_load_and_cleared_after_close() -> None:
    backend = LocalHFBackend()
    assert backend.model is None
    assert backend.tokenizer is None
    backend.load("distilbert-base-uncased-finetuned-sst-2-english")
    assert backend.model is not None
    assert backend.tokenizer is not None
    backend.close()
    assert backend.model is None
    assert backend.tokenizer is None
```

(This mirrors the file's existing pattern of loading a small real public model — check the top of `test_inference_backend.py` for the `@pytest.mark.skipif` / network-guard marker already used by its other real-load tests, and apply the same marker to this test so it skips identically in offline CI.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_inference_backend.py -k model_and_tokenizer -v`
Expected: FAIL — `AttributeError: 'LocalHFBackend' object has no attribute 'model'`

- [ ] **Step 3: Add the properties**

In `backend/app/inference/local_hf.py`, immediately after `predict_batch` (before `_decode_logits`):

```python
    @property
    def model(self) -> Any:
        """The loaded transformers model, or None before load()/after close().

        Exposed only for callers that need the raw object (e.g. SHAP's
        transformers pipeline integration in app.attribution.shap_text) —
        predict()/predict_batch() remain the contract every probe uses.
        """
        return self._model

    @property
    def tokenizer(self) -> Any:
        """The loaded tokenizer, or None before load()/after close()."""
        return self._tokenizer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_inference_backend.py -k model_and_tokenizer -v`
Expected: PASS (or SKIPPED if the file's existing network guard skips real-model tests in this environment — same as its sibling tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/inference/local_hf.py backend/tests/test_inference_backend.py
git commit -m "feat: expose loaded model/tokenizer on LocalHFBackend for SHAP integration"
```

---

### Task 4: `app/attribution/` package — errors, schemas

**Files:**
- Create: `backend/app/attribution/__init__.py` (empty)
- Create: `backend/app/attribution/errors.py`
- Create: `backend/app/attribution/schemas.py`
- Test: `backend/tests/test_attribution_schemas.py`

**Interfaces:**
- Produces: `UnsupportedModelTypeError(AppError)`, `UnsupportedMethodError(AppError)`; `TokenAttribution`, `AttributionRunRequest`, `FeatureAttributionRead` (Pydantic models).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_attribution_schemas.py
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.attribution.schemas import AttributionRunRequest, FeatureAttributionRead, TokenAttribution


def test_run_request_requires_non_empty_text() -> None:
    with pytest.raises(ValidationError):
        AttributionRunRequest(model_id=1, text="", method="shap")


def test_run_request_rejects_text_over_length_cap() -> None:
    with pytest.raises(ValidationError):
        AttributionRunRequest(model_id=1, text="x" * 2001, method="shap")


def test_run_request_accepts_shap_and_lime_at_schema_level() -> None:
    # Schema allows both — the router (Task 6) is what rejects "lime" for v1.
    AttributionRunRequest(model_id=1, text="hello", method="shap")
    AttributionRunRequest(model_id=1, text="hello", method="lime")


def test_token_attribution_shape() -> None:
    t = TokenAttribution(token="great", weight=0.8, position=4)
    assert t.token == "great"
    assert t.weight == 0.8
    assert t.position == 4


def test_feature_attribution_read_requires_limitations() -> None:
    with pytest.raises(ValidationError):
        FeatureAttributionRead.model_validate(
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "model_id": 1,
                "evaluation_id": None,
                "method": "shap",
                "input_text": "hello",
                "predicted_label": "POSITIVE",
                "predicted_index": 1,
                "predicted_score": 0.9,
                "label_space": {"0": "NEGATIVE", "1": "POSITIVE"},
                "token_attributions": [],
                "model_ref": "org/model",
                "model_revision": "abc",
                "inference_metadata": {},
                "methodology_version": "tl-attribution-v1.0",
                "status": "EVALUATED",
                "status_reason": None,
                "evidence_refs": [],
                "created_at": "2026-09-15T00:00:00Z",
                # "limitations" deliberately omitted
            }
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attribution_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.attribution'`

- [ ] **Step 3: Create the package files**

```python
# backend/app/attribution/__init__.py
```

```python
# backend/app/attribution/errors.py
"""Attribution-specific AppError subclasses — same {code, message, details} envelope as every other router."""

from __future__ import annotations

from typing import Any

from app.api.errors import AppError


class UnsupportedModelTypeError(AppError):
    """Model loaded but isn't a supported modality (v1: text-classification only)."""

    def __init__(
        self,
        message: str = "This model type is not supported for feature attribution yet",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("UNSUPPORTED_MODEL_TYPE", message, status_code=422, details=details)


class UnsupportedMethodError(AppError):
    """Attribution method valid at the schema level but not implemented yet (v1: shap only)."""

    def __init__(
        self,
        message: str = "This attribution method is not implemented yet",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("UNSUPPORTED_METHOD", message, status_code=422, details=details)
```

```python
# backend/app/attribution/schemas.py
"""Feature-attribution request/response schemas — standalone, not a probe schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_INPUT_TEXT_CHARS = 2000

METHODOLOGY_VERSION = "tl-attribution-v1.0"

LIMITATIONS: tuple[str, ...] = (
    "single-instance explanation, not global model behavior",
    "approximate — Shapley values are estimated by sampling, not exact for non-linear models",
    "sensitive to explainer configuration (background distribution / masker choice)",
)


class AttributionRunRequest(BaseModel):
    model_id: int
    text: str = Field(..., min_length=1, max_length=MAX_INPUT_TEXT_CHARS)
    method: Literal["shap", "lime"] = "shap"
    model_revision: str | None = None


class TokenAttribution(BaseModel):
    token: str
    weight: float
    position: int


class FeatureAttributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: int
    evaluation_id: uuid.UUID | None
    method: str
    input_text: str
    predicted_label: str | None
    predicted_index: int | None
    predicted_score: float | None
    label_space: dict[str, Any] | None
    token_attributions: list[TokenAttribution]
    model_ref: str
    model_revision: str | None
    inference_metadata: dict[str, Any] | None
    methodology_version: str
    status: str
    status_reason: str | None
    evidence_refs: list[dict[str, Any]]
    created_at: datetime
    limitations: list[str] = Field(default_factory=lambda: list(LIMITATIONS))


class FeatureAttributionList(BaseModel):
    items: list[FeatureAttributionRead]
    next_cursor: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_attribution_schemas.py -v`
Expected: 4 pass — the "requires_limitations" test fails to build validation error because `limitations` has a default; **fix**: change that test to instead assert the default populates:

```python
def test_feature_attribution_read_defaults_limitations_when_omitted() -> None:
    read = FeatureAttributionRead.model_validate(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "model_id": 1,
            "evaluation_id": None,
            "method": "shap",
            "input_text": "hello",
            "predicted_label": "POSITIVE",
            "predicted_index": 1,
            "predicted_score": 0.9,
            "label_space": {"0": "NEGATIVE", "1": "POSITIVE"},
            "token_attributions": [],
            "model_ref": "org/model",
            "model_revision": "abc",
            "inference_metadata": {},
            "methodology_version": "tl-attribution-v1.0",
            "status": "EVALUATED",
            "status_reason": None,
            "evidence_refs": [],
            "created_at": "2026-09-15T00:00:00Z",
        }
    )
    assert len(read.limitations) == 3
    assert "single-instance explanation" in read.limitations[0]
```

Replace the earlier `test_feature_attribution_read_requires_limitations` with this version in the test file, then re-run:

Run: `cd backend && python -m pytest tests/test_attribution_schemas.py -v`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add backend/app/attribution/__init__.py backend/app/attribution/errors.py backend/app/attribution/schemas.py backend/tests/test_attribution_schemas.py
git commit -m "feat: add app.attribution schemas and error types"
```

---

### Task 5: `app/attribution/shap_text.py` — SHAP explainer wrapper

**Files:**
- Create: `backend/app/attribution/shap_text.py`
- Test: `backend/tests/test_shap_text.py`

**Interfaces:**
- Consumes: `LocalHFBackend` (Task 3's `model`/`tokenizer` properties), `LoadedModelInfo.id2label` (existing, `app/inference/base.py`).
- Produces: `explain_text(backend: LocalHFBackend, text: str, *, max_tokens: int = 256) -> ShapTextResult` where `ShapTextResult` has `predicted_index: int`, `predicted_label: str`, `predicted_score: float`, `token_attributions: list[dict]` (`{"token", "weight", "position"}`), `raw_explanation: dict` (JSON-safe dump of the full SHAP output, for the evidence blob).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_shap_text.py
"""SHAP text-classification wrapper — requires torch/transformers/shap installed
(same optional [attribution] extra gate as LocalHFBackend's [robustness] extra).
Skips cleanly when shap isn't installed, matching this repo's existing pattern
for real-model tests (see test_inference_backend.py)."""
from __future__ import annotations

import pytest

shap = pytest.importorskip("shap")

from app.attribution.shap_text import explain_text
from app.inference.local_hf import LocalHFBackend


@pytest.mark.slow
def test_explain_text_returns_token_attributions_for_predicted_class() -> None:
    backend = LocalHFBackend()
    backend.load("distilbert-base-uncased-finetuned-sst-2-english")
    try:
        result = explain_text(backend, "This movie was absolutely wonderful.")
    finally:
        backend.close()

    assert result.predicted_label in ("POSITIVE", "NEGATIVE")
    assert isinstance(result.predicted_score, float)
    assert len(result.token_attributions) > 0
    for tok in result.token_attributions:
        assert "token" in tok and "weight" in tok and "position" in tok
    assert isinstance(result.raw_explanation, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_shap_text.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.attribution.shap_text'` (or SKIPPED if `shap` isn't installed yet in this environment — install it first per Task 7, or run this step after Task 7).

- [ ] **Step 3: Implement the wrapper**

```python
# backend/app/attribution/shap_text.py
"""SHAP wrapper for HF text-classification models — reads LocalHFBackend's
already-loaded model/tokenizer directly (Task 3's properties), never
downloads or re-loads anything itself."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.inference.local_hf import LocalHFBackend


@dataclass
class ShapTextResult:
    predicted_index: int
    predicted_label: str
    predicted_score: float
    token_attributions: list[dict[str, Any]] = field(default_factory=list)
    raw_explanation: dict[str, Any] = field(default_factory=dict)


def explain_text(backend: LocalHFBackend, text: str, *, max_tokens: int = 256) -> ShapTextResult:
    """Run one SHAP explanation over ``text`` using ``backend``'s loaded model.

    Raises whatever the underlying transformers/shap call raises on failure —
    callers (AttributionService) map that to a FAILED result, never crash the
    request.
    """
    import numpy as np
    import shap
    import torch
    import transformers

    model = backend.model
    tokenizer = backend.tokenizer
    if model is None or tokenizer is None:
        raise RuntimeError("backend.load() must be called before explain_text()")

    id2label: dict[int, str] = getattr(model.config, "id2label", None) or {}

    pipe = transformers.pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer,
        top_k=None,
        truncation=True,
        max_length=max_tokens,
        device=model.device,
    )

    with torch.no_grad():
        predictions = pipe([text])[0]
    best = max(predictions, key=lambda p: p["score"])
    label_to_index = {str(v): int(k) for k, v in id2label.items()} if id2label else {}
    predicted_index = label_to_index.get(best["label"], 0)
    predicted_label = str(best["label"])
    predicted_score = float(best["score"])

    explainer = shap.Explainer(pipe)
    explanation = explainer([text])

    values = np.asarray(explanation.values[0])
    if values.ndim == 2:
        # (n_tokens, n_classes) — select the predicted class column.
        class_index = min(predicted_index, values.shape[1] - 1)
        per_token_values = values[:, class_index]
    else:
        per_token_values = values

    tokens = list(explanation.data[0])
    token_attributions = [
        {"token": str(tok), "weight": float(val), "position": i}
        for i, (tok, val) in enumerate(zip(tokens, per_token_values, strict=False))
    ]

    raw_explanation = {
        "tokens": [str(t) for t in tokens],
        "values": [float(v) for v in per_token_values],
        "base_values": (
            float(np.asarray(explanation.base_values[0]).reshape(-1)[0])
            if explanation.base_values is not None
            else None
        ),
        "predicted_label": predicted_label,
        "predicted_index": predicted_index,
    }

    return ShapTextResult(
        predicted_index=predicted_index,
        predicted_label=predicted_label,
        predicted_score=predicted_score,
        token_attributions=token_attributions,
        raw_explanation=raw_explanation,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_shap_text.py -v`
Expected: PASS (requires the `[attribution]` extra installed locally — Task 7 adds it to `pyproject.toml`; install with `pip install -e ".[attribution]"` from `backend/` before running this step for real, or accept the `importorskip` SKIP in an environment without it).

- [ ] **Step 5: Commit**

```bash
git add backend/app/attribution/shap_text.py backend/tests/test_shap_text.py
git commit -m "feat: add SHAP text-classification explainer wrapper"
```

---

### Task 6: `app/attribution/service.py` — orchestration + repository

**Files:**
- Create: `backend/app/db/repositories/attribution.py`
- Create: `backend/app/attribution/service.py`
- Test: `backend/tests/test_attribution_service.py`

**Interfaces:**
- Consumes: `ModelRepository.get_by_id` (existing, `app/db/repositories/model.py`), `EvidenceStore.put_artifact` (existing), `explain_text` (Task 5), `LocalHFBackend` (Task 3), `AttributionRunRequest`/`FeatureAttributionRead` (Task 4).
- Produces: `FeatureAttributionRepository.create(...) -> FeatureAttributionResult`, `FeatureAttributionRepository.get_by_id(id) -> FeatureAttributionResult | None`, `FeatureAttributionRepository.list_for_model(model_id, *, limit, cursor) -> tuple[list[FeatureAttributionResult], str | None]`; `AttributionService.run(request: AttributionRunRequest) -> FeatureAttributionRead`, `AttributionService.get(id: uuid.UUID) -> FeatureAttributionRead`, `AttributionService.list(model_id: int | None, limit: int, cursor: str | None) -> FeatureAttributionList`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_attribution_service.py
"""AttributionService — mocks explain_text so no real model load happens."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.api.errors import NotFoundError
from app.attribution.errors import UnsupportedModelTypeError
from app.attribution.schemas import AttributionRunRequest
from app.attribution.service import AttributionService
from app.attribution.shap_text import ShapTextResult
from app.db.models import Model
from app.inference.errors import InferenceError, UNSUPPORTED_TASK
from tests.fakes import FakeEvidenceStore


def _seed_model(db_session) -> Model:
    model = Model(
        hf_repo_id=f"org/attr-{uuid.uuid4().hex[:8]}",
        model_metadata={},
        revision="a" * 40,
    )
    db_session.add(model)
    db_session.flush()
    return model


@patch("app.attribution.service.LocalHFBackend")
@patch("app.attribution.service.explain_text")
def test_run_persists_row_and_evidence_artifact(mock_explain, mock_backend_cls, db_session) -> None:
    model = _seed_model(db_session)
    mock_explain.return_value = ShapTextResult(
        predicted_index=1,
        predicted_label="POSITIVE",
        predicted_score=0.95,
        token_attributions=[{"token": "great", "weight": 0.8, "position": 1}],
        raw_explanation={"tokens": ["great"], "values": [0.8]},
    )
    mock_backend_cls.return_value.load.return_value.id2label = {0: "NEGATIVE", 1: "POSITIVE"}
    mock_backend_cls.return_value.device_info.return_value.__dict__ = {"device": "cpu"}

    store = FakeEvidenceStore()
    service = AttributionService(db_session, evidence_store=store)
    result = service.run(AttributionRunRequest(model_id=model.id, text="great movie", method="shap"))

    assert result.predicted_label == "POSITIVE"
    assert result.status == "EVALUATED"
    assert len(result.token_attributions) == 1
    assert len(result.evidence_refs) == 1
    assert len(result.limitations) == 3
    mock_backend_cls.return_value.close.assert_called_once()


def test_run_unknown_model_raises_not_found(db_session) -> None:
    store = FakeEvidenceStore()
    service = AttributionService(db_session, evidence_store=store)
    with pytest.raises(NotFoundError):
        service.run(AttributionRunRequest(model_id=999999, text="hello", method="shap"))


@patch("app.attribution.service.LocalHFBackend")
def test_run_unsupported_model_type_raises_typed_error(mock_backend_cls, db_session) -> None:
    model = _seed_model(db_session)
    mock_backend_cls.return_value.load.side_effect = InferenceError(
        UNSUPPORTED_TASK, "model has no sequence-classification head"
    )
    store = FakeEvidenceStore()
    service = AttributionService(db_session, evidence_store=store)
    with pytest.raises(UnsupportedModelTypeError):
        service.run(AttributionRunRequest(model_id=model.id, text="hello", method="shap"))


def test_get_returns_persisted_row(db_session) -> None:
    model = _seed_model(db_session)
    store = FakeEvidenceStore()
    service = AttributionService(db_session, evidence_store=store)
    with patch("app.attribution.service.LocalHFBackend") as mock_backend_cls, \
         patch("app.attribution.service.explain_text") as mock_explain:
        mock_explain.return_value = ShapTextResult(
            predicted_index=0, predicted_label="NEGATIVE", predicted_score=0.6,
            token_attributions=[], raw_explanation={},
        )
        mock_backend_cls.return_value.load.return_value.id2label = {0: "NEGATIVE", 1: "POSITIVE"}
        created = service.run(AttributionRunRequest(model_id=model.id, text="bad movie", method="shap"))

    fetched = service.get(created.id)
    assert fetched.id == created.id
    assert fetched.predicted_label == "NEGATIVE"


def test_get_unknown_id_raises_not_found(db_session) -> None:
    store = FakeEvidenceStore()
    service = AttributionService(db_session, evidence_store=store)
    with pytest.raises(NotFoundError):
        service.get(uuid.uuid4())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attribution_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.attribution.service'`

- [ ] **Step 3: Implement the repository**

```python
# backend/app/db/repositories/attribution.py
"""FeatureAttributionResult repository — standalone, not ProbeResultRepository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FeatureAttributionResult


class FeatureAttributionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, **kwargs: Any) -> FeatureAttributionResult:
        row = FeatureAttributionResult(**kwargs)
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, result_id: uuid.UUID) -> FeatureAttributionResult | None:
        return self._session.get(FeatureAttributionResult, result_id)

    def list_for_model(
        self, model_id: int | None, *, limit: int = 20
    ) -> list[FeatureAttributionResult]:
        stmt = select(FeatureAttributionResult).order_by(FeatureAttributionResult.created_at.desc()).limit(limit)
        if model_id is not None:
            stmt = stmt.where(FeatureAttributionResult.model_id == model_id)
        return list(self._session.scalars(stmt))
```

- [ ] **Step 4: Implement the service**

```python
# backend/app/attribution/service.py
"""AttributionService — orchestrates one SHAP run: load model, explain,
persist row + evidence artifact. Deliberately does not use ProbeContext/
ProbeOutput/ProbeRegistry — this is not a FRIES probe."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.api.errors import NotFoundError, ValidationAppError
from app.attribution.errors import UnsupportedModelTypeError
from app.attribution.schemas import (
    METHODOLOGY_VERSION,
    AttributionRunRequest,
    FeatureAttributionList,
    FeatureAttributionRead,
)
from app.attribution.shap_text import explain_text
from app.db.repositories.attribution import FeatureAttributionRepository
from app.db.repositories.model import ModelRepository
from app.inference.errors import InferenceError, UNSUPPORTED_TASK
from app.inference.local_hf import LocalHFBackend
from app.storage.evidence_store import EvidenceStore, EvidenceStoreError, format_sha256


class AttributionService:
    def __init__(self, session: Session, *, evidence_store: EvidenceStore) -> None:
        self._session = session
        self._models = ModelRepository(session)
        self._results = FeatureAttributionRepository(session)
        self._evidence_store = evidence_store

    def run(self, request: AttributionRunRequest) -> FeatureAttributionRead:
        model = self._models.get_by_id(request.model_id)
        if model is None:
            raise NotFoundError(f"Model {request.model_id} not found", details={"model_id": request.model_id})
        if request.method != "shap":
            raise ValidationAppError(f"method {request.method!r} is not implemented yet")

        revision = request.model_revision or model.revision
        backend = LocalHFBackend()
        try:
            try:
                loaded = backend.load(model.hf_repo_id, revision=revision)
            except InferenceError as exc:
                if exc.code == UNSUPPORTED_TASK:
                    raise UnsupportedModelTypeError(
                        "This model does not have a text-classification head",
                        details={"model_id": model.id, "cause": exc.message},
                    ) from exc
                raise

            shap_result = explain_text(backend, request.text)
            device_info = backend.device_info()
        finally:
            backend.close()

        input_hash = format_sha256(request.text.encode("utf-8"))
        id2label = loaded.id2label or {}

        artifact = {
            "method": "shap",
            "model_ref": model.hf_repo_id,
            "model_revision": revision,
            "input_text": request.text,
            "raw_explanation": shap_result.raw_explanation,
        }
        try:
            ref = self._evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name="feature_attribution",
                evaluation_id=uuid.uuid4(),  # standalone run, not tied to an Evaluation row
            )
        except EvidenceStoreError:
            raise

        row = self._results.create(
            model_id=model.id,
            evaluation_id=None,
            method="shap",
            input_text=request.text,
            input_hash=input_hash,
            predicted_label=shap_result.predicted_label,
            predicted_index=shap_result.predicted_index,
            predicted_score=shap_result.predicted_score,
            label_space={str(k): v for k, v in id2label.items()} or None,
            token_attributions=shap_result.token_attributions,
            model_ref=model.hf_repo_id,
            model_revision=revision,
            inference_metadata=asdict(device_info) if device_info else None,
            methodology_version=METHODOLOGY_VERSION,
            status="EVALUATED",
            status_reason=None,
            evidence_refs=[ref.model_dump(mode="json")],
        )
        return FeatureAttributionRead.model_validate(row)

    def get(self, result_id: uuid.UUID) -> FeatureAttributionRead:
        row = self._results.get_by_id(result_id)
        if row is None:
            raise NotFoundError(f"Attribution result {result_id} not found", details={"id": str(result_id)})
        return FeatureAttributionRead.model_validate(row)

    def list(self, *, model_id: int | None, limit: int = 20) -> FeatureAttributionList:
        rows = self._results.list_for_model(model_id, limit=limit)
        return FeatureAttributionList(items=[FeatureAttributionRead.model_validate(r) for r in rows])
```

`EvidenceStore.put_artifact` requires an `evaluation_id: uuid.UUID` (existing signature — it's used as an object-key namespace, not a real FK anywhere in `EvidenceStore` itself). Since this run has no real evaluation, a fresh `uuid.uuid4()` is generated purely to namespace the MinIO object key — it is **not** stored as `feature_attribution_results.evaluation_id` (that column stays `None` unless the caller explicitly supplies one via the API, added in Task 8).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_attribution_service.py -v`
Expected: PASS (5/5).

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/repositories/attribution.py backend/app/attribution/service.py backend/tests/test_attribution_service.py
git commit -m "feat: add AttributionService and FeatureAttributionRepository"
```

---

### Task 7: `pyproject.toml` — `attribution` extra

**Files:**
- Modify: `backend/pyproject.toml` (add to `[project.optional-dependencies]`, after the `robustness` block)

- [ ] **Step 1: Add the extra**

```toml
# Feature attribution (SHAP) — needs torch for the same reason `robustness`
# does (LocalHFBackend.load()); shap itself is the only new package.
attribution = [
  "shap>=0.45.0",
  "torch>=2.2.0",
]
```

- [ ] **Step 2: Install and verify**

Run: `cd backend && pip install -e ".[attribution]"`
Expected: installs `shap` (and `torch` if not already present from `[robustness]`) without conflict.

- [ ] **Step 3: Re-run Task 5's test for real (not skipped)**

Run: `cd backend && python -m pytest tests/test_shap_text.py -v`
Expected: PASS (no longer skipped now that `shap` is installed).

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build: add optional [attribution] extra (shap, torch)"
```

---

### Task 8: `/v1/attribution/*` router

**Files:**
- Create: `backend/app/routers/v1/attribution.py`
- Modify: `backend/app/routers/v1/__init__.py`
- Test: `backend/tests/test_attribution_router.py`

**Interfaces:**
- Consumes: `AttributionService` (Task 6), `get_db` (existing, `app/api/deps.py`), `get_evidence_store`/`Settings` (existing, `app/storage/evidence_store.py`, `app/core/config.py`).
- Produces: `POST /v1/attribution/runs`, `GET /v1/attribution/runs/{id}`, `GET /v1/attribution/runs?model_id=&limit=`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_attribution_router.py
from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.attribution.shap_text import ShapTextResult
from app.db.models import Model


def _seed_model(db_session) -> Model:
    model = Model(hf_repo_id=f"org/router-attr-{uuid.uuid4().hex[:8]}", model_metadata={}, revision="a" * 40)
    db_session.add(model)
    db_session.flush()
    return model


@patch("app.attribution.service.explain_text")
@patch("app.attribution.service.LocalHFBackend")
def test_post_run_returns_201_with_attribution_read(
    mock_backend_cls, mock_explain, api_client: TestClient, db_session
) -> None:
    model = _seed_model(db_session)
    mock_explain.return_value = ShapTextResult(
        predicted_index=1, predicted_label="POSITIVE", predicted_score=0.9,
        token_attributions=[{"token": "great", "weight": 0.7, "position": 0}],
        raw_explanation={},
    )
    mock_backend_cls.return_value.load.return_value.id2label = {0: "NEGATIVE", 1: "POSITIVE"}

    response = api_client.post(
        "/v1/attribution/runs",
        json={"model_id": model.id, "text": "great movie", "method": "shap"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["predicted_label"] == "POSITIVE"
    assert len(body["limitations"]) == 3


def test_post_run_unknown_model_returns_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/v1/attribution/runs", json={"model_id": 999999, "text": "hi", "method": "shap"}
    )
    assert response.status_code == 404


def test_post_run_lime_rejected_as_unsupported_method(api_client: TestClient, db_session) -> None:
    model = _seed_model(db_session)
    response = api_client.post(
        "/v1/attribution/runs", json={"model_id": model.id, "text": "hi", "method": "lime"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_METHOD"


def test_post_run_empty_text_returns_422(api_client: TestClient, db_session) -> None:
    model = _seed_model(db_session)
    response = api_client.post(
        "/v1/attribution/runs", json={"model_id": model.id, "text": "", "method": "shap"}
    )
    assert response.status_code == 422


@patch("app.attribution.service.explain_text")
@patch("app.attribution.service.LocalHFBackend")
def test_get_run_by_id_roundtrips(mock_backend_cls, mock_explain, api_client: TestClient, db_session) -> None:
    model = _seed_model(db_session)
    mock_explain.return_value = ShapTextResult(
        predicted_index=0, predicted_label="NEGATIVE", predicted_score=0.6,
        token_attributions=[], raw_explanation={},
    )
    mock_backend_cls.return_value.load.return_value.id2label = {0: "NEGATIVE", 1: "POSITIVE"}
    created = api_client.post(
        "/v1/attribution/runs", json={"model_id": model.id, "text": "bad", "method": "shap"}
    ).json()

    response = api_client.get(f"/v1/attribution/runs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["predicted_label"] == "NEGATIVE"


def test_get_run_unknown_id_returns_404(api_client: TestClient) -> None:
    response = api_client.get(f"/v1/attribution/runs/{uuid.uuid4()}")
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attribution_router.py -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet) or `ModuleNotFoundError`.

- [ ] **Step 3: Implement the router**

```python
# backend/app/routers/v1/attribution.py
"""/v1/attribution — standalone feature-attribution runs (SHAP). Not a FRIES
probe endpoint; no evaluation lifecycle, no auth (this codebase has none)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import AppError
from app.attribution.schemas import (
    AttributionRunRequest,
    FeatureAttributionList,
    FeatureAttributionRead,
)
from app.attribution.service import AttributionService
from app.core.config import get_settings
from app.schemas.common import ErrorResponse
from app.storage.evidence_store import get_evidence_store

router = APIRouter(prefix="/attribution", tags=["attribution"])


def _service(db: Session) -> AttributionService:
    store = get_evidence_store(get_settings())
    if store is None:
        raise AppError("EVIDENCE_STORE_UNCONFIGURED", "S3/MinIO is not configured", status_code=503)
    return AttributionService(db, evidence_store=store)


@router.post(
    "/runs",
    response_model=FeatureAttributionRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def create_run(body: AttributionRunRequest, db: Session = Depends(get_db)) -> FeatureAttributionRead:
    return _service(db).run(body)


@router.get(
    "/runs/{result_id}",
    response_model=FeatureAttributionRead,
    responses={404: {"model": ErrorResponse}},
)
def get_run(result_id: uuid.UUID, db: Session = Depends(get_db)) -> FeatureAttributionRead:
    return _service(db).get(result_id)


@router.get("/runs", response_model=FeatureAttributionList)
def list_runs(
    model_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> FeatureAttributionList:
    return _service(db).list(model_id=model_id, limit=limit)
```

Note: `AttributionRunRequest.method` is `Literal["shap", "lime"]` at the schema level (Task 4). Rejecting `"lime"` with `422 UNSUPPORTED_METHOD` happens inside `AttributionService.run()` (Task 6, `raise ValidationAppError(...)` when `method != "shap"`) — swap that to `UnsupportedMethodError` for the correct error code:

In `backend/app/attribution/service.py`, change:
```python
        if request.method != "shap":
            raise ValidationAppError(f"method {request.method!r} is not implemented yet")
```
to:
```python
        if request.method != "shap":
            raise UnsupportedMethodError(
                f"method {request.method!r} is not implemented yet — v1 supports shap only",
                details={"method": request.method},
            )
```
and add `UnsupportedMethodError` to the existing `from app.attribution.errors import UnsupportedModelTypeError` import line (`from app.attribution.errors import UnsupportedMethodError, UnsupportedModelTypeError`).

- [ ] **Step 4: Register the router**

In `backend/app/routers/v1/__init__.py`:
```python
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
api_router.include_router(attribution.router)
api_router.include_router(models.router)
...
```
(Insert `attribution.router` first alphabetically, matching the existing import ordering; the exact position among `include_router` calls doesn't matter functionally.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_attribution_router.py -v`
Expected: PASS (6/6).

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `cd backend && python -m pytest tests/ -q`
Expected: no new failures beyond any pre-existing environment gaps (e.g. missing `python-multipart`/`transformers` in this sandbox, unrelated to this change — see prior verification in this same working session).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/v1/attribution.py backend/app/routers/v1/__init__.py backend/app/attribution/service.py backend/tests/test_attribution_router.py
git commit -m "feat: add /v1/attribution router"
```

---

### Task 9: Frontend — `FeatureAttributionPage` + types + entry point

**Files:**
- Modify: `frontend/src/api/types.ts` (add attribution types)
- Create: `frontend/src/pages/FeatureAttributionPage.tsx`
- Modify: `frontend/src/pages/ModelDetailPage.tsx` (add entry-point link)
- Modify: `frontend/src/App.tsx` (add route)
- Test: `frontend/src/pages/FeatureAttributionPage.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` (existing, `api/client.ts`), `ErrorNotice`/`Spinner` (existing components).
- Produces: route `/models/:id/attribution`.

- [ ] **Step 1: Add types to `api/types.ts`**

Append near the end of the file (after `ReportRead`, before the errors section, matching the file's existing sectioning with a `// ---- attribution ----` header comment):

```typescript
// ---- feature attribution (SHAP) ----
// Standalone, model-centric — NOT a FRIES dimension, never joined into
// dimension_scores or report scoring. See docs/superpowers/specs/
// 2026-09-15-feature-attribution-shap-lime-design.md.

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
  input_text: string;
  predicted_label: string | null;
  predicted_index: number | null;
  predicted_score: number | null;
  label_space: Record<string, string> | null;
  token_attributions: TokenAttribution[];
  model_ref: string;
  model_revision: string | null;
  inference_metadata: Record<string, unknown> | null;
  methodology_version: string;
  status: string;
  status_reason: string | null;
  evidence_refs: Record<string, unknown>[];
  created_at: string;
  limitations: string[];
}

export interface AttributionRunRequest {
  model_id: number;
  text: string;
  method: "shap";
  model_revision?: string | null;
}
```

- [ ] **Step 2: Write the failing frontend test**

```tsx
// frontend/src/pages/FeatureAttributionPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { apiFetch } from "../api/client";
import FeatureAttributionPage from "./FeatureAttributionPage";

vi.mock("../api/client", () => ({
  apiFetch: vi.fn(),
}));

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
    vi.mocked(apiFetch).mockReset();
  });

  it("shows an empty input form with no prior submission", () => {
    renderPage();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.queryByText(/predicted/i)).not.toBeInTheDocument();
  });

  it("submits text and renders the prediction, tokens, and limitations", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      id: "r1",
      model_id: 1,
      evaluation_id: null,
      method: "shap",
      input_text: "great movie",
      predicted_label: "POSITIVE",
      predicted_index: 1,
      predicted_score: 0.95,
      label_space: { "0": "NEGATIVE", "1": "POSITIVE" },
      token_attributions: [{ token: "great", weight: 0.8, position: 0 }],
      model_ref: "org/model",
      model_revision: "abc123",
      inference_metadata: null,
      methodology_version: "tl-attribution-v1.0",
      status: "EVALUATED",
      status_reason: null,
      evidence_refs: [],
      created_at: "2026-09-15T00:00:00Z",
      limitations: ["single-instance explanation, not global model behavior"],
    });

    renderPage();
    await userEvent.type(screen.getByRole("textbox"), "great movie");
    await userEvent.click(screen.getByRole("button", { name: /explain/i }));

    await waitFor(() => expect(screen.getByText("POSITIVE")).toBeInTheDocument());
    expect(screen.getByText("great")).toBeInTheDocument();
    expect(screen.getByText(/single-instance explanation/i)).toBeInTheDocument();
  });

  it("shows a distinct message for UNSUPPORTED_MODEL_TYPE", async () => {
    const { ApiError } = await import("../api/client");
    vi.mocked(apiFetch).mockRejectedValueOnce(
      new ApiError(422, { code: "UNSUPPORTED_MODEL_TYPE", message: "not supported", details: {} }),
    );

    renderPage();
    await userEvent.type(screen.getByRole("textbox"), "hello");
    await userEvent.click(screen.getByRole("button", { name: /explain/i }));

    await waitFor(() =>
      expect(screen.getByText(/text-classification models only/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/FeatureAttributionPage.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the page**

```tsx
// frontend/src/pages/FeatureAttributionPage.tsx
import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import { ApiError, apiFetch } from "../api/client";
import type { AttributionRunRequest, FeatureAttributionRead } from "../api/types";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";

function tokenColor(weight: number): string {
  const intensity = Math.min(Math.abs(weight), 1);
  const alpha = 0.15 + intensity * 0.55;
  return weight >= 0 ? `rgba(34,139,34,${alpha})` : `rgba(178,34,34,${alpha})`;
}

export default function FeatureAttributionPage() {
  const { id } = useParams();
  const modelId = Number(id);
  const [text, setText] = useState("");
  const [result, setResult] = useState<FeatureAttributionRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const body: AttributionRunRequest = { model_id: modelId, text, method: "shap" };
      const response = await apiFetch<FeatureAttributionRead>("/v1/attribution/runs", {
        method: "POST",
        body,
      });
      setResult(response);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  const isUnsupportedModel = error instanceof ApiError && error.code === "UNSUPPORTED_MODEL_TYPE";

  return (
    <div>
      <h1>Explain a prediction</h1>
      <form onSubmit={(e) => void handleSubmit(e)}>
        <label>
          Input text
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={2000}
            rows={4}
          />
        </label>
        <button type="submit" disabled={loading || !text.trim()}>
          {loading ? "Loading model — first request can take longer…" : "Explain"}
        </button>
      </form>

      {loading ? <Spinner /> : null}

      {isUnsupportedModel ? (
        <div className="notice notice-error">
          This model is not supported for feature attribution — v1 supports text-classification models only.
        </div>
      ) : (
        <ErrorNotice error={error} />
      )}

      {result ? (
        <div>
          <p>
            Predicted: <strong>{result.predicted_label}</strong>
            {result.predicted_score !== null ? ` (${result.predicted_score.toFixed(3)})` : null}
          </p>
          <p>Method: SHAP</p>
          <p>
            Model: {result.model_ref} · revision {result.model_revision ?? "unknown"}
          </p>
          <p>Generated: {result.created_at}</p>
          <div>
            {result.token_attributions.map((t, i) => (
              <span key={i} style={{ backgroundColor: tokenColor(t.weight), padding: "0 2px" }}>
                {t.token}{" "}
              </span>
            ))}
          </div>
          <ul>
            {result.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/FeatureAttributionPage.test.tsx`
Expected: PASS (3/3).

- [ ] **Step 6: Add the route and entry point**

In `frontend/src/App.tsx`, add the import and route:
```tsx
import FeatureAttributionPage from "./pages/FeatureAttributionPage";
...
          <Route path="/models/:id" element={<ModelDetailPage />} />
          <Route path="/models/:id/attribution" element={<FeatureAttributionPage />} />
```

In `frontend/src/pages/ModelDetailPage.tsx`, add a link near the model identity header (after the existing `<span className="identity-meta-item">Imported ...</span>` block, around line 86):
```tsx
        <Link to={`/models/${model.id}/attribution`} className="btn">
          Explain a prediction
        </Link>
```
(`Link` is already imported from `react-router-dom` at the top of this file — no new import needed.)

- [ ] **Step 7: Run the full frontend test suite to check for regressions**

Run: `cd frontend && npx vitest run`
Expected: no new failures.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/FeatureAttributionPage.tsx frontend/src/pages/FeatureAttributionPage.test.tsx frontend/src/pages/ModelDetailPage.tsx frontend/src/App.tsx
git commit -m "feat: add FeatureAttributionPage and ModelDetailPage entry point"
```

---

## Spec coverage check

- §1 Architecture → Tasks 1, 4, 5, 6 (package structure, reuse list).
- §2 Persistence → Task 1 (table/migration), Task 2 (EvidenceRef docstring).
- §3 API → Task 8.
- §4 SHAP vs LIME → Task 5 (SHAP only), Task 8 (LIME rejected at API layer).
- §5 Evidence semantics → Task 4 (`FeatureAttributionRead.limitations` default, no confidence field).
- §6 Frontend → Task 9.
- §7 Security/performance → Global Constraints (no model cache, sync v1); text length cap enforced in Task 4's `AttributionRunRequest`.
- §8 Future extensibility → Task 4 (`method: Literal["shap","lime"]` kept open); `modality` discriminator deliberately **not added in v1** — no image/tabular backend exists yet to dispatch to, and adding an unused field would be speculative. Flagging this as a deviation from spec §8's literal text: add `modality: Literal["text"]` only when a second modality is actually being built, not preemptively.

## Execution options

Plan complete and saved to `docs/superpowers/plans/2026-09-15-feature-attribution.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
