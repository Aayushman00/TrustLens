# TrustLens — Feature Suite

Snapshot of what is actually implemented in the repo today (verified against code, not aspiration). See `README.md` for methodology/roadmap framing; this doc is a flat feature list.

## Auth & access
- JWT login/refresh (15 min access / 7 day refresh, rotation on refresh).
- Roles: researcher / reviewer / admin (RBAC on routes).
- `GET /v1/auth/me`.

## Model intake
- `POST /v1/models/import-hf` — Hugging Face Hub **metadata-only** import (card, tags, license, file list, revision, checksum). No weight download at import time.
- Upsert on re-import (refreshes metadata, same row/id).
- Scope guards (ADR 0012): no crawling/search/index endpoints, no local-file/upload path for **models**, no weight download at import.
- Typed error codes: `INVALID_MODEL_REF`, `VALIDATION_ERROR`, `MODEL_NOT_FOUND`, `HF_AUTH_REQUIRED`, `HF_HUB_UNAVAILABLE`.

## Dataset intake
- `DatasetIntakeForm` — local CSV upload wired in for evaluation drafts (separate from model import, which stays Hub-only).
- Column role mapping (`ColumnRoleMappingForm`) and documentation-source capture (`DocumentationSourceForm`) as part of draft creation.

## Evaluation pipeline
- Async evaluations via Celery (`POST /v1/evaluations` → `trustlens.evaluate_model`).
- Five FRIES probes run in order: Fairness → Robustness → Integrity → Explainability → Safety.
- Per-probe **first-class status** (`ProbeEvaluationStatus`): `EVALUATED`, `INSUFFICIENT_EVIDENCE`, `NOT_APPLICABLE`, `SKIPPED`, `FAILED`, `PROXY`.
- Immutable `methodology_version` stamped per evaluation at creation (`v2-per-dimension-2026`, current; `pre-v1-fixed-5dim` legacy sentinel), copied verbatim into the report.
- Execution device (CPU/CUDA, GPU name or fallback reason) persisted per evaluation and shown on the detail page.

### Probes
| Dimension | Evidence | Runs imported model? |
|---|---|---|
| Fairness | Adult Census tabular subset; DPD, EOD, subgroup F1 spread | No — sklearn LogisticRegression proxy |
| Robustness | Pinned NLP subset; clean vs char-swap accuracy | Yes, for text-classification models (CPU) |
| Integrity | Hub identity/disclosure checklist (`I-INT-*` risks), optional injected hash compare | No weight download; hash compare only when both hashes supplied |
| Explainability | Model-card ATX section coverage | Metadata only |
| Safety | Mandatory disclosure checklist + high-impact claim flags | Metadata only |

## O/S/D assessment
- Two engines, orthogonal to workflow mode:
  - **`deterministic`** (default) — abstains; no O/S/D generated; FRIES withheld.
  - **`legacy_heuristic`** (admin-only, top-level `probe_config.assessment_engine`) — `HeuristicOSDAgent` bands metrics into O/S/D (`PROPOSED / REQUIRES VALIDATION`, not an LLM).
- Heuristic agent abstains (`None`) on missing evidence for Fairness, Robustness, and Integrity; Explainability and Safety still fall back to a fixed empty-card band `(2, 2, 3)`.
- Two workflow modes as **human-review gates** (not LLM interpretation): `AI_AUTONOMOUS` (may finalize without reviewer) and `AI_ASSISTED` (stops at `AWAITING_REVIEW` for a reviewer to record/edit O/S/D).
- OSD review UI for reviewers to inspect and edit proposed bands before finalize.

## Confidence
- Uncalibrated evidence-strength geometric mean (`data_quality`, `probe_reliability`, `evidence_completeness`) per dimension and overall — not correctness, not O/S/D.
- Under `methodology_version = v2-per-dimension-2026`, dimensions marked `NOT_APPLICABLE` are excluded from the overall figure (still shown as `None` per-dimension). Legacy evaluations keep the old always-folded-in behavior byte-for-byte.

## FRIES scoring
- Original FRIES math: `T_risk = ∛(O × S × D)`, veto on any 0, `T = 10` at O=S=D=10.
- Aspect score = mean of selected risk scores; overall FRIES = weighted sum (equal `0.2` weights by default).
- Frozen test vectors in `shared/scoring/fixtures/fries_test_vectors.json`.
- Only runs when a complete O/S/D triple exists (legacy/admin engine, or human-supplied).
- No partial/reweighted FRIES yet — an aspect with no risks scores `0`, not withheld.

## Reports & leaderboard
- Canonical `report_v1` JSON in MinIO (append-only versions) whenever FRIES was scored; PDF is a projection.
- Finalized-but-withheld evaluations return `409`, not "not finalized yet".
- Leaderboard: private by default; owner/admin can publish after `FINALIZED` **and** a FRIES score exists.

## Evaluation timeline (recent work, this branch)
- Second-precision timestamp formatting.
- Gap-since-previous and attempt-numbering helpers.
- `evaluation_requeued` event labeled and summarized.
- Timeline UI renders gaps, attempt dividers, expandable detail rows, and a live badge.

## Evidence store
- SHA-256 artifact hashes in MinIO, scoped per evaluation, append-only.

## Not yet implemented (see README roadmap for full detail)
- Resource checker / compatibility states (`SUPPORTED`/`CONSTRAINED`/`UNSUPPORTED`/`UNKNOWN`) and pre-download runtime estimate.
- Shared `InferenceBackend` (only the robustness NLP runner currently loads the imported model).
- Fairness evaluation of the actual imported model (still a tabular proxy).
- Structured O/S/D mapping traces (`rule_id`, band, rationale) — risks are still one triple per dimension.
- Partial/reweighted FRIES scoring when an aspect has no risks.
- Safety behavioral test suite (currently governance checklist only).
- `llm_assisted` O/S/D mode (not implemented; explicitly out of scope for the current professor-comparison ask, see project discussion).
