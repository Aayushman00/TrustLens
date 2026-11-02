"""EvidenceItem v2 (DESIGN_SYNTHESIS 5.1). Every probe emits it, TrustBench reads it."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.posterior.rates import bonferroni_level, jeffreys_interval

_APPLICABILITY = re.compile(r"^(applicable|(not_applicable|insufficient_evidence)\(.+\))$", re.S)
_MAX_MIN = re.compile(r"^max[-_ ]?min$", re.I)


class Estimand(BaseModel):
    name: str
    scale: Literal["rate", "difference", "bool", "count"]
    direction: Literal["higher_is_worse", "higher_is_better"]
    reference: str | None = None  # "pooled" | "<group>" | None; signed, never max-min

    @field_validator("reference")
    @classmethod
    def _no_max_min(cls, v: str | None) -> str | None:
        if v is not None and _MAX_MIN.match(v.strip()):
            raise ValueError("reference must be signed (pooled or a group), never max-min")
        return v


class Counts(BaseModel):
    k: int
    n: int

    @model_validator(mode="after")
    def _bounds(self) -> Counts:
        if self.n < 1 or not 0 <= self.k <= self.n:
            raise ValueError("counts need n >= 1 and 0 <= k <= n")
        return self


class Uncertainty(BaseModel):
    method: Literal["jeffreys", "wilson", "newcombe", "paired_bootstrap", "exact", "none"]
    level: float
    interval: tuple[float, float]
    draws: list[float] | None = Field(default=None, max_length=1000)


class Look(BaseModel):
    index: int
    max_looks: int
    alpha_spent: float


class EvidenceInputs(BaseModel):
    model_ref: str  # "<repo>@<revision>"
    dataset_sha256: str
    config: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    methodology_version: str
    instrument_hashes: dict[str, str] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    id: str
    kind: Literal["property", "disclosure", "legacy"]  # legacy = v1 comparator (G1 only)
    estimand: Estimand
    estimate: float | None = None
    n: int
    counts: Counts | None = None
    uncertainty: Uncertainty | None = None
    look: Look
    applicability: str = "applicable"
    tier: Literal["A", "B"] | None = None
    inputs: EvidenceInputs
    evidence_ref: str | None = None

    @field_validator("applicability")
    @classmethod
    def _applicability(cls, v: str) -> str:
        if not _APPLICABILITY.match(v):
            raise ValueError("applicability must be applicable, not_applicable(<reason>) or insufficient_evidence(<reason>)")
        return v

    @model_validator(mode="after")
    def _rules(self) -> EvidenceItem:
        if self.tier is not None and not self.id.startswith("int."):
            raise ValueError("tier is only for integrity items (id starts with 'int.')")
        u = self.uncertainty
        if u is not None and u.draws is not None and self.estimand.scale != "difference":
            raise ValueError("draws only allowed for difference estimands")
        if self.applicability != "applicable":
            return self  # estimate/counts/uncertainty may be absent
        if self.estimate is None or u is None:
            raise ValueError("applicable items need estimate and uncertainty")
        if self.kind == "legacy":
            return self  # v1 comparators keep v1's uncertainty method (Task 12)
        if self.estimand.scale == "rate":
            if self.counts is None:
                raise ValueError("rate estimands require counts")
            if u.method == "paired_bootstrap":
                raise ValueError("rate estimands may not use paired_bootstrap")
        return self

    @classmethod
    def rate(
        cls,
        id: str,
        k: int,
        n: int,
        *,
        direction: Literal["higher_is_worse", "higher_is_better"],
        reference: str | None = None,
        level: float = 0.95,
        look: Look = Look(index=1, max_looks=3, alpha_spent=0.05 / 3),
        inputs: EvidenceInputs,
    ) -> EvidenceItem:
        counts = Counts(k=k, n=n)
        adj = bonferroni_level(level, look.max_looks)
        return cls(
            id=id,
            kind="property",
            estimand=Estimand(name=id, scale="rate", direction=direction, reference=reference),
            estimate=k / n,
            n=n,
            counts=counts,
            uncertainty=Uncertainty(method="jeffreys", level=adj, interval=jeffreys_interval(k, n, adj)),
            look=look,
            inputs=inputs,
        )
