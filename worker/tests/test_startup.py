"""Worker Phase 1 tests — import smoke only."""

import app.main as worker_main


def test_worker_main_imports() -> None:
    assert callable(worker_main.main)
    assert worker_main._shutdown is False
