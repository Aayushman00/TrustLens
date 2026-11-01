# TrustLens v1 freeze — manual honesty checklist

Run after code lands. No Playwright; exercise the UI in a browser.

1. Sign in as researcher (`researcher@trustlens.local`).
2. Import a Hub model (metadata only is enough).
3. Create an evaluation with **Auto-finalize (no human review)** and **no** legacy engine field.
4. Wait until status is **FINALIZED**.
5. Confirm:
   - Probe evidence cards are present (five dimensions) with status / flags / limitations where persisted.
   - O/S/D cells show **Unavailable**, not blank and not `0`.
   - Card **Evaluation complete — FRIES score withheld** is shown; no synthesized FRIES zeros.
   - Disclosure does **not** say O/S/D were generated automatically or that values are AI-proposed.
   - Workflow label is auto-finalize / human-review, not “the AI scored this.”
   - Evidence strength is labeled **uncalibrated**; FRIES hero (if any) does not show OSD-mean confidence.
6. Open the report URL: expect withheld/unavailable copy, not “not finalized yet.”
7. An evaluation list that is empty or filtered does not imply low trust for a missing FRIES score.
8. As researcher, creating with top-level `legacy_heuristic` is rejected (403). Admins may still select that path explicitly.
