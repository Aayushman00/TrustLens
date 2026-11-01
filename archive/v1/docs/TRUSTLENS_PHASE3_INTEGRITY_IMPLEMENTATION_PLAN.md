# TrustLens Phase 3 — Integrity Implementation Plan

This document is the approved implementation plan for **Phase 3 Integrity only**.

---

# 1. Phase 3 Objective

Make Integrity a **Layer-A evidence probe** in the same shape as Fairness and Robustness:

**objective evidence → validity/status → named risk → O/S/D only if explicitly validated → FRIES later**

Integrity v1 must:

1. Collect structured identity / provenance / disclosure evidence from the **already-imported Hub snapshot**.
2. Distinguish **EVALUATED**, **INSUFFICIENT_EVIDENCE**, and **FAILED** (and document why N/A and SKIPPED are unused for HF models).
3. Detect a **narrow, named** Integrity risk set with explicit claim boundaries.
4. Produce **no** deterministic O/S/D, **no** `osd_proposals`, **no** FRIES.
5. Persist an auditable evidence artifact.
6. Integrate as a **read-only metadata source** for `DeterministicOSDMapper`.
7. Leave `HeuristicOSDAgent` and `fries.py` untouched.

Integrity after Phase 3 answers: *what did TrustLens record about this artifact's Hub identity and disclosure, and (only if both hashes exist) did local bytes match a stated trusted reference?* It does **not** answer whether the model was tampered with, is legally licensed, is reproducible, or has a true training lineage.

---

# 2. Authoritative Methodology

**Primary:** [`docs/TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md`](TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md) §3 (locked architecture), §6 (Integrity), §9–11 (consistency / KEEP-ADD-REMOVE).

**Architectural reference (pattern only, do not rewrite):** Fairness pairing + Robustness Phase 2 (`aspect_scoring`, `probe_status`, `risks_triggered`, `scored_risk_id`, `reliability.failed_gates`, `proposed_mapping: false`, empty `osd_proposals`).

**Not authoritative:** [`docs/TRUSTLENS_IMPLEMENTATION_BLUEPRINT.md`](TRUSTLENS_IMPLEMENTATION_BLUEPRINT.md), README Integrity score text, historical `integrity_score_0_10` / `proposed_mapping: True`.

**Out of scope to change:** [`backend/app/scoring/fries.py`](backend/app/scoring/fries.py), FRIES fixtures, [`HeuristicOSDAgent`](backend/app/osd/agent.py).

There is **no** settled `tl-methodology-v1.0` Integrity chapter. Phase 3 stamps Integrity artifacts with **`tl-integrity-v1.0`**, plus `methodology_basis: "TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md"`.

---

# 3. Current Implementation Audit

(See git history pre-Phase-3 for Phase 10 checklist behavior: six checks, `integrity_score_0_10`, `proposed_mapping: True`, default `EVALUATED`, misnamed `checksum_recorded`.)

---

# 4. Target Integrity Scope

**In v1:** identity recording, provenance/disclosure, conditional cryptographic identity (schema + injected comparison only).

**Out of v1:** tampering, intent, true lineage, true reproducibility, generic 0–10 score, FRIES/O/S/D.

---

# 5. Final Integrity Risk Taxonomy

| ID | Role |
| -- | ---- |
| `I-INT-REV-UNPINNED` | Named Layer-A risk |
| `I-INT-MANIFEST-MISSING` | Named Layer-A risk |
| `I-INT-LICENSE-UNDISCLOSED` | Named Layer-A risk |
| `I-INT-BYTES-DIVERGE` | Named Layer-A risk (conditional) |
| `I-INT-HASH-UNVERIFIED` | Claim-scope gate / limitation, **not** a scored risk |

`scored_risk_id` is always `null`. Reproducibility keywords are evidence-only (no `I-INT-REPRO-UNDISCLOSED`).

---

# 6. Evidence Model

Core artifact fields: `methodology_version`, `methodology_basis`, `status`, `aspect_scoring`, `risks_triggered`, `identity`, `disclosure`, `checks`, `claims`, `claim_boundary`, `reliability`, `limitations`, `proposed_mapping: false`, `osd_proposals: []`. No `integrity_score_0_10`.

Check rename: `checksum_recorded` → `files_listing_recorded`; fingerprint field `files_listing_fingerprint`.

---

