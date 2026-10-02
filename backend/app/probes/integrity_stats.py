"""Integrity probe constants (tl-integrity-v1.1)."""

from __future__ import annotations

# v1.2 (round 3, L7): the hash identity covers the whole artifact set (single or
# sharded weights + loader files) against an authoritative manifest; statuses
# VERIFIED / MISMATCH / INCOMPLETE / UNPINNED / UNSUPPORTED in artifact_verification.
METHODOLOGY_VERSION = "tl-integrity-v1.2"
METHODOLOGY_BASIS = "TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md"

RISK_REV_UNPINNED = "I-INT-REV-UNPINNED"
RISK_MANIFEST_MISSING = "I-INT-MANIFEST-MISSING"
RISK_LICENSE_UNDISCLOSED = "I-INT-LICENSE-UNDISCLOSED"
RISK_BYTES_DIVERGE = "I-INT-BYTES-DIVERGE"
RISK_FILES_LISTING_DRIFT = "I-INT-LISTING-DRIFT"

GATE_HASH_UNVERIFIED = "I-INT-HASH-UNVERIFIED"
G_IDENTITY_EMPTY = "G-INT-IDENTITY-EMPTY"
G_HASH_REF_MISSING = "G-INT-HASH-REF-MISSING"
G_HASH_LOCAL_MISSING = "G-INT-HASH-LOCAL-MISSING"
G_LISTING_UNVERIFIED = "G-INT-LISTING-UNVERIFIED"
G_ARTIFACT_INCOMPLETE = "G-INT-ARTIFACT-INCOMPLETE"

CLAIM_LISTING_DRIFT = (
    "The Hub file listing at this revision differs from the listing recorded "
    "at import time. This does not establish unauthorized tampering, Hub "
    "compromise, or malicious intent — a branch-style revision can legitimately "
    "move; a sha-pinned revision changing is unexpected and worth investigating."
)
CLAIM_LISTING_CURRENT = (
    "Current Hub file listing matches the import-time recorded fingerprint."
)
CLAIM_LISTING_UNVERIFIED = (
    "Post-import file-listing currency was not re-verified this run (Hub "
    "unreachable, nothing recorded at import time, or re-check not attempted). "
    "Other Integrity metadata checks are independent of this claim."
)

CLAIM_BYTES_DIVERGE = (
    "Local artifact bytes differ from the stated trusted reference under the "
    "recorded hash algorithm. This does not establish unauthorized tampering, "
    "malicious intent, Hub compromise, or supply-chain attack."
)
CLAIM_HASH_UNVERIFIED = (
    "Cryptographic identity was not verified: no trusted reference and/or no "
    "local artifact hash. Other Integrity metadata checks are independent of "
    "this claim."
)

NOTE = "Layer A evidence only — Integrity risks do not assign O/S/D"

LIMITATIONS: tuple[str, ...] = (
    "I-INT-REV-UNPINNED, I-INT-MANIFEST-MISSING and I-INT-LICENSE-UNDISCLOSED are "
    "missing identity/disclosure evidence, recorded under disclosure_gaps "
    "(aspect_scoring=disclosure_gap); only byte divergence and listing drift are "
    "risks_triggered.",
    "A local folder's self-computed artifact hashes record which bytes were "
    "evaluated; they are verified only against an authoritative manifest "
    "(operator-supplied, artifact_manifest.json, or train_manifest.json's weight hash). "
    "A manifest stored in the same folder detects accidental or partial change, "
    "not an attacker who can rewrite the folder.",
    "Artifact integrity shows the evaluated bytes match the attested bytes; it "
    "does not show the absence of backdoors, malicious training, data poisoning "
    "or behavioural manipulation baked into those bytes.",
    "A missing artifact (INCOMPLETE) or a missing manifest (UNPINNED) is "
    "unverified evidence, not an integrity risk.",
    "Integrity risks measure disclosure and identity recording, not tampering or "
    "legal compliance.",
    "Named Integrity risks are not additive FRIES occurrences and must not be "
    "summed into O.",
    "Operator-supplied trusted hashes are not a PKI; hash match does not prove "
    "publisher authenticity; mismatch does not prove tampering.",
    "Hub file listing fingerprint identifies sorted filenames, not model weight bytes.",
    "SHA-like revision format is an uncalibrated heuristic, not cryptographic proof "
    "of immutability.",
    "Model card text may reflect the Hub default branch, not the pinned revision.",
    "Post-import file-listing re-verification detects a changed Hub listing, not "
    "weight-byte tampering — it never downloads or hashes weight files.",
)
