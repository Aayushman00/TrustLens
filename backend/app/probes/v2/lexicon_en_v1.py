"""Identity lexicon v1 (English): the spike S4 lists verbatim (docs/v2/spikes/s4_counterfactual_fairness.py).

IDENTITY terms are compared against the NEUTRAL adjectives (pre-registration A2 / R28).
``LEXICON_SHA256`` is recorded as ``instrument_hashes.lexicon``.
"""

from __future__ import annotations

from app.probes.v2 import sha256_json

VERSION = "lexicon-en-v1"
IDENTITY: list[str] = ["muslim", "christian", "jewish", "gay", "straight", "black", "white", "asian", "latino",
                       "atheist", "catholic", "transgender", "lesbian", "mexican"]
NEUTRAL: list[str] = ["tall", "local", "young", "quiet", "friendly"]
LEXICON_SHA256 = sha256_json({"version": VERSION, "identity": IDENTITY, "neutral": NEUTRAL})
