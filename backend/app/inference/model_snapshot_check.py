"""Worker-side enforcement of the Global Constraint that resolved_model_sha/
model_label_snapshot are frozen once at draft/Evaluation confirmation and
must be hard-verified against the actually-reloaded model at execution time
(never trusted from intake alone)."""

from __future__ import annotations

from app.inference.base import LoadedModelInfo
from app.inference.errors import UNSUPPORTED_MODEL, InferenceError
from app.schemas.evaluation_contract_v2 import ModelLabelSnapshot


def verify_loaded_model_matches_snapshot(
    loaded: LoadedModelInfo, snapshot: ModelLabelSnapshot
) -> None:
    """Hard-fail if the freshly loaded model disagrees with the frozen snapshot."""
    if loaded.num_labels is not None and loaded.num_labels != snapshot.num_labels:
        raise InferenceError(
            UNSUPPORTED_MODEL,
            "loaded model num_labels disagrees with frozen model_label_snapshot",
            details={"expected": snapshot.num_labels, "got": loaded.num_labels},
        )
    if loaded.id2label:
        normalized_expected = {
            int(k): str(v).strip().lower() for k, v in snapshot.id2label.items()
        }
        normalized_got = {
            int(k): str(v).strip().lower() for k, v in loaded.id2label.items()
        }
        for idx, name in normalized_got.items():
            expected_name = normalized_expected.get(idx)
            if expected_name is not None and expected_name != name:
                raise InferenceError(
                    UNSUPPORTED_MODEL,
                    "loaded model id2label disagrees with frozen model_label_snapshot",
                    details={"index": idx, "expected": expected_name, "got": name},
                )
