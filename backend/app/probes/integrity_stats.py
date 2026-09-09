"""Integrity probe constants (tl-integrity-v1.0)."""

from __future__ import annotations

METHODOLOGY_VERSION = "tl-integrity-v1.0"
METHODOLOGY_BASIS = "TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md"

RISK_REV_UNPINNED = "I-INT-REV-UNPINNED"
RISK_MANIFEST_MISSING = "I-INT-MANIFEST-MISSING"
RISK_LICENSE_UNDISCLOSED = "I-INT-LICENSE-UNDISCLOSED"
RISK_BYTES_DIVERGE = "I-INT-BYTES-DIVERGE"

GATE_HASH_UNVERIFIED = "I-INT-HASH-UNVERIFIED"
G_IDENTITY_EMPTY = "G-INT-IDENTITY-EMPTY"
G_HASH_REF_MISSING = "G-INT-HASH-REF-MISSING"
G_HASH_LOCAL_MISSING = "G-INT-HASH-LOCAL-MISSING"

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
)
