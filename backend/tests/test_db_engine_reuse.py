from app.core import db


def test_engine_is_reused_for_url_with_password():
    """Regression: str(engine.url) masks the password, so comparing it to the
    raw URL rebuilt the engine (and leaked its pool) on every request."""
    url = "postgresql+psycopg2://u:secret@localhost:5432/x"
    db.reset_engine()
    try:
        assert db.get_engine(url) is db.get_engine(url)
    finally:
        db.reset_engine()
