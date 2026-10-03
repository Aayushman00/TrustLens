"""L5: L4.1 confirmatory fairness run (frozen pre-registration
docs/superpowers/plans/2026-10-03-round3-L4.1-confirmatory-prereg.md).

Runs the production FairnessProbe (binary EOD rule, tl-fairness-binary-v1.2)
in-process with real LocalHFBackend inference on the new eval set, for the
clean control, the nested fairness flips and the existing 2-label reference.
No LLM stage, no API; evidence-level hypotheses only.

Usage (from backend/, after prepare_flawed_suite_data/train_flawed_suite --fairness-confirm)::

    python -m app.scripts.run_fairness_confirm --root ../results/fairness_confirm_20261003
"""

from __future__ import annotations

import argparse
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.db.models import DatasetContent
from app.inference.base import InferenceBackend
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.fairness import FairnessProbe
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    LabelMappingEntry,
    ModelLabelSnapshot,
)
from app.schemas.probe_config import ProbeConfigV1
from app.scripts.compare_ground_truth import evidence_flag_one, spearman
from app.scripts.prepare_flawed_suite_data import CONFIRM_CONTROLS, REPO_ROOT, SUITE_DIR, validate_out_dir
from app.storage.evidence_store import DatasetContentStore, EvidenceStore

DEFAULT_ROOT = REPO_ROOT / "results" / "fairness_confirm_20261003"
REFERENCE = "reference_toxicbert_2label"
_BUCKET = "fairness-confirm"


class _MemClient:
    """In-memory object client (put_object/get_object) for one process."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_kw: Any) -> dict:  # noqa: N803
        self.objects[(Bucket, Key)] = bytes(Body)
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict:  # noqa: N803
        data = self.objects[(Bucket, Key)]

        class _Body:
            def read(self) -> bytes:
                return data

        return {"Body": _Body()}


class _MemSession:
    """Resolves the one DatasetContent row the probe looks up."""

    def __init__(self, row: DatasetContent) -> None:
        self._row = row

    def get(self, _cls: type, key: uuid.UUID) -> DatasetContent | None:
        return self._row if key == self._row.id else None


LABEL_MAPPING = [LabelMappingEntry(dataset_value="0", model_label_index=0),
                 LabelMappingEntry(dataset_value="1", model_label_index=1)]


def in_memory_context(
    model_dir: Path,
    csv_bytes: bytes,
    *,
    contracts: Callable[[uuid.UUID], dict[str, Any]],
    probe_config: ProbeConfigV1 | None = None,
    model_metadata: dict[str, Any] | None = None,
) -> ProbeContext:
    """ProbeContext for a local model and CSV, with in-memory content-addressed
    dataset and evidence stores. ``contracts(content_id)`` returns the
    EvaluationContractV2 per-dimension sections (fairness/robustness/safety)."""
    client = _MemClient()
    store = DatasetContentStore(client, _BUCKET)  # type: ignore[arg-type]
    uri, digest = store.put(csv_bytes, format="csv")
    content = DatasetContent(
        id=uuid.uuid4(), content_hash=digest.removeprefix("sha256:"), storage_uri=uri,
        byte_size=len(csv_bytes), format="csv", row_count=csv_bytes.count(b"\n") - 1, columns=[],
    )
    id2label = json.loads((model_dir / "config.json").read_text(encoding="utf-8")).get("id2label") or {}
    snapshot = ModelLabelSnapshot(num_labels=2, id2label={int(k): v for k, v in id2label.items()})
    ref = str(model_dir)
    # Local checkpoints have no HF revision; same "local" sentinel run_flawed_suite_eval registers.
    contract = EvaluationContractV2(
        model_ref=ref, model_revision="local", resolved_model_sha="local",
        model_label_snapshot=snapshot, **contracts(content.id),
    )
    return ProbeContext(
        evaluation_id=uuid.uuid4(), model_ref=ref, model_metadata=model_metadata or {},
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=EvidenceStore(client, _BUCKET),  # type: ignore[arg-type]
        evaluation_contract=contract, dataset_content_store=store,
        session=_MemSession(content),  # type: ignore[arg-type]
    )


def probe_once(model_dir: Path, csv_bytes: bytes, *, backend: InferenceBackend | None = None) -> ProbeOutput:
    """One FairnessProbe run under the contract run_flawed_suite_eval submits."""
    ctx = in_memory_context(model_dir, csv_bytes, contracts=lambda cid: {"fairness": FairnessContractV2(
        dataset_content_id=cid, text_column="text", target_column="label", sensitive_column="identity_ref",
        label_mapping=LABEL_MAPPING, min_group_n=30, positive_label_index=1,
    )})
    return FairnessProbe(inference=backend).run(ctx)


_REPEAT_KEYS = ("equal_opportunity_difference", "eopp_ci", "fairness_finding", "aspect_scoring", "risks_triggered")


def summarize(outputs: list[Any]) -> dict[str, Any]:
    """Pre-registered per-model record; first run's evidence plus per-run lists."""
    runs = [o.metric_values for o in outputs]
    m = runs[0]
    groups = m.get("groups") or {}
    positives = (m.get("eligibility") or {}).get("positives") or {}
    flags = [evidence_flag_one("FAIRNESS", r, None) for r in runs]
    return {
        "group_sizes": {g: v["n"] for g, v in groups.items()},
        "group_positive_label_rates": {g: round(positives[g] / v["n"], 6) for g, v in groups.items() if g in positives},
        "group_tpr": {g: v.get("tpr") for g, v in groups.items()},
        "group_fpr": {g: v.get("fpr") for g, v in groups.items()},
        **{k: m.get(k) for k in (
            "demographic_parity_difference", "equal_opportunity_difference", "eopp_ci", "fpr_gap",
            "subgroup_f1_spread", "equalized_odds_difference", "excess_dpd_v1", "label_rate_gap",
            "dp_ci", "fairness_finding", "risks_triggered", "aspect_scoring", "methodology_version",
        )},
        "status": str(getattr(outputs[0].status, "value", outputs[0].status)),
        "status_reason": outputs[0].status_reason,
        "probe_flags": outputs[0].flags,
        "equal_opportunity_difference_per_run": [r.get("equal_opportunity_difference") for r in runs],
        "fairness_finding_per_run": [r.get("fairness_finding") for r in runs],
        "aspect_scoring_per_run": [r.get("aspect_scoring") for r in runs],
        "flags_per_run": flags,
        "flagged": sum(flags) * 2 > len(flags),
        "repeatable": all(r.get(k) == m.get(k) for r in runs for k in _REPEAT_KEYS),
    }


