"""Database package — ORM models for TrustLens (Phase 3).

Worker note (Phase 7): models live in this package (`app.db`). The worker can
import them by installing the backend package editable, or by adding
`backend/` to ``PYTHONPATH``. Do not duplicate ORM definitions in the worker.
"""

from app.db.base import Base
from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension, UserRole
from app.db.models import (
    AttackFlag,
    Evaluation,
    FinalScore,
    HumanReview,
    Model,
    OsdAgentOutput,
    ProbeResult,
    Report,
    User,
)

__all__ = [
    "AttackFlag",
    "Base",
    "Evaluation",
    "EvaluationMode",
    "EvaluationStatus",
    "FinalScore",
    "FriesDimension",
    "HumanReview",
    "Model",
    "OsdAgentOutput",
    "ProbeResult",
    "Report",
    "User",
    "UserRole",
]
