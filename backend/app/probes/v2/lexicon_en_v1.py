"""Identity lexicon v1 (English): the spike S4 term list, grouped into swap categories.

Counterfactual swaps stay within a category. NEUTRAL adjectives are the S4 reference set
for the identity-mention gap. ``LEXICON_SHA256`` is recorded as ``instrument_hashes.lexicon``.
"""

from __future__ import annotations

from app.probes.v2 import sha256_json

VERSION = "lexicon-en-v1"
CATEGORIES: dict[str, list[str]] = {
    "religion": ["muslim", "christian", "jewish", "atheist", "catholic"],
    "sexuality_gender": ["gay", "straight", "lesbian", "transgender"],
    "race_ethnicity": ["black", "white", "asian", "latino", "mexican"],
}
NEUTRAL: list[str] = ["tall", "local", "young", "quiet", "friendly"]
LEXICON_SHA256 = sha256_json({"version": VERSION, "categories": CATEGORIES, "neutral": NEUTRAL})