def check_hypotheses(table: dict[str, dict[str, Any]], rates: dict[str, float]) -> dict[str, Any]:
    """H1-H4 under the decision criteria frozen in the pre-registration."""
    flagged_controls = [c for c in CONFIRM_CONTROLS if table[c]["flagged"]]
    targets = [n for n, r in sorted(rates.items(), key=lambda kv: kv[1]) if r >= 0.4]
    recall = sum(table[n]["flagged"] for n in targets) / len(targets)
    levels = [(r, table[n]["equal_opportunity_difference"]) for n, r in sorted(rates.items(), key=lambda kv: kv[1])
              if table[n]["equal_opportunity_difference"] is not None]
    rho = spearman([r for r, _ in levels], [e for _, e in levels]) if len(levels) >= 3 else None
    decreases = sum(b[1] < a[1] for a, b in zip(levels, levels[1:], strict=False))
    return {
        "H1": {"holds": not flagged_controls, "controls": CONFIRM_CONTROLS, "flagged_controls": flagged_controls},
        "H2": {"holds": recall == 1.0, "models": targets, "recall": recall,
               "flagged": {n: table[n]["flagged"] for n in targets}},
        "H3": {"holds": rho is not None and rho > 0, "spearman_rho": rho, "n_levels": len(levels),
               "levels": levels, "adjacent_decreases": decreases,
               "strictly_monotone": rho is not None and abs(rho - 1.0) < 1e-12},
        "H4": {"per_model": {
            n: {"insufficient_evidence": row["fairness_finding_per_run"].count("INSUFFICIENT_EVIDENCE"),
                "mapping_blocked": row["aspect_scoring_per_run"].count("mapping_blocked")}
            for n, row in table.items()
        }},
    }


def _markdown(table: dict[str, dict[str, Any]], hyp: dict[str, Any], rates: dict[str, float]) -> str:
    def f(x: Any) -> str:
        return "—" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))

    lines = [
        "# L5 — L4.1 confirmatory fairness validation (seed 20261003)", "",
        "Rule: v6-eod-fairness-risk-2026 / tl-fairness-binary-v1.2, unchanged (ε = 0.02, wide-CI 0.15, B = 1000).",
        "", "| model | flip rate | n (g0/g1) | pos rate (g0/g1) | DPD | EOD | EOD CI | FPR gap | F1 spread | finding | risks | aspect | flagged | repeatable |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for n, s in table.items():
        ci = s["eopp_ci"] or {}
        lines.append(
            f"| {n} | {rates.get(n, 'control')} | {'/'.join(str(v) for v in s['group_sizes'].values())} | "
            f"{'/'.join(f(v) for v in s['group_positive_label_rates'].values())} | {f(s['demographic_parity_difference'])} | "
            f"{f(s['equal_opportunity_difference'])} | [{f(ci.get('ci_lower'))}, {f(ci.get('ci_upper'))}] | {f(s['fpr_gap'])} | "
            f"{f(s['subgroup_f1_spread'])} | {s['fairness_finding']} | {s['risks_triggered']} | {s['aspect_scoring']} | "
            f"{s['flagged']} | {s['repeatable']} |"
        )
    lines += ["", "## Hypotheses (frozen criteria)", "", "```json", json.dumps(hyp, indent=2), "```", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args(argv)
    out = validate_out_dir(args.root / "analysis")
    gt = json.loads((args.root / "ground_truth.json").read_text(encoding="utf-8"))
    csv_bytes = (args.root / "data" / "eval_set.csv").read_bytes()
    rates = {n: e["flip_rate"] for n, e in gt["models"].items() if "flip_rate" in e}
    dirs = {n: args.root / "models" / n for n in rates} | {REFERENCE: SUITE_DIR / "models" / REFERENCE}
    (out / "raw").mkdir(parents=True)
    table: dict[str, dict[str, Any]] = {}
    for name, model_dir in dirs.items():
        outputs = []
        for i in range(args.runs):
            o = probe_once(model_dir, csv_bytes)
            (out / "raw" / f"{name}__run{i + 1}.json").write_text(
                json.dumps({"status": str(o.status), "status_reason": o.status_reason, "flags": o.flags,
                            "metric_values": o.metric_values}, indent=2, default=str), encoding="utf-8")
            outputs.append(o)
        table[name] = summarize(outputs)
        print(name, table[name]["equal_opportunity_difference"], table[name]["fairness_finding"])
    hyp = check_hypotheses(table, rates)
    (out / "analysis.json").write_text(json.dumps({"rates": rates, "models": table, "hypotheses": hyp}, indent=2,
                                                  default=str), encoding="utf-8")
    (out / "analysis.md").write_text(_markdown(table, hyp, rates), encoding="utf-8")


if __name__ == "__main__":
    main()