# 7. Status / Gate Semantics

- **EVALUATED:** at least one of {revision, files, card}; hash not performed does not demote whole probe.
- **INSUFFICIENT_EVIDENCE:** no revision AND empty files AND empty card (`G-INT-IDENTITY-EMPTY`).
- **FAILED:** evidence store / unexpected probe failure.
- Hash claim insufficient is claim-level only (`G-INT-HASH-REF-MISSING`, `G-INT-HASH-LOCAL-MISSING`).

---

# 8. Trusted Hash / Artifact Verification Design

Production: **deferred** (no weight download). Schema always emitted; comparison runs only when `probe_config.extra.integrity` supplies both `trusted_reference` and `local_artifact_hash`. Algorithm: SHA-256 via `hashes_equal`.

---

# 9. Confidence Engine Changes

Integrity `_integrity_factors` uses evidence-strength semantics (not checklist pass-rate). Hash-not-performed does not collapse metadata confidence.

---

# 10. Deterministic OSD Integration

Mapper copies Integrity metadata keys read-only; no O/S/D, no `osd_proposals`.

---

# 11. API / Serialization / Report Changes

Remove `integrity_score_0_10` from new runs. Keep `proposed_mapping: false`. Historical JSON untouched.

---

# 12. Backward Compatibility / Historical Data

No migration of persisted probe rows. Legacy heuristic still reads `checks.*.pass`.

---

# 13. Detailed File-by-File Change Plan

| File | Change |
| ---- | ------ |
| `backend/app/probes/integrity_stats.py` | New constants |
| `backend/app/probes/integrity_eval.py` | Pure evaluation |
| `backend/app/probes/integrity.py` | Layer-A probe wiring |
| `backend/app/confidence/engine.py` | `_integrity_factors` only |
| `backend/app/osd/deterministic.py` | Metadata key copy |
| Tests + README | Rewrite assertions |

---

# 14. Test Plan

Unit, probe, integration, and legacy-heuristic isolation tests per Phase 3 sign-off list (22 scenarios).

---

# 15. Implementation Order

1. integrity_stats + integrity_eval
2. integrity.py probe wiring
3. confidence engine
4. deterministic OSD keys
5. tests + README

---

# 16. Definition of Done

New Integrity runs emit Layer-A artifact with named `I-INT-*` risks, no fake score, deterministic O/S/D null, confidence not pass-rate, heuristic agent unchanged.

---

# 17. Explicit Non-Goals

Weight download, FRIES, O mapping, tamper science, Explainability/Safety phases, HeuristicOSDAgent edits.

---

# 18. Open Decisions

Hub `files_metadata` LFS enrichment at import: **deferred**.

---

# 19. Risk / Regression Analysis

Checklist rename must preserve `checks.*.pass` for legacy heuristic. README and CI tests updated to remove 0–10 score assertions.

---

# 20. FINAL RECOMMENDATION

Implement Integrity as metadata identity + disclosure with optional injected hash comparison. Four named detections plus HASH-UNVERIFIED gate. Remove fake 0–10 score and `proposed_mapping: true`.

---

## Plain answers

1. **Measures:** Hub identity recording, structured license disclosure, card presence, repro language, conditional hash compare when both hashes supplied.
2. **Risks:** `I-INT-REV-UNPINNED`, `I-INT-MANIFEST-MISSING`, `I-INT-LICENSE-UNDISCLOSED`, conditional `I-INT-BYTES-DIVERGE`; `I-INT-HASH-UNVERIFIED` is a gate only.
3. **Impossible:** tampering, intent, true lineage/reproducibility, generic integrity score, validated O.
4. **Removed from new runs:** `integrity_score_0_10`, equal-weight scoring, `proposed_mapping: true`, pass-rate confidence, `checksum_recorded` name.
5. **Preserved:** per-check pass/detail, anti-gaming license, files list, listing fingerprint (renamed), MinIO artifacts.
6. **Metadata-only:** default production path; hash fields `not_performed` without injection.
7. **Hash verification:** deferred for downloads; schema + injected comparison in tests/operators.
8. **Incomplete evidence:** empty identity → INSUFFICIENT; missing hash inputs → crypto claim insufficient only.
9. **F/R consistency:** same status enum, `proposed_mapping: false`, named risks without O, mapper read-only.
10. **Sign-off:** full test suite per §14.
