"""Run all FRIES probes and persist ``probe_results`` (Phase 9; confidence engine Phase 15)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.confidence.engine import refine
from app.db.repositories.probe_result import ProbeResultRepository
from app.probes.base import Probe, ProbeContext, ProbeOutput
from app.probes.errors import ProbeError
from app.probes.registry import ProbeRegistry, default_registry
from app.schemas.internal import EvaluateModelPayload
from app.schemas.probe_config import parse_probe_config
from app.storage.evidence_store import EvidenceStore, EvidenceStoreError

logger = logging.getLogger("trustlens.probes")


def validate_probe_output(probe: Probe, output: ProbeOutput) -> None:
    """Hard-fail invalid probe outputs to preserve evaluation integrity."""
    if output.dimension != probe.dimension:
        raise ProbeError(
            f"probe output dimension mismatch: expected={probe.dimension.value} "
            f"got={output.dimension.value}"
        )
    if not (0.0 <= output.confidence <= 1.0):
        raise ProbeError(
            f"probe confidence out of range [0,1]: {output.confidence} "
            f"dimension={output.dimension.value}"
        )
    if not output.evidence_refs:
        raise ProbeError(
            f"probe output missing evidence_refs dimension={output.dimension.value}"
        )
    if not isinstance(output.metric_values, dict):
        raise ProbeError(
            f"probe metric_values must be a dict dimension={output.dimension.value}"
        )


def run_all_probes(
    session: Session,
    payload: EvaluateModelPayload,
    *,
    model_metadata: dict[str, Any],
    evidence_store: EvidenceStore,
    registry: ProbeRegistry | None = None,
    model_revision: str | None = None,
    model_checksum: str | None = None,
) -> list[ProbeOutput]:
    """Run F→R→I→E→S; persist each via ProbeResultRepository; return outputs.

    Raises:
        ProbeError: invalid output or probe execution failure.
        EvidenceStoreError: MinIO/store failures from probes.
        ValidationError: invalid ``probe_config`` schema.
    """
    probe_config = parse_probe_config(payload.probe_config)
    reg = registry if registry is not None else default_registry()
    probes_repo = ProbeResultRepository(session)
    ctx = ProbeContext(
        evaluation_id=payload.evaluation_id,
        model_ref=payload.model_ref,
        model_metadata=model_metadata or {},
        probe_config=probe_config,
        evidence_store=evidence_store,
        model_revision=model_revision,
        model_checksum=model_checksum,
    )
    outputs: list[ProbeOutput] = []
    for probe in reg.all_ordered():
        dim = probe.dimension.value
        logger.info(
            "probe_start evaluation_id=%s dimension=%s",
            payload.evaluation_id,
            dim,
        )
        try:
            output = probe.run(ctx)
        except EvidenceStoreError:
            raise
        except ProbeError:
            raise
        except Exception as exc:
            raise ProbeError(
                f"probe {dim} failed: {exc}"
            ) from exc
        validate_probe_output(probe, output)
        # Phase 15: Confidence Engine overwrites the probe-local heuristic with
        # factorized confidence; factors persist in metric_values for re-reads.
        dim_conf = refine(
            output.dimension,
            metric_values=output.metric_values,
            flags=output.flags,
            evidence_refs=output.evidence_refs,
        )
        output.metric_values = {
            **output.metric_values,
            "confidence_factors": dim_conf.factors.model_dump(),
        }
        output.confidence = dim_conf.confidence
        probes_repo.create(
            evaluation_id=payload.evaluation_id,
            dimension=output.dimension,
            metric_values=output.metric_values,
            confidence=output.confidence,
            evidence_refs=[ref.model_dump(mode="json") for ref in output.evidence_refs],
        )
        outputs.append(output)
        logger.info(
            "probe_complete evaluation_id=%s dimension=%s confidence=%s evidence_count=%s",
            payload.evaluation_id,
            dim,
            output.confidence,
            len(output.evidence_refs),
        )
    return outputs
