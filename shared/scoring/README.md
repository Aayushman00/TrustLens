# Shared scoring fixtures

Frozen test vectors for the **original FRIES** scorer, used by the backend tests.

> [!NOTE]
> These files are JSON data only. There is **no** scorer implementation, **no** `calculate_fries()` and **no** metric → O/S/D mapping here.

| Item | Detail |
| ---- | ------ |
| Fixture | `fixtures/fries_test_vectors.json` |
| Source | Frozen `implementation/phase0/fries_formula.md` test cases and `golden_reference.md` Table 8 inputs |
| Used by | `backend/tests/test_fries_scorer.py` (oracle documented in [`backend/tests/SCORING.md`](../../backend/tests/SCORING.md)) |
| Not included | FRIES2, which is a proposed extension and is intentionally absent |

Metric → O/S/D remains an open research question (`implementation/phase0/open_research_questions.md`).
