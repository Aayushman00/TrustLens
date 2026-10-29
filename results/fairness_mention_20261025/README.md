# Exploratory mention-based fairness run - INCOMPLETE

Plan: docs/superpowers/plans/2026-10-25-mention-fairness-exploratory.md (written before any data existed).
Script: backend/app/scripts/run_fairness_mention.py (prepare / train / eval).

Status (2026-10-25):
- `prepare` done: data/ (800 mention + 2200 other eval rows; 8000-row clean slice; nested flip slices).
- `train` done: models/ holds clean_control and mention_r020/r040/r070/r100 (train_manifest.json in each).
- `eval` NOT completed: the background job was stopped by the system for low memory before any
  probe output was written. analysis/ holds only an empty raw/ directory.
- No results from this run are reported anywhere in the thesis.

To finish: delete the empty analysis/ directory, then run (from backend/, with USE_TF=0 USE_TORCH=1):
    python -m app.scripts.run_fairness_mention eval --out ../results/fairness_mention_20261025
