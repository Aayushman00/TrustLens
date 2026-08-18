"""Domain enums persisted as PostgreSQL ENUM types."""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class EvaluationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PROBES_COMPLETED = "PROBES_COMPLETED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


class EvaluationMode(str, enum.Enum):
    AI_ASSISTED = "AI_ASSISTED"
    AI_AUTONOMOUS = "AI_AUTONOMOUS"


class FriesDimension(str, enum.Enum):
    FAIRNESS = "FAIRNESS"
    ROBUSTNESS = "ROBUSTNESS"
    INTEGRITY = "INTEGRITY"
    EXPLAINABILITY = "EXPLAINABILITY"
    SAFETY = "SAFETY"
