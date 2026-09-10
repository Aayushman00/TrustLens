"""Model Adapter layer (Phase 6, ADR 0012) — see app.adapters.base.

Resolves a Hugging Face Hub repo id/URL to metadata only (never weights),
via ModelService.import_from_hf. NOT to be confused with the unrelated
row -> model-input adapters at app.inference.adapters (ModelInputAdapter),
which convert a dataset row into text for an already-loaded model.
"""
