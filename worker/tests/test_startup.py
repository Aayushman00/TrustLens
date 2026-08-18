"""Worker Phase 2 tests — import smoke + redis check skip."""

from unittest.mock import patch

import app.main as worker_main
from app.core.redis_client import check_redis


def test_worker_main_imports() -> None:
    assert callable(worker_main.main)
    assert worker_main._shutdown is False


def test_check_redis_skipped_without_url() -> None:
    assert check_redis(None) == "skipped"
    assert check_redis("") == "skipped"


def test_heartbeat_loop_exits_on_shutdown() -> None:
    """Drive one heartbeat then signal shutdown without hanging the suite."""

    def _flip_shutdown(*_args: object, **_kwargs: object) -> None:
        worker_main._shutdown = True

    worker_main._shutdown = False
    with (
        patch("app.main.get_settings") as mock_settings,
        patch("app.main.check_redis", return_value="ok") as mock_ping,
        patch("app.main.time.sleep", side_effect=_flip_shutdown),
        patch("app.main.signal.signal"),
    ):
        mock_settings.return_value.app_env = "test"
        mock_settings.return_value.log_level = "INFO"
        mock_settings.return_value.redis_url = "redis://localhost:6379/0"
        mock_settings.return_value.s3_endpoint = None
        mock_settings.return_value.s3_bucket = "trustlens"
        mock_settings.return_value.worker_heartbeat_seconds = 30
        rc = worker_main.main()
    assert rc == 0
    mock_ping.assert_called()
    worker_main._shutdown = False
